from __future__ import annotations

import re
from typing import Dict, Optional, List


class SimpleRouter:
    """
    ZERO Router（收束版）

    只回三種 mode：
    - direct: 明確單一步驟可直接執行
    - task:   長任務 / 排程 / 佇列
    - llm:    其餘自然語言交給 llm_planner / planner

    設計原則：
    1. 明確單一步驟才走 direct
    2. 多子句、多步、含「然後 / 再 / 接著」的自然語句，不走 direct
    3. 避免 router 抢走本來該交給 planner / llm_planner 的工作
    """

    _POLITE_PREFIXES: List[str] = [
        "幫我",
        "請",
        "請幫我",
        "麻煩你",
        "麻煩幫我",
        "可以幫我",
        "可不可以幫我",
        "請你",
    ]

    def route(self, user_input: str, context: Optional[Dict] = None) -> Dict:
        text = str(user_input or "").strip()
        lowered = text.lower()

        if not text:
            return {"mode": "llm"}

        normalized_text = self._strip_polite_prefix(text)
        normalized_lowered = normalized_text.lower()

        # 0) 多步自然語句：直接交給 planner / llm_planner
        if self._looks_like_multi_step(normalized_text):
            return {"mode": "llm"}

        # 1) 明確 command 前綴
        if normalized_lowered.startswith("command:"):
            cmd = normalized_text[len("command:"):].strip()
            if cmd:
                return {
                    "mode": "direct",
                    "step": {
                        "type": "command",
                        "command": cmd,
                    },
                }

        # 2) 明確單步寫檔
        write_step = self._match_write_file(normalized_text)
        if write_step is not None:
            return {
                "mode": "direct",
                "step": write_step,
            }

        # 3) 明確單步讀檔
        read_step = self._match_read_file(normalized_text)
        if read_step is not None:
            return {
                "mode": "direct",
                "step": read_step,
            }

        # 4) 明確單步刪除檔案
        delete_step = self._match_delete_file(normalized_text)
        if delete_step is not None:
            return {
                "mode": "direct",
                "step": delete_step,
            }

        # 5) task mode
        if self._looks_like_task_request(normalized_lowered):
            return {
                "mode": "task",
                "task": True,
            }

        # 6) 其餘一律 llm
        return {"mode": "llm"}

    def _strip_polite_prefix(self, text: str) -> str:
        value = str(text or "").strip()

        changed = True
        while changed:
            changed = False
            for prefix in self._POLITE_PREFIXES:
                if value.startswith(prefix):
                    value = value[len(prefix):].strip()
                    changed = True

        return value

    def _looks_like_multi_step(self, text: str) -> bool:
        value = str(text or "").strip().lower()

        multi_markers = [
            "然後",
            "接著",
            "之後",
            "再來",
            "再 ",
            "再讀",
            "再看",
            "再打開",
            "and then",
            "then ",
        ]

        punctuation_split = any(token in value for token in ["，", ",", "。", ";", "；"])
        marker_split = any(marker in value for marker in multi_markers)

        return punctuation_split or marker_split

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
            r"^新增\s+([^\s]+)\s+內容是\s+(.+)$",
            r"^新增\s+([^\s]+)\s*，\s*內容是\s+(.+)$",
            r"^create\s+([^\s]+)\s+with\s+content\s+(.+)$",
            r"^write\s+([^\s]+)\s+with\s+content\s+(.+)$",
        ]

        for pattern in patterns:
            match = re.match(pattern, text, flags=re.IGNORECASE)
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
            "打開",
            "open ",
            "read ",
            "show ",
        ]

        for prefix in prefixes:
            if text.lower().startswith(prefix.lower()):
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