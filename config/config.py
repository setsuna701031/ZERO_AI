from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class WebSearchConfig:
    mode: str = "searxng"
    searxng_base_url: str = "http://127.0.0.1:8888"
    timeout: int = 10
    max_results: int = 5
    language: str = "zh-TW"
    safesearch: int = 1


@dataclass(frozen=True)
class LLMPluginConfig:
    """
    單一 LLM 插件設定。

    設計目標：
    - 把模型視為插件，而不是寫死在核心
    - 每個使用者可以依硬體/環境替換 provider / model
    - 目前先支援 ollama，未來可擴 openai / anthropic / vllm / lmstudio
    """

    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    general_model: str = "llama3.1:latest"
    coder_model: str = "llama3.1:latest"
    timeout: int = 120
    enabled: bool = True


@dataclass(frozen=True)
class LLMConfig:
    """
    LLM 總設定。

    規則：
    - default_plugin: 預設使用哪個插件
    - plugins: 所有可用插件的設定表
    - system_prompt: 給主模型的系統提示詞
    """

    default_plugin: str = "local_ollama"
    plugins: dict[str, LLMPluginConfig] = field(
        default_factory=lambda: {
            "local_ollama": LLMPluginConfig(
                provider="ollama",
                base_url="http://127.0.0.1:11434",
                general_model="llama3.1:latest",
                coder_model="llama3.1:latest",
                timeout=120,
                enabled=True,
            )
        }
    )
    system_prompt: str = (
        "你是 ZERO，本地工程型 AI 助手。"
        "回答風格必須直接、短、清楚、務實。"
        "禁止使用客服式寒暄。"
        "禁止說『很高興幫助你』、『很樂意幫你』、『如何幫助您』、『請問有什麼可以協助』。"
        "禁止過度禮貌與空話。"
        "不要雞湯，不要安撫，不要灌水。"
        "能一句講完，就不要講兩句。"
        "若使用者只說『你好』，只回『你好。』"
        "若使用者問『你是誰』，只回『我是 ZERO，本地工程型 AI 助手。』"
        "若資訊不足，直接說資訊不足。"
    )

    def get_plugin(self, plugin_name: Optional[str] = None) -> LLMPluginConfig:
        selected = (plugin_name or self.default_plugin).strip()
        plugin = self.plugins.get(selected)

        if plugin is None:
            raise ValueError(f"Unknown LLM plugin: {selected}")

        if not plugin.enabled:
            raise ValueError(f"LLM plugin is disabled: {selected}")

        return plugin


@dataclass(frozen=True)
class FileToolConfig:
    workspace_root: str = "./workspace"
    encoding: str = "utf-8"


@dataclass(frozen=True)
class AppConfig:
    app_name: str = "ZERO AI - Local Agent Prototype"
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    file_tool: FileToolConfig = field(default_factory=FileToolConfig)


CONFIG = AppConfig()


def get_env_llm_override() -> dict[str, Optional[str]]:
    """
    提供環境變數覆蓋，但不直接污染 CONFIG。
    由 llm_client / system_boot 在初始化時決定是否套用。

    支援：
    - ZERO_LLM_PLUGIN
    - ZERO_LLM_PROVIDER
    - ZERO_LLM_BASE_URL
    - ZERO_MODEL
    - ZERO_CODER_MODEL
    - ZERO_LLM_TIMEOUT
    """
    timeout_raw = os.getenv("ZERO_LLM_TIMEOUT", "").strip()
    timeout_value: Optional[int] = None

    if timeout_raw:
        try:
            timeout_value = int(timeout_raw)
        except ValueError:
            timeout_value = None

    return {
        "plugin_name": os.getenv("ZERO_LLM_PLUGIN", "").strip() or None,
        "provider": os.getenv("ZERO_LLM_PROVIDER", "").strip() or None,
        "base_url": os.getenv("ZERO_LLM_BASE_URL", "").strip() or None,
        "general_model": os.getenv("ZERO_MODEL", "").strip() or None,
        "coder_model": os.getenv("ZERO_CODER_MODEL", "").strip() or None,
        "timeout": timeout_value,
    }