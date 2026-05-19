import os
import platform
from typing import Any, Dict

from core.runtime.execution_gateway import safe_subprocess_run


class TerminalTool:
    name = "terminal"

    def run(self, command: str, cwd: str | None = None, timeout: int = 60) -> Dict[str, Any]:
        if not command or not command.strip():
            return {"ok": False, "tool": self.name, "error": "Empty command"}

        working_dir = cwd if cwd and os.path.isdir(cwd) else os.getcwd()
        is_windows = platform.system().lower().startswith("win")
        result = safe_subprocess_run(
            command,
            cwd=working_dir,
            shell=bool(True),
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "ok": result.get("returncode") == 0,
            "tool": self.name,
            "command": command,
            "cwd": working_dir,
            "returncode": result.get("returncode"),
            "stdout": str(result.get("stdout") or "")[-12000:],
            "stderr": str(result.get("stderr") or "")[-12000:],
            "platform": "windows" if is_windows else "other",
            "error": result.get("error"),
        }
