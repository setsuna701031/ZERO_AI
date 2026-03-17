import json
import os
import urllib.request
import urllib.error


OLLAMA_BASE_URL = os.environ.get("ZERO_OLLAMA_BASE_URL", "http://127.0.0.1:11434/api")
DEFAULT_OLLAMA_MODEL = os.environ.get("ZERO_OLLAMA_MODEL", "llama3.1")
OLLAMA_TIMEOUT = int(os.environ.get("ZERO_OLLAMA_TIMEOUT", "120"))


def ask_local_llm(question: str, model_name: str | None = None) -> dict:
    question = (question or "").strip()
    model_name = (model_name or DEFAULT_OLLAMA_MODEL).strip()

    if not question:
        return {
            "success": False,
            "backend": "ollama",
            "model": model_name,
            "message": "question is empty",
        }

    url = f"{OLLAMA_BASE_URL.rstrip('/')}/generate"

    payload = {
        "model": model_name,
        "prompt": question,
        "stream": False,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            result = json.loads(raw)

        return {
            "success": True,
            "backend": "ollama",
            "model": result.get("model", model_name),
            "answer": result.get("response", "").strip(),
            "raw": result,
        }

    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        return {
            "success": False,
            "backend": "ollama",
            "model": model_name,
            "message": f"http error: {exc.code}",
            "details": body,
        }

    except urllib.error.URLError as exc:
        return {
            "success": False,
            "backend": "ollama",
            "model": model_name,
            "message": f"url error: {exc}",
        }

    except Exception as exc:
        return {
            "success": False,
            "backend": "ollama",
            "model": model_name,
            "message": f"llm request failed: {exc}",
        }