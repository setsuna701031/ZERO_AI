from __future__ import annotations

from pathlib import Path

from config import PYTHON_EXEC_TIMEOUT
from tools.base_tool import BaseTool
from utils.file_utils import resolve_user_path
from utils.safe_exec import ensure_run_allowed, run_python_file


class RunPythonTool(BaseTool):
    name = "run_python"
    description = "執行 Python 檔案"

    def run(self, args: dict) -> str:
        path = resolve_user_path(args.get("path", ""))
        if not path.exists() or not path.is_file():
            return f"Python 檔案不存在: {path}"
        ensure_run_allowed(path)
        return run_python_file(path, timeout=PYTHON_EXEC_TIMEOUT)