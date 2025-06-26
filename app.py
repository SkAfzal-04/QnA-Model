from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import cloudinary
import cloudinary.uploader
# app.py
from transformers import pipeline

summarizer = None

def get_summarizer():
    global summarizer
    if summarizer is None:
        print("🧠 Loading summarizer model...")
        summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
    return summarizer




from train_model import train_classifier_model, predict_class
from qa_model import train_qa_model, load_and_predict_answer, shorten_text, last_answer, last_query
from search import search_wikipedia,search_duckduckgo
from utils.feedback_utils import (
    is_negative_feedback,
    is_shorten_command,
    is_expand_command,
    is_cancel_feedback,
    is_casual_followup
)

load_dotenv()
app = Flask(__name__)
CORS(app)

client = MongoClient(os.getenv("MONGO_URI"))
db = client["VoiceAssistant"]
fruit_collection = db["fruits"]
qa_collection = db["qa_data"]

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

pending_correction = False
last_failed_question = None
last_real_question = None

def migrate_answer_to_array():
    print("🔁 Starting migration...")
    updated = 0
    skipped = 0
    for doc in qa_collection.find():
        answer = doc.get("answer")
        if isinstance(answer, str):
            split_answers = [a.strip() for a in answer.split("/") if a.strip()]
            qa_collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"answer": split_answers}}
            )
            updated += 1
        elif isinstance(answer, list) and len(answer) == 1 and "/" in answer[0]:
            split_answers = [a.strip() for a in answer[0].split("/") if a.strip()]
            qa_collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"answer": split_answers}}
            )
            updated += 1
        else:
            skipped += 1
    print(f"✅ Migration done: {updated} updated, {skipped} skipped.")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/add-fruit", methods=["POST"])
def add_fruit():
    name = request.form.get("name", "").strip().lower()
    image = request.files.get("image")
    if not name or not image:
        return jsonify({"error": "Name and image required"}), 400
    try:
        upload_result = cloudinary.uploader.upload(image)
        image_url = upload_result.get("secure_url")
    except Exception as e:
        return jsonify({"error": f"Upload failed: {str(e)}"}), 500
    fruit_collection.insert_one({"name": name, "image_url": image_url})
    train_classifier_model(fruit_collection)
    return jsonify({"message": f"Fruit '{name}' added.", "image_url": image_url})

@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()
    text = data.get("text", "").strip().lower()
    prediction, image_url = predict_class(text, fruit_collection)
    if prediction:
        return jsonify({"prediction": prediction, "image_url": image_url})
    return jsonify({"error": "No match found."}), 404

@app.route("/ask", methods=["POST"])
def ask():
    global pending_correction, last_failed_question, last_real_question

    data = request.get_json() or {}
    question = str(data.get("question", "")).strip().lower()
    last_question = str(data.get("last_question", "") or "").strip().lower()
    prev_answer = str(data.get("last_answer", "") or "").strip()

    if not question:
        return jsonify({"error": "Question is required"}), 400

    # 1. Skip casual replies
    if is_casual_followup(question):
        return jsonify({"answer": None, "source": "skip", "message": "No response needed."})

    # 2. Handle cancel feedback
    if pending_correction and is_cancel_feedback(question):
        pending_correction = False
        last_failed_question = None
        return jsonify({"answer": "Okay, no changes made.", "source": "cancelled"})

    # 3. Handle correction input
    if pending_correction and last_failed_question:
        correct_answer = question.strip()

        # ❌ Don't allow same question as answer
        if correct_answer.lower() == last_failed_question.lower():
            pending_correction = False
            last_failed_question = None
            return jsonify({
                "answer": "⚠️ Cannot save same answer as question.",
                "source": "skip"
            })

        teach_data = {
            "question": last_failed_question,
            "answer": correct_answer
        }
        pending_correction = False
        last_failed_question = None
        last_real_question = None

        with app.test_request_context(json=teach_data):
            teach_response = teach()

        return jsonify({
            "answer": f"✅ Learned: \"{teach_data['question']}\" → \"{teach_data['answer']}\"",
            "source": "learned"
        })

    # 4. Handle "you are wrong"/"no" type feedback
    if is_negative_feedback(question):
        if last_real_question:
            pending_correction = True
            last_failed_question = last_real_question or last_question
            return jsonify({
                "answer": "❌ Got it. What should the correct answer be?",
                "source": "correction"
            })
        else:
            return jsonify({
                "answer": "⚠️ Sorry, I need a valid question to correct.",
                "source": "skip"
            })

    # 5. Handle expand/shorten follow-up
    is_short = is_shorten_command(question)
    is_expand = is_expand_command(question)
    real_q = last_question if (is_short or is_expand) and last_question else question
    last_real_question = real_q

    # 6. Try local prediction
    answer = load_and_predict_answer(
        real_q,
        collection=qa_collection,
        return_multiple=is_expand,
        exclude_answer=prev_answer or None,
        short=is_short
    )

    if answer:
        return jsonify({"answer": answer, "source": "local", "can_reteach": True})

    # 7. No answer found → return teach/search options
    last_failed_question = real_q
    return jsonify({
        "answer": None,
        "source": "none",
        "can_teach": True,
        "can_search": True,
        "question": real_q
    })
@app.route("/teach", methods=["POST"])
def teach():
    data = request.get_json()
    question = data.get("question", "").strip().lower()
    answer = data.get("answer", "").strip()

    if not question or not answer:
        return jsonify({"error": "Both question and answer required"}), 400

    # ❌ Prevent saving same answer as question
    if question == answer.lower():
        return jsonify({"error": "Answer cannot be the same as the question."}), 400

    # Clean malformed characters like quotes
    answer = answer.replace('"', '').replace("'", "").strip()

    existing = qa_collection.find_one({"question": question})
    if existing:
        old = existing.get("answer", [])
        if isinstance(old, str):
            old = [old]
        if answer not in old:
            old.append(answer)
            qa_collection.update_one({"_id": existing["_id"]}, {"$set": {"answer": old}})
    else:
        qa_collection.insert_one({"question": question, "answer": [answer]})

    train_qa_model(qa_collection)
    return jsonify({"message": "✅ Learned successfully."})

@app.route("/regenerate-answer", methods=["POST"])
def regenerate_answer():
    data = request.get_json()
    question = data.get("question", "").strip().lower()
    last_answer = data.get("last_answer", "").strip()

    if not question or not last_answer:
        return jsonify({"error": "Both question and last_answer required"}), 400

    alt_answer = load_and_predict_answer(
        question,
        collection=qa_collection,
        exclude_answer=last_answer
    )
    return jsonify({"answer": alt_answer or None})


@app.route("/search", methods=["POST"])
def search():
    data = request.get_json()
    question = data.get("question", "").strip().lower()

    if not question:
        return jsonify({"error": "Question is required"}), 400

    # 1. Fetch both sources
    wiki_answer = search_wikipedia(question)
    duck_answer = search_duckduckgo(question)

    if not wiki_answer and not duck_answer:
        return jsonify({
            "answer": None,
            "source": "none",
            "message": "No information found from Wikipedia or DuckDuckGo.",
            "question": question
        })

    # 2. Merge both (even if one is missing)
    combined = ""
    if wiki_answer:
        combined += wiki_answer.strip()
    if duck_answer and duck_answer.strip() not in combined:
        combined += "\n\n" + duck_answer.strip()

    # 3. Generate centralized summarized answer
    try:
        summarized = summarizer(combined, max_length=130, min_length=50, do_sample=False)
        final_answer = summarized[0]["summary_text"]
    except Exception as e:
        print("⚠️ Summarization failed:", e)
        final_answer = combined.strip()

    # 4. Save to MongoDB
    existing = qa_collection.find_one({"question": question})
    if existing:
        old_answers = existing.get("answer", [])
        if isinstance(old_answers, str):
            old_answers = [old_answers]
        if final_answer not in old_answers:
            old_answers.append(final_answer)
            qa_collection.update_one(
                {"_id": existing["_id"]},
                {"$set": {"answer": old_answers}}
            )
    else:
        qa_collection.insert_one({"question": question, "answer": [final_answer]})

    # 5. Retrain QA model
    train_qa_model(qa_collection)

    # 6. Return response
    return jsonify({
        "answer": final_answer,
        "source": "wiki+duckduckgo+summarized",
        "question": question
    })



@app.route("/teach-bulk", methods=["POST"])
def teach_bulk():
    data = request.get_json()
    if not isinstance(data, list):
        return jsonify({"error": "Expected a list of question-answer objects."}), 400

    entries = []
    for item in data:
        q = item.get("question", "").strip().lower()
        a = item.get("answer", "").strip()
        if q and a:
            entries.append({"question": q, "answer": [a]})

    if not entries:
        return jsonify({"error": "No valid entries."}), 400

    qa_collection.insert_many(entries)
    train_qa_model(qa_collection)
    return jsonify({
        "message": f"✅ {len(entries)} Q&A entries inserted and model retrained."
    })



if __name__ == "__main__":
   
    # print("🔁 Starting migration...")
    # migrate_answer_to_array()  # Only run once
    # print("✅ Migration complete.")

    # ✅ Start Flask app
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=True)

