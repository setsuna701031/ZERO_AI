import requests


OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


def ollama_generate(prompt: str, model: str = "llama3.1") -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }

    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        return data.get("response", "")
    except Exception as e:
        return f"OLLAMA_ERROR: {e}"