from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


class WorkspaceTool:
    name = "workspace_tool"
    description = "Read and write files in workspace."

    def __init__(self, workspace_root: Path | str):
        self.workspace_root = Path(workspace_root)

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        支援：
        {
            "action": "read_file",
            "path": "test.txt"
        }
        """
        if not isinstance(args, dict):
            return {
                "success": False,
                "error": "args must be dict",
            }

        action = args.get("action")
        path = args.get("path")
        content = args.get("content")

        if not action:
            return {
                "success": False,
                "error": "action is required",
            }

        if action == "read_file":
            return self._read_file(path)

        if action == "write_file":
            return self._write_file(path, content)

        return {
            "success": False,
            "error": f"unknown action: {action}",
        }

    def _read_file(self, path: Any) -> Dict[str, Any]:
        if not path:
            return {
                "success": False,
                "error": "path is empty",
            }

        file_path = self.workspace_root / str(path)

        if not file_path.exists():
            return {
                "success": False,
                "error": f"file not found: {file_path}",
            }

        try:
            text = file_path.read_text(encoding="utf-8")
            return {
                "success": True,
                "path": str(file_path),
                "content": text,
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

    def _write_file(self, path: Any, content: Any) -> Dict[str, Any]:
        if not path:
            return {
                "success": False,
                "error": "path is empty",
            }

        file_path = self.workspace_root / str(path)

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(str(content or ""), encoding="utf-8")
            return {
                "success": True,
                "path": str(file_path),
            }
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }