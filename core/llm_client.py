import requests
from typing import Dict, Any


class LocalLLMClient:
    """
    Local LLM Client for Ollama
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "zero_lite:latest",
        timeout: int = 120
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat(self, prompt: str) -> str:
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 80,
                "temperature": 0.7
            }
        }

        response = requests.post(
            url,
            json=payload,
            timeout=self.timeout
        )
        response.raise_for_status()

        data = response.json()
        return data.get("response", "")

    def generate(self, prompt: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 80,
                "temperature": 0.7
            }
        }

        response = requests.post(
            url,
            json=payload,
            timeout=self.timeout
        )
        response.raise_for_status()

        return response.json()