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

# === Global memory for recent interaction
last_query = None
last_answer = None

# === Helper: Embed a text
def embed(text):
    """Convert text to vector"""
    return model.encode(text, convert_to_tensor=True)

# === Helper: Train and save Q&A model
def train_qa_model(collection):
    """Train and save the semantic model from DB"""
    data = list(collection.find())
    questions = [item["question"] for item in data]
    answers = [item["answer"] for item in data]
    embeddings = [embed(q) for q in questions]
    joblib.dump((embeddings, questions, answers), model_path)
    print("✅ Semantic Q&A model trained and saved.")

# === Helper: Shorten long text to 1-2 sentences
def shorten_text(text, max_sentences=2):
    try:
        sentences = text.strip().split(".")
        trimmed = ". ".join([s.strip() for s in sentences[:max_sentences]])
        return trimmed + "." if trimmed and not trimmed.endswith(".") else trimmed
    except:
        return text

# === Core: Answer loader and predictor
def load_and_predict_answer(
    query,
    collection,
    similarity_threshold=0.45,
    return_multiple=False,
    exclude_answer=None,
    redirect=False,
    short=False
):
    global last_query, last_answer
    try:
        # Load saved embeddings and data
        embeddings, questions, answers = joblib.load(model_path)
        query_embedding = embed(query)

        # Calculate cosine similarity scores
        scores = [util.pytorch_cos_sim(query_embedding, emb).item() for emb in embeddings]
        matched = [(score, i) for i, score in enumerate(scores) if score >= similarity_threshold]

        if not matched:
            return None

        # Sort matches by score and find top-scoring ones
        matched.sort(reverse=True)
        top_score = matched[0][0]
        top_matches = [i for score, i in matched if abs(score - top_score) < 0.01]
        random.shuffle(top_matches)

        selected_answer = None
        for i in top_matches:
            if answers[i] != exclude_answer:
                selected_answer = answers[i]
                break

        # Fallback if none found
        if not selected_answer:
            selected_answer = answers[top_matches[0]]

        # Alternative if redirection requested
        if redirect:
            alt_matches = [i for _, i in matched if answers[i] != exclude_answer]
            if alt_matches:
                selected_answer = answers[random.choice(alt_matches)]

        # Shorten if requested
        if short:
            selected_answer = shorten_text(selected_answer)

        # Save last interaction
        last_query = query
        last_answer = selected_answer
        return selected_answer

    except Exception as e:
        print(f"❌ Error predicting answer: {e}")
        return None
