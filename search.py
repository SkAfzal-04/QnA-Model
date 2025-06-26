import wikipedia
import requests
from bs4 import BeautifulSoup

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
    



import requests
from bs4 import BeautifulSoup

def search_duckduckgo(query):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        return f"❌ DuckDuckGo search failed: {str(e)}"

    soup = BeautifulSoup(response.text, 'html.parser')
    results = soup.find_all('div', class_='result__snippet', limit=3)

    if not results:
        return None  # So it can fallback to Wikipedia or partial answers

    snippets = [res.get_text(strip=True) for res in results if res.get_text(strip=True)]
    return " ".join(snippets) if snippets else None




