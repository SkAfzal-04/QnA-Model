from sentence_transformers import SentenceTransformer, util

# Load model
model = SentenceTransformer('all-MiniLM-L6-v2')

# === Feedback Phrases ===
negative_examples = [
    "no you are wrong", "you're wrong", "that's incorrect", "wrong answer",
    "not true", "not correct", "that's not correct", "that's not right",
    "i don't think so", "you are mistaken", "incorrect", "that's false",
    "you are wrong", "i disagree", "not really", "nope", "nah", "that’s not what i meant",
    "that’s not it", "you got it wrong", "not what i asked", "completely wrong",
    "totally wrong", "absolutely wrong", "that's a mistake", "you messed up",
    "you said it wrong", "false", "no", "that's nonsense", "that makes no sense"
]
negative_embeddings = model.encode(negative_examples, convert_to_tensor=True)

# === Cancel Phrases ===
cancel_phrases = [
    "cancel", "ok", "leave", "nevermind", "forget it", "forget", "skip", "stop",
    "not now", "not interested", "let it go", "ignore that", "just leave it", "nvm"
]
cancel_embeddings = model.encode(cancel_phrases, convert_to_tensor=True)
# === Casual phrases that should not trigger search
casual_phrases = [
    "ok", "okay", "cool", "great", "thanks", "thank you", "fine", "awesome", "good", "alright", "nice"
]
casual_embeddings = model.encode(casual_phrases, convert_to_tensor=True)

# === Modifiers ===


short_phrases = [
    "tell shortly", "write short", "short", "summarize", "shortly",
    "keep it short", "make it brief", "brief it", "in short", "concise",
    "tl;dr", "give a summary", "short version", "just a line"
]

short_embeddings = model.encode(short_phrases, convert_to_tensor=True)

expand_phrases = [
    "describe more", "more details", "explain more", "expand",
    "elaborate", "tell me more", "go deeper", "more info",
    "what else", "continue", "explain in detail", "add more"
]
expand_embeddings = model.encode(expand_phrases, convert_to_tensor=True)

# === Checks ===

def is_negative_feedback(user_input: str) -> bool:
    user_embedding = model.encode(user_input, convert_to_tensor=True)
    similarities = util.cos_sim(user_embedding, negative_embeddings)
    max_score = similarities.max().item()
    return max_score > 0.7

def is_cancel_feedback(user_input: str) -> bool:
    user_embedding = model.encode(user_input, convert_to_tensor=True)
    similarities = util.cos_sim(user_embedding, cancel_embeddings)
    max_score = similarities.max().item()
    return max_score > 0.7


def is_casual_followup(user_input: str) -> bool:
    """Detect small talk or confirmations that don't require an answer"""
    user_embedding = model.encode(user_input, convert_to_tensor=True)
    similarities = util.cos_sim(user_embedding, casual_embeddings)
    return similarities.max().item() > 0.7


def is_shorten_command(user_input: str) -> bool:
    user_embedding = model.encode(user_input, convert_to_tensor=True)
    similarities = util.cos_sim(user_embedding, short_embeddings)
    return similarities.max().item() > 0.7

def is_expand_command(user_input: str) -> bool:
    user_embedding = model.encode(user_input, convert_to_tensor=True)
    similarities = util.cos_sim(user_embedding, expand_embeddings)
    return similarities.max().item() > 0.7
