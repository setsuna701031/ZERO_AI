from __future__ import annotations

from core.runtime.execution_gateway import safe_subprocess_run
from tools.base_tool import BaseTool


class RunShellTool(BaseTool):
    name = "run_shell"
    description = "Archived shell helper routed through canonical executor."

    def run(self, args: dict) -> str:
        command = str(args.get("command", "")).strip()
        if not command:
            return "shell command is required"

        allowed_prefixes = ("pip ", "python ", "py ", "mkdir ", "dir", "type ", "echo ")
        if not any(command.lower().startswith(prefix) for prefix in allowed_prefixes):
            return f"shell command blocked: {command}"

        result = safe_subprocess_run(
            command,
            shell=bool(True),
            capture_output=True,
            text=True,
            timeout=30,
        )
        stdout = str(result.get("stdout") or "").strip()
        stderr = str(result.get("stderr") or "").strip()
        if result.get("returncode") == 0:
            return stdout or "shell command completed"
        return stderr or stdout or f"shell command failed: {result.get('returncode')}"
