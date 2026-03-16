from __future__ import annotations

import requests

from config import LLM_API_URL, LLM_ENABLED, LLM_MODEL, LLM_TIMEOUT
from brain.prompt_manager import PromptManager


class LLMClient:
    def __init__(self) -> None:
        self.enabled = LLM_ENABLED
        self.api_url = LLM_API_URL
        self.model = LLM_MODEL
        self.timeout = LLM_TIMEOUT

    def generate(self, prompt: str) -> str:
        if not self.enabled:
            return "LLM 未啟用。"

        full_prompt = f"{PromptManager.system_prompt()}\n\n{prompt}"
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
        }

        try:
            response = requests.post(self.api_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "模型沒有回傳內容。")
        except Exception as exc:
            return f"LLM 呼叫失敗: {exc}"