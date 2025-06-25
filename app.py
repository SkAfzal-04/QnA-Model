from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import cloudinary
import cloudinary.uploader

from train_model import train_classifier_model, predict_class
from qa_model import train_qa_model, load_and_predict_answer, shorten_text, last_answer, last_query
from wiki_search import search_wikipedia
from utils.feedback_utils import is_negative_feedback, is_shorten_command, is_expand_command,is_cancel_feedback,is_casual_followup


# === Setup ===
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

# === Global States for Correction Learning ===
pending_correction = False
last_failed_question = None
last_real_question = None


# === ROUTES ===

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
        return jsonify({"error": f"Image upload failed: {str(e)}"}), 500

    fruit_collection.insert_one({"name": name, "image_url": image_url})
    train_classifier_model(fruit_collection)

    return jsonify({
        "message": f"Fruit '{name}' added and model trained.",
        "image_url": image_url
    })


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

    try:
        data = request.get_json() or {}
        question = str(data.get("question", "")).strip().lower()
        last_question = str(data.get("last_question", "") or "").strip().lower()
        prev_answer = str(data.get("last_answer", "") or "").strip()

        if not question:
            return jsonify({"error": "Question is required"}), 400

        if is_casual_followup(question):
            return jsonify({"answer": None, "source": "skip", "message": "No response needed."})

        if pending_correction and is_cancel_feedback(question):
            pending_correction = False
            last_failed_question = None
            return jsonify({"answer": "Okay, no changes made.", "source": "cancelled"})

        if pending_correction and last_failed_question:
            existing = qa_collection.find_one({"question": last_failed_question})
            if existing:
                old = existing.get("answer", "")
                parts = [part.strip().lower() for part in old.split("/")]
                if question.lower() not in parts:
                    new_answer = old + " / " + question
                else:
                    new_answer = old
                qa_collection.update_one(
                    {"question": last_failed_question},
                    {"$set": {"answer": new_answer}},
                    upsert=True
                )
            else:
                qa_collection.insert_one({"question": last_failed_question, "answer": question})

            train_qa_model(qa_collection)
            pending_correction = False
            last_failed_question = None
            return jsonify({
                "answer": f"✅ Learned: \"{last_real_question}\" → \"{question}\"",
                "source": "learned"
            })

        if is_negative_feedback(question):
            pending_correction = True
            last_failed_question = last_real_question or last_question
            return jsonify({
                "answer": "❌ That may be wrong. Please provide the correct answer.",
                "source": "correction"
            })

        is_short = is_shorten_command(question)
        is_expand = is_expand_command(question)
        real_q = last_question if (is_short or is_expand) and last_question else question
        last_real_question = real_q

        answer = load_and_predict_answer(
            real_q,
            qa_collection,
            return_multiple=is_expand,
            exclude_answer=prev_answer if prev_answer else None,
            short=is_short
        )

        if answer:
            return jsonify({"answer": answer, "source": "local", "can_reteach": True})

        wiki_answer = search_wikipedia(real_q)
        if wiki_answer:
            qa_collection.update_one(
                {"question": real_q},
                {"$set": {"answer": wiki_answer}},
                upsert=True
            )
            train_qa_model(qa_collection)
            return jsonify({"answer": wiki_answer, "source": "wiki", "can_reteach": True})

        last_failed_question = real_q
        return jsonify({
            "answer": None,
            "source": "none",
            "can_teach": True,
            "can_search": True
        })

    except Exception as e:
        print("🔥 Internal Server Error:", str(e))
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


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
    last_question = data.get("last_question", "").strip().lower()

    # Follow-up handling
    expand_phrases = ["describe more", "more details", "explain more", "expand"]
    true_question = last_question if question in expand_phrases else question

    if not true_question:
        return jsonify({"error": "Valid question is required"}), 400

    wiki_answer = search_wikipedia(true_question)

    if wiki_answer:
        try:
            existing = qa_collection.find_one({"question": true_question})
            if existing:
                qa_collection.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"answer": wiki_answer}}
                )
            else:
                qa_collection.insert_one({
                    "question": true_question,
                    "answer": wiki_answer
                })
            train_qa_model(qa_collection)
        except Exception as e:
            print("❌ Failed to save/train from wiki:", e)

        return jsonify({
            "answer": wiki_answer,
            "source": "wiki",
            "can_reteach": True,
            "question": true_question
        })

    return jsonify({
        "answer": None,
        "source": "none",
        "message": "Nothing found in Wikipedia either.",
        "question": true_question
    })


@app.route("/teach", methods=["POST"])
def teach():
    data = request.get_json()
    question = data.get("question", "").strip().lower()
    answer = data.get("answer", "").strip()

    if not question or not answer:
        return jsonify({"error": "Both question and answer required"}), 400

    try:
        existing = qa_collection.find_one({"question": question})
        if existing:
            old_answer = existing.get("answer", "")
            parts = [part.strip().lower() for part in old_answer.split("/")]
            if answer.lower() not in parts:
                new_answer = old_answer + " / " + answer
                qa_collection.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"answer": new_answer}}
                )
        else:
            qa_collection.insert_one({"question": question, "answer": answer})

        train_qa_model(qa_collection)
        return jsonify({"message": "Learned successfully!"})

    except Exception as e:
        return jsonify({"error": f"Failed to save or train: {str(e)}"}), 500





@app.route("/teach-bulk", methods=["POST"])
def teach_bulk():
    data = request.get_json()
    if not isinstance(data, list):
        return jsonify({"error": "Expected a list of question-answer objects."}), 400

    entries = [
        {"question": item.get("question", "").strip().lower(), "answer": item.get("answer", "").strip()}
        for item in data if item.get("question") and item.get("answer")
    ]

    if not entries:
        return jsonify({"error": "No valid entries."}), 400

    qa_collection.insert_many(entries)
    train_qa_model(qa_collection)

    return jsonify({
        "message": f"✅ {len(entries)} Q&A entries inserted and model retrained."
    })


@app.route("/search-and-learn", methods=["POST"])
def search_and_learn():
    data = request.get_json()
    question = data.get("question", "").strip().lower()

    if not question:
        return jsonify({"error": "Question is required"}), 400

    answer = search_wikipedia(question)
    if answer:
        existing = qa_collection.find_one({"question": question})
        if existing:
            qa_collection.update_one({"_id": existing["_id"]}, {"$set": {"answer": answer}})
        else:
            qa_collection.insert_one({"question": question, "answer": answer})

        train_qa_model(qa_collection)
        return jsonify({"answer": answer, "source": "wikipedia"})

    return jsonify({"answer": None})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=True)
