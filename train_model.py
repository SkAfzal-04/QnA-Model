from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from bson.regex import Regex
import joblib


def train_classifier_model(collection):
    data = list(collection.find())
    if len(data) < 2:
        print("❌ Need at least two classes to train.")
        return

    texts = [item['name'] for item in data]
    labels = [item['name'] for item in data]

    model = Pipeline([
        ('tfidf', TfidfVectorizer()),
        ('clf', LogisticRegression())
    ])
    model.fit(texts, labels)
    joblib.dump(model, 'model.pkl')
    print("✅ Fruit classification model trained.")



def predict_class(query, collection):
    try:
        model = joblib.load('model.pkl')
        print("🟡 All items in database:")
        for item in collection.find():
            print(item)
        prediction = model.predict([query])[0]

        # Use regex to find case-insensitive match in MongoDB
        match = collection.find_one({"name": Regex(f"^{prediction}$", "i")})
        print(f"Prediction: {prediction}, Match: {match}")

        if match and "image_url" in match:
            return prediction, match["image_url"]
        elif match:
            return prediction, None  # Image missing
        else:
            return prediction, None  # Prediction found but no match in DB
    except Exception as e:
        print(f"❌ Error in predict_class: {e}")
        return None, None