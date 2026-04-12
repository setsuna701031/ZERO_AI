from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

from config.config import CONFIG, get_env_llm_override


@dataclass(frozen=True)
class ResolvedLLMConfig:
    """
    最終解析後的 LLM 設定。
    這一層是執行期設定，不是靜態 config。
    """

    plugin_name: str
    provider: str
    base_url: str
    general_model: str
    coder_model: str
    timeout: int


class LocalLLMClient:
    """
    ZERO LLM Client

    設計原則：
    1. 模型視為插件，不寫死在核心邏輯裡
    2. client 只負責“使用”模型，不負責定義全域預設
    3. 預設來源：
       CLI / 呼叫端 override
         > 環境變數 override
         > config.config 中的 plugin 設定
    4. 目前先支援 provider=ollama
    5. 保留 self.model / self.coder_model 以兼容舊程式碼
    """

    def __init__(
        self,
        plugin_name: Optional[str] = None,
        provider: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        coder_model: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> None:
        resolved = self._resolve_config(
            plugin_name=plugin_name,
            provider=provider,
            base_url=base_url,
            model=model,
            coder_model=coder_model,
            timeout=timeout,
        )

        self.plugin_name = resolved.plugin_name
        self.provider = resolved.provider
        self.base_url = resolved.base_url.rstrip("/")
        self.model = resolved.general_model
        self.coder_model = resolved.coder_model
        self.timeout = resolved.timeout

    @staticmethod
    def _resolve_config(
        plugin_name: Optional[str],
        provider: Optional[str],
        base_url: Optional[str],
        model: Optional[str],
        coder_model: Optional[str],
        timeout: Optional[int],
    ) -> ResolvedLLMConfig:
        env_override = get_env_llm_override()

        selected_plugin_name = (
            plugin_name
            or env_override["plugin_name"]
            or CONFIG.llm.default_plugin
        )

        plugin = CONFIG.llm.get_plugin(selected_plugin_name)

        final_provider = provider or env_override["provider"] or plugin.provider
        final_base_url = base_url or env_override["base_url"] or plugin.base_url
        final_general_model = model or env_override["general_model"] or plugin.general_model
        final_coder_model = (
            coder_model
            or env_override["coder_model"]
            or plugin.coder_model
        )
        final_timeout = timeout or env_override["timeout"] or plugin.timeout

        if not final_provider:
            raise ValueError("LLM provider is empty.")

        if final_provider == "ollama" and not final_base_url:
            raise ValueError("Ollama base_url is empty.")

        if not final_general_model:
            raise ValueError("General LLM model is empty.")

        if not final_coder_model:
            raise ValueError("Coder LLM model is empty.")

        return ResolvedLLMConfig(
            plugin_name=selected_plugin_name,
            provider=final_provider,
            base_url=final_base_url,
            general_model=final_general_model,
            coder_model=final_coder_model,
            timeout=int(final_timeout),
        )

    def get_runtime_info(self) -> Dict[str, Any]:
        """
        給 chat_handler / planner / debug 顯示當前實際使用中的模型資訊。
        """
        return {
            "plugin_name": self.plugin_name,
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "coder_model": self.coder_model,
            "timeout": self.timeout,
        }

    def _generate_request(
        self,
        model_name: str,
        prompt: str,
        num_predict: int = 80,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        if self.provider != "ollama":
            return {
                "response": "",
                "error": f"Unsupported LLM provider: {self.provider}",
                "model": model_name,
                "success": False,
            }

        url = f"{self.base_url}/api/generate"

        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": num_predict,
                "temperature": temperature,
            },
        }

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

            if "success" not in data:
                data["success"] = True
            if "model" not in data:
                data["model"] = model_name

            return data

        except requests.exceptions.RequestException as exc:
            return {
                "response": "",
                "error": f"Ollama request failed: {exc}",
                "model": model_name,
                "success": False,
            }

    def chat(self, prompt: str) -> str:
        """
        舊程式相容入口：使用一般模型，回傳純文字。
        """
        data = self._generate_request(
            model_name=self.model,
            prompt=prompt,
            num_predict=160,
            temperature=0.7,
        )
        return data.get("response", "")

    def generate(self, prompt: str) -> Dict[str, Any]:
        """
        舊程式相容入口：使用一般模型，回傳完整 JSON。
        """
        return self._generate_request(
            model_name=self.model,
            prompt=prompt,
            num_predict=160,
            temperature=0.7,
        )

    def chat_with_model(
        self,
        prompt: str,
        model_name: Optional[str] = None,
        num_predict: int = 160,
        temperature: float = 0.7,
    ) -> str:
        selected_model = model_name or self.model
        data = self._generate_request(
            model_name=selected_model,
            prompt=prompt,
            num_predict=num_predict,
            temperature=temperature,
        )
        return data.get("response", "")

    def generate_with_model(
        self,
        prompt: str,
        model_name: Optional[str] = None,
        num_predict: int = 160,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        selected_model = model_name or self.model
        return self._generate_request(
            model_name=selected_model,
            prompt=prompt,
            num_predict=num_predict,
            temperature=temperature,
        )

    def chat_general(self, prompt: str) -> str:
        return self.chat_with_model(
            prompt=prompt,
            model_name=self.model,
            num_predict=160,
            temperature=0.7,
        )

    def chat_coder(self, prompt: str) -> str:
        return self.chat_with_model(
            prompt=prompt,
            model_name=self.coder_model,
            num_predict=256,
            temperature=0.2,
        )

    def generate_general(self, prompt: str) -> Dict[str, Any]:
        return self.generate_with_model(
            prompt=prompt,
            model_name=self.model,
            num_predict=160,
            temperature=0.7,
        )

    def generate_coder(self, prompt: str) -> Dict[str, Any]:
        return self.generate_with_model(
            prompt=prompt,
            model_name=self.coder_model,
            num_predict=256,
            temperature=0.2,
        )