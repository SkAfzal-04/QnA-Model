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
    try:
        data = request.get_json() or {}
        question = str(data.get("question", "") or "").strip().lower()
        last_question = str(data.get("last_question", "") or "").strip().lower()
        last_answer = str(data.get("last_answer", "") or "").strip()

        if not question:
            return jsonify({"error": "Question is required"}), 400

        # Check for modifiers
        short_phrases = ["tell shortly", "write short", "short", "summarize", "shortly"]
        expand_phrases = ["describe more", "more details", "explain more", "expand"]

        is_short = question in short_phrases
        is_expand = question in expand_phrases

        true_question = last_question if (is_short or is_expand) and last_question else question

        answer = load_and_predict_answer(
            true_question,
            qa_collection,
            return_multiple=is_expand,
            exclude_answer=last_answer if last_answer else None
        )

        if answer:
            if is_short and len(answer) > 120:
                answer = answer[:120].rsplit('.', 1)[0] + "..."
            return jsonify({
                "answer": answer,
                "source": "local",
                "can_reteach": True
            })

        # If expand requested but no answer found locally, search online
        if is_expand:
            wiki_answer = search_wikipedia(true_question)
            if wiki_answer:
                return jsonify({
                    "answer": wiki_answer,
                    "source": "wiki",
                    "can_reteach": True,
                    "can_save": True
                })
            else:
                return jsonify({
                    "answer": None,
                    "source": "none",
                    "can_search": True,
                    "can_teach": True
                })

        # If no answer found at all, prompt to teach or search
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
            if answer.lower() not in old_answer.lower():
                new_answer = f"{old_answer} / {answer}"
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
