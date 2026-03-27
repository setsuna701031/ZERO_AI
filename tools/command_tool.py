from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict


class CommandTool:
    name = "command_tool"
    description = "Execute system shell commands."

    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        支援多種參數名稱：
        - command
        - command_text
        - cmd
        - text
        """

        if not isinstance(args, dict):
            return {
                "success": False,
                "error": "args must be a dict.",
            }

        command_text = (
            args.get("command")
            or args.get("command_text")
            or args.get("cmd")
            or args.get("text")
        )

        if not command_text or not str(command_text).strip():
            return {
                "success": False,
                "error": "command_text is empty.",
            }

        command_text = str(command_text).strip()

        try:
            result = subprocess.run(
                command_text,
                shell=True,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
            )

            return {
                "success": result.returncode == 0,
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": command_text,
            }

        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "command": command_text,
            }