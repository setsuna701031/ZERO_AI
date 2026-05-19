from __future__ import annotations

from pathlib import Path

from core.runtime.execution_gateway import safe_subprocess_run
from tools.base_tool import BaseTool


class DebugPythonTool(BaseTool):
    name = "debug_python"
    description = "Archived Python debug helper routed through canonical executor."

    def run(self, args: dict) -> dict:
        path = str(args.get("path", "")).strip()
        if not path:
            return {"success": False, "output": "python path is required"}

        file_path = Path(path)
        if not file_path.exists():
            return {"success": False, "output": f"file not found: {path}"}
        if not file_path.is_file():
            return {"success": False, "output": f"not a file: {path}"}
        if file_path.name.lower() == "main.py":
            return {"success": False, "output": "debug_python does not run main.py"}

        result = safe_subprocess_run(
            ["python", str(file_path)],
            cwd=str(file_path.parent) if str(file_path.parent) else None,
            capture_output=True,
            text=True,
            timeout=15,
        )
        stdout = str(result.get("stdout") or "").strip()
        stderr = str(result.get("stderr") or "").strip()
        if result.get("returncode") == 0:
            return {"success": True, "output": stdout or "program executed with no output"}
        return {"success": False, "output": stderr or stdout or "python execution failed"}
