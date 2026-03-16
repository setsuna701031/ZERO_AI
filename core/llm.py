import requests


class LocalLLM:

    def __init__(self, model="qwen:7b"):

        self.model = model
        self.url = "http://localhost:11434/api/generate"

        print("LLM model:", self.model)

    def generate(self, prompt):

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 32,
                "temperature": 0.1
            }
        }

        response = requests.post(
            self.url,
            json=payload,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        return data.get("response", "").strip()