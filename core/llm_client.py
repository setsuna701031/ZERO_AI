import requests
from typing import Dict, Any, Optional


class LocalLLMClient:
    """
    Local LLM Client for Ollama

    預設設計：
    - general_model: 一般對話 / 規劃 / 非程式任務
    - coder_model: 寫程式 / 改程式 / debug 任務

    目前保留 self.model 作為預設主模型，避免舊程式碼直接壞掉。
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:7b",
        coder_model: str = "qwen2.5-coder:7b",
        timeout: int = 120
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.coder_model = coder_model
        self.timeout = timeout

    def _generate_request(
        self,
        model_name: str,
        prompt: str,
        num_predict: int = 80,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": num_predict,
                "temperature": temperature
            }
        }

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            return {
                "response": "",
                "error": f"Ollama request failed: {exc}",
                "model": model_name,
                "success": False
            }

    def chat(self, prompt: str) -> str:
        """
        用預設主模型回覆純文字。
        舊程式如果直接呼叫 chat()，會走這裡。
        """
        data = self._generate_request(
            model_name=self.model,
            prompt=prompt,
            num_predict=160,
            temperature=0.7
        )
        return data.get("response", "")

    def generate(self, prompt: str) -> Dict[str, Any]:
        """
        用預設主模型回傳完整 JSON 結果。
        """
        data = self._generate_request(
            model_name=self.model,
            prompt=prompt,
            num_predict=160,
            temperature=0.7
        )
        return data

    def chat_with_model(
        self,
        prompt: str,
        model_name: Optional[str] = None,
        num_predict: int = 160,
        temperature: float = 0.7
    ) -> str:
        """
        指定模型輸出純文字。
        """
        selected_model = model_name or self.model
        data = self._generate_request(
            model_name=selected_model,
            prompt=prompt,
            num_predict=num_predict,
            temperature=temperature
        )
        return data.get("response", "")

    def generate_with_model(
        self,
        prompt: str,
        model_name: Optional[str] = None,
        num_predict: int = 160,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        指定模型輸出完整 JSON。
        """
        selected_model = model_name or self.model
        return self._generate_request(
            model_name=selected_model,
            prompt=prompt,
            num_predict=num_predict,
            temperature=temperature
        )

    def chat_general(self, prompt: str) -> str:
        """
        明確使用通用模型。
        """
        return self.chat_with_model(
            prompt=prompt,
            model_name=self.model,
            num_predict=160,
            temperature=0.7
        )

    def chat_coder(self, prompt: str) -> str:
        """
        明確使用程式模型。
        """
        return self.chat_with_model(
            prompt=prompt,
            model_name=self.coder_model,
            num_predict=256,
            temperature=0.2
        )

    def generate_general(self, prompt: str) -> Dict[str, Any]:
        """
        通用模型完整輸出。
        """
        return self.generate_with_model(
            prompt=prompt,
            model_name=self.model,
            num_predict=160,
            temperature=0.7
        )

    def generate_coder(self, prompt: str) -> Dict[str, Any]:
        """
        程式模型完整輸出。
        """
        return self.generate_with_model(
            prompt=prompt,
            model_name=self.coder_model,
            num_predict=256,
            temperature=0.2
        )