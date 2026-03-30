from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.path_manager import PathManager
from tools.base_tool import BaseTool


class FileTool(BaseTool):
    name = "file"
    description = "Read, write, append files safely inside workspace."

    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "path": {"type": "string"},
            "content": {}
        },
        "required": ["action", "path"]
    }

    def __init__(
        self,
        workspace_root: Optional[str] = None,
        encoding: str = "utf-8",
        path_manager: Optional[PathManager] = None,
    ) -> None:
        """
        相容兩種初始化方式：

        1. 新版（推薦）
           FileTool(path_manager=path_manager)

        2. 舊版（相容）
           FileTool(workspace_root="E:/zero_ai/workspace")

        規則：
        - 若有傳 path_manager，優先使用
        - 若沒有 path_manager，才從 workspace_root 建立 PathManager
        """
        if path_manager is not None:
            self.path_manager = path_manager
        else:
            self.path_manager = PathManager(base_dir=workspace_root)

        self.workspace_root: Path = self.path_manager.workspace_root
        self.encoding = encoding
        self.backup_root = self.path_manager.to_workspace_path("data/backups")

    # =========================
    # Main Execute
    # =========================

    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        arguments = {
            "action": payload.get("action", ""),
            "path": payload.get("path", ""),
            "content": payload.get("content", ""),
        }
        return self.run(arguments)

    def run(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        action = str(arguments.get("action", "")).strip().lower()
        raw_path = str(arguments.get("path", "")).strip()
        content = arguments.get("content", "")

        if action == "":
            return self._error("missing_action")

        if raw_path == "":
            return self._error("empty_path")

        try:
            target_path = self._resolve_safe_path(raw_path)
        except Exception as exc:
            return self._error("invalid_path", [str(exc)])

        if action == "read":
            return self._read(target_path)

        if action == "write":
            return self._write(target_path, content)

        if action == "overwrite":
            return self._overwrite(target_path, content)

        if action == "append":
            return self._append(target_path, content)

        if action == "exists":
            return self._exists(target_path)

        if action == "mkdir":
            return self._mkdir(target_path)

        return self._error("unsupported_action", [action])

    # =========================
    # Path Resolve
    # =========================

    def _resolve_safe_path(self, raw_path: str) -> Path:
        """
        所有 workspace 路徑解析統一交給 PathManager。

        可接受：
        - e.txt
        - workspace/e.txt
        - /workspace/e.txt
        - workspace\\workspace\\e.txt
        - task_0001/plan.txt

        最後都會被清洗並限制在 workspace 內。
        """
        return self.path_manager.to_workspace_path(raw_path)

    # =========================
    # File Operations
    # =========================

    def _read(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return self._error("file_not_found", [str(path)])

        if path.is_dir():
            return self._error("path_is_directory", [str(path)])

        text = path.read_text(encoding=self.encoding)
        return self._success(
            summary="read file",
            changed_files=[],
            evidence=[str(path)],
            results=[{
                "path": str(path),
                "content": text,
            }]
        )

    def _write(self, path: Path, content: Any) -> Dict[str, Any]:
        if path.exists():
            return self._error("file_exists", [str(path)])

        if path.suffix == "" and not self._looks_like_file_path(path):
            return self._error("target_looks_like_directory", [str(path)])

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content), encoding=self.encoding)

        return self._success(
            summary="write file",
            changed_files=[str(path)],
            evidence=[str(path)],
            results=[{
                "path": str(path),
            }]
        )

    def _overwrite(self, path: Path, content: Any) -> Dict[str, Any]:
        if path.exists() and path.is_dir():
            return self._error("path_is_directory", [str(path)])

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content), encoding=self.encoding)

        return self._success(
            summary="overwrite file",
            changed_files=[str(path)],
            evidence=[str(path)],
            results=[{
                "path": str(path),
            }]
        )

    def _append(self, path: Path, content: Any) -> Dict[str, Any]:
        if path.exists() and path.is_dir():
            return self._error("path_is_directory", [str(path)])

        path.parent.mkdir(parents=True, exist_ok=True)

        old = ""
        if path.exists():
            old = path.read_text(encoding=self.encoding)

        new = old + str(content)
        path.write_text(new, encoding=self.encoding)

        return self._success(
            summary="append file",
            changed_files=[str(path)],
            evidence=[str(path)],
            results=[{
                "path": str(path),
            }]
        )

    def _exists(self, path: Path) -> Dict[str, Any]:
        return self._success(
            summary="exists check",
            changed_files=[],
            evidence=[str(path)],
            results=[{
                "path": str(path),
                "exists": path.exists(),
                "is_file": path.is_file(),
                "is_dir": path.is_dir(),
            }]
        )

    def _mkdir(self, path: Path) -> Dict[str, Any]:
        path.mkdir(parents=True, exist_ok=True)
        return self._success(
            summary="mkdir",
            changed_files=[str(path)],
            evidence=[str(path)],
            results=[{
                "path": str(path),
            }]
        )

    # =========================
    # Helpers
    # =========================

    def _looks_like_file_path(self, path: Path) -> bool:
        """
        粗略判斷路徑看起來像不像檔案。
        例如：
        - a.txt -> True
        - src/main.py -> True
        - folder -> False
        """
        return path.name != "" and "." in path.name

    def _success(
        self,
        summary: str,
        changed_files: list,
        evidence: list,
        results: list
    ) -> Dict[str, Any]:
        return {
            "ok": True,
            "tool_name": self.name,
            "summary": summary,
            "changed_files": changed_files,
            "evidence": evidence,
            "results": results,
        }

    def _error(self, error: str, details: Optional[list] = None) -> Dict[str, Any]:
        return {
            "ok": False,
            "tool_name": self.name,
            "error": error,
            "details": details or [],
        }