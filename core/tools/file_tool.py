from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from core.system.path_manager import PathManager
from core.tools.base_tool import BaseTool


class FileTool(BaseTool):
    name = "file"
    description = "Read, write, append files safely inside workspace."

    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string"},
            "path": {"type": "string"},
            "content": {},
        },
        "required": ["action", "path"],
    }

    def __init__(
        self,
        workspace_root: Optional[str] = None,
        workspace_dir: Optional[str] = None,
        encoding: str = "utf-8",
        path_manager: Optional[PathManager] = None,
        **_: Any,
    ) -> None:
        base_dir = workspace_root or workspace_dir

        if path_manager is not None:
            self.path_manager = path_manager
        else:
            self.path_manager = PathManager(base_dir=base_dir)

        self.workspace_root: Path = self.path_manager.workspace_root
        self.encoding = encoding
        self.backup_root = self.path_manager.to_workspace_path("data/backups")

    def execute(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        arguments = payload if isinstance(payload, dict) else {}
        return self.run(arguments)

    def run(self, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = arguments if isinstance(arguments, dict) else {}

        action = str(args.get("action", "")).strip().lower()
        raw_path = str(args.get("path", "")).strip()
        content = args.get("content", "")

        if action == "":
            return self._error_result(
                error_type="missing_action",
                message="action is required",
                path=raw_path,
                retryable=False,
            )

        if raw_path == "":
            return self._error_result(
                error_type="empty_path",
                message="path is required",
                path=raw_path,
                retryable=False,
            )

        try:
            target_path = self._resolve_safe_path(raw_path)
        except Exception as exc:
            return self._error_result(
                error_type="invalid_path",
                message=str(exc),
                path=raw_path,
                retryable=False,
                details=[str(exc)],
            )

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

        return self._error_result(
            error_type="unsupported_action",
            message=f"unsupported action: {action}",
            path=str(target_path),
            retryable=False,
            details=[action],
        )

    def invoke(self, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.run(arguments)

    def _resolve_safe_path(self, raw_path: str) -> Path:
        return self.path_manager.to_workspace_path(raw_path)

    def _read(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return self._error_result(
                error_type="file_not_found",
                message="file not found",
                path=str(path),
                retryable=False,
                details=[str(path)],
            )

        if path.is_dir():
            return self._error_result(
                error_type="path_is_directory",
                message="path is a directory",
                path=str(path),
                retryable=False,
                details=[str(path)],
            )

        text = path.read_text(encoding=self.encoding)
        return self._success_result(
            summary="read file",
            path=path,
            changed_files=[],
            evidence=[str(path)],
            results=[
                {
                    "path": str(path),
                    "content": text,
                }
            ],
        )

    def _write(self, path: Path, content: Any) -> Dict[str, Any]:
        if path.exists():
            return self._error_result(
                error_type="file_exists",
                message="file already exists",
                path=str(path),
                retryable=False,
                details=[str(path)],
            )

        if path.suffix == "" and not self._looks_like_file_path(path):
            return self._error_result(
                error_type="target_looks_like_directory",
                message="target path looks like a directory",
                path=str(path),
                retryable=False,
                details=[str(path)],
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content), encoding=self.encoding)

        return self._success_result(
            summary="write file",
            path=path,
            changed_files=[str(path)],
            evidence=[str(path)],
            results=[
                {
                    "path": str(path),
                }
            ],
        )

    def _overwrite(self, path: Path, content: Any) -> Dict[str, Any]:
        if path.exists() and path.is_dir():
            return self._error_result(
                error_type="path_is_directory",
                message="path is a directory",
                path=str(path),
                retryable=False,
                details=[str(path)],
            )

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content), encoding=self.encoding)

        return self._success_result(
            summary="overwrite file",
            path=path,
            changed_files=[str(path)],
            evidence=[str(path)],
            results=[
                {
                    "path": str(path),
                }
            ],
        )

    def _append(self, path: Path, content: Any) -> Dict[str, Any]:
        if path.exists() and path.is_dir():
            return self._error_result(
                error_type="path_is_directory",
                message="path is a directory",
                path=str(path),
                retryable=False,
                details=[str(path)],
            )

        path.parent.mkdir(parents=True, exist_ok=True)

        old = ""
        if path.exists():
            old = path.read_text(encoding=self.encoding)

        new = old + str(content)
        path.write_text(new, encoding=self.encoding)

        return self._success_result(
            summary="append file",
            path=path,
            changed_files=[str(path)],
            evidence=[str(path)],
            results=[
                {
                    "path": str(path),
                }
            ],
        )

    def _exists(self, path: Path) -> Dict[str, Any]:
        return self._success_result(
            summary="exists check",
            path=path,
            changed_files=[],
            evidence=[str(path)],
            results=[
                {
                    "path": str(path),
                    "exists": path.exists(),
                    "is_file": path.is_file(),
                    "is_dir": path.is_dir(),
                }
            ],
        )

    def _mkdir(self, path: Path) -> Dict[str, Any]:
        path.mkdir(parents=True, exist_ok=True)
        return self._success_result(
            summary="mkdir",
            path=path,
            changed_files=[str(path)],
            evidence=[str(path)],
            results=[
                {
                    "path": str(path),
                }
            ],
        )

    def _looks_like_file_path(self, path: Path) -> bool:
        return path.name != "" and "." in path.name

    def _success_result(
        self,
        summary: str,
        path: Path,
        changed_files: List[str],
        evidence: List[str],
        results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "ok": True,
            "tool": self.name,
            "path": str(path),
            "workspace_root": str(self.workspace_root),
            "summary": summary,
            "changed_files": changed_files,
            "evidence": evidence,
            "results": results,
            "error": None,
        }

    def _error_result(
        self,
        error_type: str,
        message: str,
        path: str,
        retryable: bool,
        details: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return {
            "ok": False,
            "tool": self.name,
            "path": path,
            "workspace_root": str(self.workspace_root),
            "summary": "",
            "changed_files": [],
            "evidence": details or ([] if not path else [path]),
            "results": [],
            "error": {
                "type": error_type,
                "message": message,
                "retryable": retryable,
                "details": details or [],
            },
        }