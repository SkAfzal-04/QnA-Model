from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from bson.regex import Regex
import joblib


import os
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

def train_classifier_model(collection):
    print("🔧 Starting training...")
    data = list(collection.find())

    if len(data) < 2:
        print(f"❌ Not enough data to train. Found {len(data)} record(s).")
        return

    # Print all data entries
    print(f"📦 Training data ({len(data)} items):", data)

    texts = [item['name'] for item in data]
    labels = [item['name'] for item in data]

    try:
        model = Pipeline([
            ('tfidf', TfidfVectorizer()),
            ('clf', LogisticRegression())
        ])
        model.fit(texts, labels)
        print("✅ Model trained successfully.")

        # Ensure model save directory is valid
        model_path = os.path.join(os.getcwd(), "model.pkl")
        print(f"💾 Saving model to: {model_path}")

        joblib.dump(model, model_path)
        print("✅ Model saved to model.pkl.")
    except Exception as e:
        print(f"❌ Error training or saving model: {e}")



def predict_class(query, collection):
    try:
        model = joblib.load('model.pkl')
        prediction = model.predict([query])[0]

        # Use regex to find case-insensitive match in MongoDB
        match = collection.find_one({"name": Regex(f"^{prediction}$", "i")})
        # print(f"Prediction: {prediction}, Match: {match}")

        if match and "image_url" in match:
            return prediction, match["image_url"]
        elif match:
            return prediction, None  # Image missing
        else:
            return prediction, None  # Prediction found but no match in DB
    except Exception as e:
        print(f"❌ Error in predict_class: {e}")
        return None, None