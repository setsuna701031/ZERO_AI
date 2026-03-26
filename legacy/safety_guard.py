from __future__ import annotations

from typing import Any, Dict, List


class SafetyGuard:
    """
    ZERO 安全守門層

    目前版本先做規則式安全檢查。
    用途：
    1. 在工具執行前先檢查是否允許
    2. 根據 mode 限制工具能力
    3. 為未來 execute/file/git/shell 等高風險工具預留入口
    """

    def __init__(self) -> None:
        self.read_only_modes = {"explore", "plan"}

        self.write_like_actions = {
            ("memory", "write"),
        }

        self.blocked_tool_names_in_read_only = {
            "execute",
            "shell",
            "file_write",
            "git",
        }

    def check_tool_call(
        self,
        mode: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        mode = (mode or "chat").strip().lower()
        tool_name = (tool_name or "").strip()

        if not tool_name:
            return {
                "ok": False,
                "error": "empty_tool_name",
                "details": ["tool_name cannot be empty"],
            }

        if mode in self.read_only_modes:
            if tool_name in self.blocked_tool_names_in_read_only:
                return {
                    "ok": False,
                    "error": "tool_blocked_in_read_only_mode",
                    "details": [f"tool '{tool_name}' is blocked in mode '{mode}'"],
                }

            action = str(arguments.get("action", "")).strip().lower()
            if (tool_name, action) in self.write_like_actions:
                return {
                    "ok": False,
                    "error": "write_action_blocked_in_read_only_mode",
                    "details": [f"action '{action}' of tool '{tool_name}' is blocked in mode '{mode}'"],
                }

        return {
            "ok": True
        }