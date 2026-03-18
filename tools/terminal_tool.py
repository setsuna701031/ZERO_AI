import os
import subprocess
import platform
from typing import Dict, Any


class TerminalTool:
    name = "terminal"

    def run(self, command: str, cwd: str | None = None, timeout: int = 60) -> Dict[str, Any]:
        if not command or not command.strip():
            return {
                "ok": False,
                "tool": self.name,
                "error": "Empty command"
            }

        working_dir = cwd if cwd and os.path.isdir(cwd) else os.getcwd()
        is_windows = platform.system().lower().startswith("win")

        try:
            completed = subprocess.run(
                command,
                cwd=working_dir,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace"
            )

            return {
                "ok": completed.returncode == 0,
                "tool": self.name,
                "command": command,
                "cwd": working_dir,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-12000:],
                "stderr": completed.stderr[-12000:],
                "platform": "windows" if is_windows else "other"
            }

        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "tool": self.name,
                "command": command,
                "cwd": working_dir,
                "error": f"Command timed out after {timeout} seconds"
            }
        except Exception as e:
            return {
                "ok": False,
                "tool": self.name,
                "command": command,
                "cwd": working_dir,
                "error": f"{type(e).__name__}: {e}"
            }