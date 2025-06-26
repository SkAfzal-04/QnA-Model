import os
import joblib
import random
from sentence_transformers import SentenceTransformer, util

# === Cache and Model Paths ===
CACHE_DIR = "/app/cache"
os.makedirs(CACHE_DIR, exist_ok=True)

os.environ["HF_HOME"] = CACHE_DIR
os.environ["TRANSFORMERS_CACHE"] = CACHE_DIR
os.environ["TORCH_HOME"] = CACHE_DIR

model_path = "qa_model_embeddings.pkl"

# === Load SentenceTransformer ===
model = SentenceTransformer("all-MiniLM-L6-v2")

# === Global: Model Memory
embeddings = []
questions = []
answers = []

# === Global memory for last interaction
last_query = None
last_answer = None

# === Helper: Embed Text
def embed(text):
    return model.encode(text, convert_to_tensor=True)

# === Train and Save the Model ===
def train_qa_model(collection):
    global embeddings, questions, answers

    print("⚙️ Training Q&A model...")
    data = list(collection.find())

    if not data:
        print("⚠️ No Q&A data available to train.")
        return "❌ Training failed: No data found."

    embeddings = []
    questions = []
    answers = []

    for item in data:
        q = item["question"].strip().lower()
        ans_list = item["answer"]

        if isinstance(ans_list, str):
            ans_list = [ans_list]

        for ans in ans_list:
            a = ans.strip()
            if a:
                questions.append(q)
                answers.append(a)
                embeddings.append(embed(q))

    try:
        joblib.dump((embeddings, questions, answers), model_path)
        print("✅ Semantic Q&A model trained and saved.")
        return "✅ Semantic Q&A model trained and reloaded."
    except Exception as e:
        print("❌ Failed to save model:", e)
        return f"❌ Model save failed: {e}"

# === Load Model into Memory
def load_model():
    global embeddings, questions, answers
    try:
        embeddings, questions, answers = joblib.load(model_path)
        return True
    except Exception as e:
        print("❌ Failed to load Q&A model:", e)
        return False

# === Shorten long answers
def shorten_text(text, max_sentences=2):
    try:
        sentences = [s.strip() for s in text.strip().split(".") if s.strip()]
        trimmed = ". ".join(sentences[:max_sentences])
        return trimmed + "." if trimmed and not trimmed.endswith(".") else trimmed
    except:
        return text

# === Predict Best Answer
def load_and_predict_answer(
    query,
    collection=None,
    similarity_threshold=0.45,
    return_multiple=False,
    exclude_answer=None,
    redirect=False,
    short=False
):
    global last_query, last_answer, embeddings, questions, answers

    try:
        if not embeddings or not questions or not answers:
            if not load_model():
                if collection:
                    print("📦 Loading from DB due to missing model...")
                    train_qa_model(collection)
                else:
                    print("❌ No model or collection to predict from.")
                    return None

        query_embedding = embed(query)
        scores = [util.pytorch_cos_sim(query_embedding, emb).item() for emb in embeddings]

        matched = [(score, i) for i, score in enumerate(scores) if score >= similarity_threshold]
        if not matched:
            return None

        matched.sort(reverse=True)
        top_score = matched[0][0]
        top_matches = [i for score, i in matched if abs(score - top_score) < 0.01]
        random.shuffle(top_matches)

        selected_answer = None
        for i in top_matches:
            if answers[i] != exclude_answer:
                selected_answer = answers[i]
                break

        if not selected_answer:
            selected_answer = answers[top_matches[0]]

        if redirect:
            alt_matches = [i for _, i in matched if answers[i] != exclude_answer]
            if alt_matches:
                selected_answer = answers[random.choice(alt_matches)]

        if short:
            selected_answer = shorten_text(selected_answer)

        last_query = query
        last_answer = selected_answer
        return selected_answer

    except Exception as e:
        print(f"❌ Error predicting answer: {e}")
        return None
