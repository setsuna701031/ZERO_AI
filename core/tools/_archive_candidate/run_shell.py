from __future__ import annotations

import subprocess

from tools.base_tool import BaseTool


class RunShellTool(BaseTool):
    name = "run_shell"
    description = "執行受限 shell 指令"

    def run(self, args: dict) -> str:
        command = str(args.get("command", "")).strip()

        if not command:
            return "沒有提供 shell 指令"

        allowed_prefixes = [
            "pip ",
            "python ",
            "py ",
            "mkdir ",
            "dir",
            "type ",
            "echo ",
        ]

        if not any(command.lower().startswith(prefix) for prefix in allowed_prefixes):
            return f"拒絕執行未授權 shell 指令: {command}"

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )

            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()

            if result.returncode == 0:
                return stdout or "shell 指令執行成功"

            return stderr or stdout or f"shell 指令執行失敗，返回碼: {result.returncode}"

        except subprocess.TimeoutExpired:
            return f"shell 指令執行逾時: {command}"
        except Exception as e:
            return f"shell 指令執行失敗: {e}"