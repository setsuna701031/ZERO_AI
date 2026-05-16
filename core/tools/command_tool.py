from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.runtime.execution_gateway import safe_subprocess_run


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

        gateway_result = safe_subprocess_run(
            command_text,
            shell=True,
            cwd=str(self.workspace_root),
            timeout=float(timeout),
        )

        timed_out = bool(
            gateway_result.get("returncode") is None
            and gateway_result.get("error")
            and "timeout" in str(gateway_result.get("error")).lower()
        )

        return {
            "ok": gateway_result["ok"],
            "tool": self.name,
            "command": command_text,
            "cwd": str(self.workspace_root),
            "returncode": gateway_result["returncode"],
            "stdout": gateway_result["stdout"],
            "stderr": gateway_result["stderr"],
            "timed_out": timed_out,
            "execution_gateway": {
                "used": True,
                "shell": gateway_result["shell"],
                "timeout": gateway_result["timeout"],
                "error": gateway_result["error"],
            },
            "error": self._build_error(gateway_result, timeout, timed_out),
        }

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

    def _build_error(
        self,
        gateway_result: Dict[str, Any],
        timeout: int,
        timed_out: bool,
    ) -> Dict[str, Any] | None:
        if gateway_result.get("ok") is True:
            return None

        if timed_out:
            return {
                "type": "timeout",
                "message": f"command timeout after {timeout}s",
                "retryable": True,
            }

        gateway_error = gateway_result.get("error")
        if gateway_error:
            return {
                "type": "execution_gateway_error",
                "message": str(gateway_error),
                "retryable": False,
            }

        returncode = gateway_result.get("returncode")
        return {
            "type": "command_failed",
            "message": f"command exited with return code {returncode}",
            "retryable": False,
        }

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
            "execution_gateway": {
                "used": False,
                "shell": None,
                "timeout": None,
                "error": None,
            },
            "error": {
                "type": error_type,
                "message": message,
                "retryable": retryable,
            },
        }