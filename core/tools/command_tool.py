from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


class CommandTool:
    name = "command"
    description = "Execute system shell commands."

    def __init__(self, workspace_root: Path | str = "workspace", **_: Any):
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def execute(self, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = args if isinstance(args, dict) else {}

        command_text = self._extract_command(payload)
        if not command_text:
            return self._error_result(
                command="",
                error_type="invalid_input",
                message="command empty",
                retryable=False,
            )

        timeout = self._extract_timeout(payload, default=20)

        try:
            result = subprocess.run(
                command_text,
                shell=True,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            return {
                "ok": result.returncode == 0,
                "tool": self.name,
                "command": command_text,
                "cwd": str(self.workspace_root),
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "timed_out": False,
                "error": None if result.returncode == 0 else {
                    "type": "command_failed",
                    "message": f"command exited with return code {result.returncode}",
                    "retryable": False,
                },
            }

        except subprocess.TimeoutExpired as exc:
            return {
                "ok": False,
                "tool": self.name,
                "command": command_text,
                "cwd": str(self.workspace_root),
                "returncode": None,
                "stdout": exc.stdout if isinstance(exc.stdout, str) else "",
                "stderr": exc.stderr if isinstance(exc.stderr, str) else "",
                "timed_out": True,
                "error": {
                    "type": "timeout",
                    "message": f"command timeout after {timeout}s",
                    "retryable": True,
                },
            }

        except Exception as exc:
            return self._error_result(
                command=command_text,
                error_type=exc.__class__.__name__,
                message=str(exc),
                retryable=False,
            )

    def run(self, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.execute(args)

    def invoke(self, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.execute(args)

    def _extract_command(self, args: Dict[str, Any]) -> str:
        command_text = (
            args.get("command")
            or args.get("command_text")
            or args.get("cmd")
            or args.get("text")
        )
        return str(command_text or "").strip()

    def _extract_timeout(self, args: Dict[str, Any], default: int = 20) -> int:
        raw_timeout = args.get("timeout", default)
        try:
            timeout = int(raw_timeout)
        except (TypeError, ValueError):
            return default
        return timeout if timeout > 0 else default

    def _error_result(
        self,
        command: str,
        error_type: str,
        message: str,
        retryable: bool,
    ) -> Dict[str, Any]:
        return {
            "ok": False,
            "tool": self.name,
            "command": command,
            "cwd": str(self.workspace_root),
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "error": {
                "type": error_type,
                "message": message,
                "retryable": retryable,
            },
        }