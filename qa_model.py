import os
import joblib
import random
from sentence_transformers import SentenceTransformer, util

# === Cache Setup ===
CACHE_DIR = "/app/cache"
os.makedirs(CACHE_DIR, exist_ok=True)

os.environ["HF_HOME"] = CACHE_DIR
os.environ["TRANSFORMERS_CACHE"] = CACHE_DIR
os.environ["TORCH_HOME"] = CACHE_DIR

# === Model Init ===
model = SentenceTransformer("all-MiniLM-L6-v2")
model_path = "qa_model_embeddings.pkl"

def embed(text):
    """Convert text to vector"""
    return model.encode(text, convert_to_tensor=True)

def train_qa_model(collection):
    """Train and save the semantic model from DB"""
    data = list(collection.find())
    questions = [item["question"] for item in data]
    answers = [item["answer"] for item in data]

    embeddings = [embed(q) for q in questions]

    # Save everything
    joblib.dump((embeddings, questions, answers), model_path)
    print("✅ Semantic Q&A model trained and saved.")

def load_and_predict_answer(query, collection, similarity_threshold=0.45, return_multiple=False, exclude_answer=None):
    try:
        embeddings, questions, answers = joblib.load(model_path)
        query_embedding = embed(query)

        scores = [util.pytorch_cos_sim(query_embedding, emb).item() for emb in embeddings]
        matched = [(score, i) for i, score in enumerate(scores) if score >= similarity_threshold]

        if matched:
            matched.sort(reverse=True)
            top_indices = [i for _, i in matched]

            if return_multiple:
                return " ".join([answers[i] for i in top_indices[:3]])

            # Exclude the last used answer if requested
            for i in top_indices:
                candidate = answers[i]
                if candidate != exclude_answer:
                    return candidate
            return answers[top_indices[0]]  # fallback to best match
        return None
    except Exception as e:
        print(f"❌ Error predicting answer: {e}")
        return None
