from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import cloudinary
import cloudinary.uploader

from train_model import train_classifier_model, predict_class
from qa_model import train_qa_model, load_and_predict_answer
from wiki_search import search_wikipedia

load_dotenv()

app = Flask(__name__)
CORS(app)

# === Database Setup ===
client = MongoClient(os.getenv("MONGO_URI"))
db = client["VoiceAssistant"]
fruit_collection = db["fruits"]
qa_collection = db["qa_data"]

# === Cloudinary Setup ===
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
    name = request.form.get("name", "").lower()
    image = request.files.get("image")

    if not name or not image:
        return jsonify({"error": "Name and image required"}), 400

    upload_result = cloudinary.uploader.upload(image)
    image_url = upload_result.get("secure_url")

    fruit_collection.insert_one({"name": name, "image_url": image_url})
    train_classifier_model(fruit_collection)

    return jsonify({
        "message": f"Fruit '{name}' added and model trained.",
        "image_url": image_url
    })

@app.route("/predict", methods=["POST"])
def predict():
    text = request.json.get("text", "").strip().lower()
    prediction, image_url = predict_class(text, fruit_collection)
    print(f"Prediction: {prediction}, Image URL: {image_url}")

    if prediction:
        return jsonify({"prediction": prediction, "image_url": image_url})
    return jsonify({"error": "No match found."})

@app.route("/ask", methods=["POST"])
def ask():
    question = request.json.get("question", "").strip().lower()

    answer = load_and_predict_answer(question, qa_collection, return_multiple=True)

    if answer:
        return jsonify({
            "answer": answer,
            "source": "local",
            "can_reteach": True
        })

    return jsonify({
        "answer": None,
        "needs_search": True,
        "message": "I couldn't find an answer. Say 'search' or teach me."
    })

@app.route("/regenerate-answer", methods=["POST"])
def regenerate_answer():
    question = request.json.get("question", "").strip().lower()
    last_answer = request.json.get("last_answer", "").strip()

    alt_answer = load_and_predict_answer(
        question,
        collection=qa_collection,
        exclude_answer=last_answer
    )

    if alt_answer:
        return jsonify({"answer": alt_answer})
    return jsonify({"answer": None})


@app.route("/teach", methods=["POST"])
def teach():
    question = request.json.get("question", "").strip().lower()
    answer = request.json.get("answer", "").strip()

    if not question or not answer:
        return jsonify({"error": "Both question and answer required"}), 400

    # Update if exists, else insert
    existing = qa_collection.find_one({"question": question})
    if existing:
        qa_collection.update_one({"_id": existing["_id"]}, {"$set": {"answer": answer}})
    else:
        qa_collection.insert_one({"question": question, "answer": answer})

    train_qa_model(qa_collection)
    return jsonify({"message": "Learned successfully!"})

@app.route("/teach-bulk", methods=["POST"])
def teach_bulk():
    data = request.get_json()

    if not isinstance(data, list):
        return jsonify({"error": "Expected a list of question-answer objects."}), 400

    entries = []
    for item in data:
        question = item.get("question", "").strip().lower()
        answer = item.get("answer", "").strip()
        if question and answer:
            entries.append({"question": question, "answer": answer})

    if not entries:
        return jsonify({"error": "No valid entries."}), 400

    qa_collection.insert_many(entries)
    train_qa_model(qa_collection)

    return jsonify({
        "message": f"✅ {len(entries)} Q&A entries inserted and model retrained."
    })

@app.route("/search-and-learn", methods=["POST"])
def search_and_learn():
    question = request.json.get("question", "").strip().lower()

    if not question:
        return jsonify({"error": "Question is required"}), 400

    answer = search_wikipedia(question)

    if answer:
        qa_collection.insert_one({"question": question, "answer": answer})
        train_qa_model(qa_collection)
        return jsonify({"answer": answer, "source": "wikipedia"})

    return jsonify({"answer": None})



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Default to 5000 if not set
    app.run(host="0.0.0.0", port=port, debug=False)
