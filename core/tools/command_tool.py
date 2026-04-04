from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict


class CommandTool:
    name = "command_tool"
    description = "Execute system shell commands."

    def __init__(self, workspace_root: Path | str):
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(args, dict):
            return {
                "ok": False,
                "error": "args must be dict",
            }

        command_text = (
            args.get("command")
            or args.get("command_text")
            or args.get("cmd")
            or args.get("text")
        )

        if not command_text:
            return {
                "ok": False,
                "error": "command empty",
            }

        command_text = str(command_text).strip()

        timeout = int(args.get("timeout", 20))

        try:
            result = subprocess.run(
                command_text,
                shell=True,
                cwd=str(self.workspace_root),   # ★★★ 關鍵
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            return {
                "ok": result.returncode == 0,
                "tool": "command_tool",
                "command": command_text,
                "cwd": str(self.workspace_root),
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "error": "command timeout",
                "command": command_text,
            }

        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "command": command_text,
            }