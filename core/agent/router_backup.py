from __future__ import annotations

import re
from typing import Dict, Optional


class SimpleRouter:
    """
    ZERO Router（單一乾淨版）

    只回三種 mode：
    - direct: 直接交給 step_executor
    - task:   交給 task mode
    - llm:    交給聊天/LLM 路徑（目前未啟用時由 agent_loop 回覆）
    """

    def route(self, user_input: str, context: Optional[Dict] = None) -> Dict:
        text = str(user_input or "").strip()
        lowered = text.lower()

        if not text:
            return {"mode": "llm"}

        # 1) 明確 command 前綴
        if lowered.startswith("command:"):
            cmd = text[len("command:"):].strip()
            return {
                "mode": "direct",
                "step": {
                    "type": "command",
                    "command": cmd,
                },
            }

        # 2) 寫檔
        write_step = self._match_write_file(text)
        if write_step is not None:
            return {
                "mode": "direct",
                "step": write_step,
            }

        # 3) 讀檔
        read_step = self._match_read_file(text)
        if read_step is not None:
            return {
                "mode": "direct",
                "step": read_step,
            }

        # 4) 刪除檔案
        delete_step = self._match_delete_file(text)
        if delete_step is not None:
            return {
                "mode": "direct",
                "step": delete_step,
            }

        # 5) task mode
        if self._looks_like_task_request(lowered):
            return {
                "mode": "task",
                "task": True,
            }

        # 6) 其餘一律 llm
        return {"mode": "llm"}

    def _match_write_file(self, text: str) -> Optional[Dict]:
        patterns = [
            r"^寫一個\s+([^\s]+)\s+內容是\s+(.+)$",
            r"^寫一個\s+([^\s]+)\s*，\s*內容是\s+(.+)$",
            r"^建立一個\s+([^\s]+)\s+內容是\s+(.+)$",
            r"^建立一個\s+([^\s]+)\s*，\s*內容是\s+(.+)$",
            r"^建立\s+([^\s]+)\s+內容是\s+(.+)$",
            r"^建立\s+([^\s]+)\s*，\s*內容是\s+(.+)$",
            r"^寫\s+([^\s]+)\s+內容是\s+(.+)$",
            r"^寫\s+([^\s]+)\s*，\s*內容是\s+(.+)$",
        ]

        for pattern in patterns:
            match = re.match(pattern, text)
            if match:
                path = match.group(1).strip()
                content = match.group(2).strip()
                if path:
                    return {
                        "type": "write_file",
                        "path": path,
                        "content": content,
                    }

        return None

    def _match_read_file(self, text: str) -> Optional[Dict]:
        prefixes = [
            "再讀取",
            "讀取",
            "讀一下",
            "讀",
            "查看",
            "看一下",
            "看",
        ]

        for prefix in prefixes:
            if text.startswith(prefix):
                path = text[len(prefix):].strip()
                if path:
                    return {
                        "type": "read_file",
                        "path": path,
                    }

        return None

    def _match_delete_file(self, text: str) -> Optional[Dict]:
        lowered = text.lower()

        zh_prefixes = [
            "刪掉",
            "刪除",
            "移除",
        ]

        en_prefixes = [
            "del ",
            "delete ",
        ]

        for prefix in zh_prefixes:
            if text.startswith(prefix):
                path = text[len(prefix):].strip()
                if path:
                    return {
                        "type": "command",
                        "command": f"del {path}",
                    }

        for prefix in en_prefixes:
            if lowered.startswith(prefix):
                path = text[len(prefix):].strip()
                if path:
                    return {
                        "type": "command",
                        "command": f"del {path}",
                    }

        return None

    def _looks_like_task_request(self, lowered: str) -> bool:
        task_keywords = [
            "建立任務",
            "新增任務",
            "排程",
            "加入佇列",
            "背景執行",
            "長任務",
            "繼續任務",
            "繼續上一個任務",
            "繼續剛剛的任務",
            "task ",
            "task:",
            "schedule",
            "queue",
            "background",
            "resume task",
            "continue task",
        ]
        return any(keyword in lowered for keyword in task_keywords)


class Router(SimpleRouter):
    pass