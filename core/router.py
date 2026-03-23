from __future__ import annotations

from typing import Any, Dict, List


class Router:
    """
    ZERO Router

    目前先把明確指令直接路由到工具：
    1. cmd: <command>
    2. ws ls [path]
    3. ws read <path>
    4. ws write <path> <content>
    5. ws append <path> <content>
    6. ws mkdir <path>
    7. ws exists <path>

    其他內容先走 chat。
    """

    def route(self, user_input: str) -> Dict[str, Any]:
        if not isinstance(user_input, str):
            return self._chat()

        text = user_input.strip()
        if text == "":
            return self._chat()

        lower = text.lower()

        # ---------------------------------------------------------
        # command_tool
        # ---------------------------------------------------------
        if lower.startswith("cmd:"):
            command = text[4:].strip()
            return self._tool(
                tool_name="command_tool",
                tool_args={
                    "command": command,
                },
            )

        # ---------------------------------------------------------
        # 舊 ws: path 相容：直接讀檔
        # 例如：ws: test.txt
        # ---------------------------------------------------------
        if lower.startswith("ws:"):
            path = text[3:].strip()
            return self._tool(
                tool_name="workspace_tool",
                tool_args={
                    "action": "read_file",
                    "path": path,
                },
            )

        # ---------------------------------------------------------
        # 新 ws 指令
        # ---------------------------------------------------------
        if lower.startswith("ws "):
            parsed = self._parse_ws_command(text)
            if parsed is not None:
                return self._tool(
                    tool_name="workspace_tool",
                    tool_args=parsed,
                )
            return self._chat()

        # ---------------------------------------------------------
        # system commands
        # ---------------------------------------------------------
        if text.startswith("/"):
            return {
                "mode": "system",
                "tool_name": None,
                "tool_args": {
                    "command": text,
                },
            }

        # ---------------------------------------------------------
        # default
        # ---------------------------------------------------------
        return self._chat()

    # =========================================================
    # Helpers
    # =========================================================

    def _tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "mode": "tool",
            "tool_name": tool_name,
            "tool_args": tool_args,
        }

    def _chat(self) -> Dict[str, Any]:
        return {
            "mode": "chat",
            "tool_name": None,
            "tool_args": {},
        }

    def _parse_ws_command(self, text: str) -> Dict[str, Any] | None:
        parts = text.strip().split()
        if len(parts) < 2:
            return None

        # parts[0] == "ws"
        cmd = parts[1].lower()

        # ws ls
        # ws ls some/path
        if cmd == "ls":
            path = parts[2] if len(parts) >= 3 else "."
            return {
                "action": "list_files",
                "path": path,
            }

        # ws read test.txt
        if cmd == "read":
            if len(parts) < 3:
                return None
            return {
                "action": "read_file",
                "path": parts[2],
            }

        # ws write test.txt hello world
        if cmd == "write":
            if len(parts) < 4:
                return None
            return {
                "action": "write_file",
                "path": parts[2],
                "content": " ".join(parts[3:]),
            }

        # ws append test.txt !!!
        if cmd == "append":
            if len(parts) < 4:
                return None
            return {
                "action": "append_file",
                "path": parts[2],
                "content": " ".join(parts[3:]),
            }

        # ws mkdir test
        if cmd == "mkdir":
            if len(parts) < 3:
                return None
            return {
                "action": "make_dir",
                "path": parts[2],
            }

        # ws exists test.txt
        if cmd == "exists":
            if len(parts) < 3:
                return None
            return {
                "action": "exists",
                "path": parts[2],
            }

        return None