import json
import requests


OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


class LLMClient:
    def __init__(self, model: str = "qwen:7b", timeout: int = 120):
        self.model = model
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }

        try:
            response = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            return str(data.get("response", "")).strip()
        except Exception as exc:
            return f"LLM_ERROR: {exc}"

    def generate_json(self, prompt: str) -> dict:
        raw = self.generate(prompt)

        if raw.startswith("LLM_ERROR:"):
            return {
                "success": False,
                "raw": raw,
                "data": None,
                "error": raw
            }

        text = raw.strip()

        start = text.find("{")
        end = text.rfind("}")

        if start != -1 and end != -1 and end >= start:
            text = text[start:end + 1]

        try:
            parsed = json.loads(text)
            return {
                "success": True,
                "raw": raw,
                "data": parsed,
                "error": ""
            }
        except Exception as exc:
            return {
                "success": False,
                "raw": raw,
                "data": None,
                "error": f"JSON parse failed: {exc}"
            }