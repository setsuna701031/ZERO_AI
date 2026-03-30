from __future__ import annotations

from typing import Dict


class Router:
    """
    ZERO Router
    """

    def __init__(self) -> None:
        self.resume_keywords = [
            "繼續任務",
            "繼續上一個任務",
            "繼續剛剛的任務",
            "resume",
            "continue task",
        ]

        self.task_keywords = [
            "分析",
            "設計",
            "寫",
            "建立",
            "讀取",
            "執行",
            "製作",
            "產生",
            "生成",
            "函式",
            "函數",
            "程式",
            "代碼",
            "代码",
            "專案",
            "项目",
            "workspace",
            ".json",
            ".py",
            ".txt",
            ".md",
        ]

        self.web_keywords = [
            "搜尋",
            "查詢",
            "查資料",
            "上網找",
        ]

        self.command_keywords = [
            "command",
            "dir",
            "ls",
            "pwd",
            "cmd",
        ]

    def route(self, user_input: str) -> Dict:
        text = str(user_input).strip()
        lowered = text.lower()

        # resume
        for kw in self.resume_keywords:
            if kw.lower() in lowered:
                return {
                    "mode": "resume",
                    "tool_name": None,
                    "tool_args": {},
                }

        # command
        for kw in self.command_keywords:
            if kw.lower() in lowered:
                return {
                    "mode": "command",
                    "tool_name": "command",
                    "tool_args": {
                        "cmd": text,
                    },
                }

        # web search
        for kw in self.web_keywords:
            if kw in text:
                return {
                    "mode": "tool",
                    "tool_name": "web_search",
                    "tool_args": {
                        "query": text,
                    },
                }

        # task
        for kw in self.task_keywords:
            if kw.lower() in lowered or kw in text:
                return {
                    "mode": "task",
                    "tool_name": None,
                    "tool_args": {},
                }

        # default chat
        return {
            "mode": "chat",
            "tool_name": None,
            "tool_args": {},
        }