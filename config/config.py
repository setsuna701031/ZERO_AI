from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WebSearchConfig:
    mode: str = "searxng"
    searxng_base_url: str = "http://127.0.0.1:8888"
    timeout: int = 10
    max_results: int = 5
    language: str = "zh-TW"
    safesearch: int = 1


@dataclass(frozen=True)
class LLMConfig:
    base_url: str = "http://127.0.0.1:11434"
    model: str = "llama3.1:latest"
    timeout: int = 120
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