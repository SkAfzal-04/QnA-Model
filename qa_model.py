from sentence_transformers import SentenceTransformer, util
import joblib
import random

# Load model once
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
            return answers[top_indices[0]]  # Fallback to the best match if all match previous
        return None
    except Exception as e:
        print(f"❌ Error predicting alternate answer: {e}")
        return None

