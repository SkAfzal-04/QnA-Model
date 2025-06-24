import wikipedia

def search_wikipedia(query):
    try:
        return wikipedia.summary(query, sentences=2)
    except wikipedia.exceptions.DisambiguationError as e:
        return f"Multiple results found: {e.options[0]}"
    except wikipedia.exceptions.PageError:
        return None
    except Exception as e:
        print("Wikipedia search error:", e)
        return None
