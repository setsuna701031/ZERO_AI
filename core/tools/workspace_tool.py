from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from core.tasks.task_paths import TaskPathManager


class WorkspaceTool:
    name = "workspace"
    description = "Read and write files in workspace."

    def __init__(
        self,
        workspace_root: Path | str = "workspace",
        workspace_dir: Path | str | None = None,
        **_: Any,
    ):
        base = workspace_dir if workspace_dir is not None else workspace_root
        self.workspace_root = Path(base).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.path_manager = TaskPathManager(str(self.workspace_root))

    def execute(self, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = args if isinstance(args, dict) else {}
        return self.run(payload)

    def run(self, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = args if isinstance(args, dict) else {}

        action = str(payload.get("action") or "").strip().lower()
        path = payload.get("path")
        content = payload.get("content")
        recursive = bool(payload.get("recursive", True))
        task_id = payload.get("task_id")

        if not action:
            return self._error_result(
                action="",
                path=str(path or ""),
                error_type="missing_action",
                message="action is required",
                retryable=False,
            )

        if action in {"read", "read_file"}:
            return self._read_file(path, task_id)

        if action in {"write", "write_file", "write_text", "save_file"}:
            return self._write_file(path, content, task_id)

        if action in {"append", "append_file"}:
            return self._append_file(path, content, task_id)

        if action in {"mkdir", "make_dir", "make_directory", "create_dir", "create_directory"}:
            return self._mkdir(path, task_id)

        if action in {"list", "list_files"}:
            return self._list_files(path, recursive=recursive, task_id=task_id)

        if action == "exists":
            return self._exists(path, task_id)

        return self._error_result(
            action=action,
            path=str(path or ""),
            error_type="unsupported_action",
            message=f"unknown action: {action}",
            retryable=False,
        )

    def invoke(self, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.run(args)

    # ============================================================
    # read
    # ============================================================

    def _read_file(self, path: Any, task_id: str | None) -> Dict[str, Any]:
        try:
            full_path = self.path_manager.resolve_read_path(
                str(path),
                task_id=task_id,
            )
            file_path = Path(full_path)
        except Exception as exc:
            return self._error_result(
                action="read_file",
                path=str(path or ""),
                error_type="invalid_path",
                message=str(exc),
                retryable=False,
            )

        if not file_path.exists():
            return self._error_result(
                action="read_file",
                path=str(file_path),
                error_type="file_not_found",
                message=f"file not found: {file_path}",
                retryable=False,
            )

        if not file_path.is_file():
            return self._error_result(
                action="read_file",
                path=str(file_path),
                error_type="not_a_file",
                message=f"not a file: {file_path}",
                retryable=False,
            )

        try:
            text = file_path.read_text(encoding="utf-8")
            return self._success_result(
                action="read_file",
                path=file_path,
                summary="read file",
                results=[
                    {
                        "path": str(file_path),
                        "relative_path": self._relative_path(file_path),
                        "content": text,
                    }
                ],
                changed_files=[],
                extra={
                    "content": text,
                },
            )
        except Exception as exc:
            return self._error_result(
                action="read_file",
                path=str(file_path),
                error_type=exc.__class__.__name__,
                message=str(exc),
                retryable=False,
            )

    # ============================================================
    # write
    # ============================================================

    def _write_file(self, path: Any, content: Any, task_id: str | None) -> Dict[str, Any]:
        try:
            full_path = self.path_manager.resolve_write_path(
                str(path),
                task_id=task_id,
            )
            file_path = Path(full_path)
        except Exception as exc:
            return self._error_result(
                action="write_file",
                path=str(path or ""),
                error_type="invalid_path",
                message=str(exc),
                retryable=False,
            )

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            text = "" if content is None else str(content)
            file_path.write_text(text, encoding="utf-8")

            return self._success_result(
                action="write_file",
                path=file_path,
                summary="write file",
                results=[
                    {
                        "path": str(file_path),
                        "relative_path": self._relative_path(file_path),
                        "bytes_written": len(text.encode("utf-8")),
                        "chars_written": len(text),
                    }
                ],
                changed_files=[str(file_path)],
                extra={
                    "bytes_written": len(text.encode("utf-8")),
                    "chars_written": len(text),
                },
            )
        except Exception as exc:
            return self._error_result(
                action="write_file",
                path=str(file_path),
                error_type=exc.__class__.__name__,
                message=str(exc),
                retryable=False,
            )

    # ============================================================
    # append
    # ============================================================

    def _append_file(self, path: Any, content: Any, task_id: str | None) -> Dict[str, Any]:
        try:
            full_path = self.path_manager.resolve_write_path(
                str(path),
                task_id=task_id,
            )
            file_path = Path(full_path)
        except Exception as exc:
            return self._error_result(
                action="append_file",
                path=str(path or ""),
                error_type="invalid_path",
                message=str(exc),
                retryable=False,
            )

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            text = "" if content is None else str(content)
            with file_path.open("a", encoding="utf-8") as f:
                f.write(text)

            return self._success_result(
                action="append_file",
                path=file_path,
                summary="append file",
                results=[
                    {
                        "path": str(file_path),
                        "relative_path": self._relative_path(file_path),
                        "bytes_appended": len(text.encode("utf-8")),
                        "chars_appended": len(text),
                    }
                ],
                changed_files=[str(file_path)],
                extra={
                    "bytes_appended": len(text.encode("utf-8")),
                    "chars_appended": len(text),
                },
            )
        except Exception as exc:
            return self._error_result(
                action="append_file",
                path=str(file_path),
                error_type=exc.__class__.__name__,
                message=str(exc),
                retryable=False,
            )

    # ============================================================
    # mkdir
    # ============================================================

    def _mkdir(self, path: Any, task_id: str | None) -> Dict[str, Any]:
        try:
            full_path = self.path_manager.resolve_write_path(
                str(path),
                task_id=task_id,
            )
            dir_path = Path(full_path)
        except Exception as exc:
            return self._error_result(
                action="mkdir",
                path=str(path or ""),
                error_type="invalid_path",
                message=str(exc),
                retryable=False,
            )

        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            return self._success_result(
                action="mkdir",
                path=dir_path,
                summary="mkdir",
                results=[
                    {
                        "path": str(dir_path),
                        "relative_path": self._relative_path(dir_path),
                    }
                ],
                changed_files=[str(dir_path)],
            )
        except Exception as exc:
            return self._error_result(
                action="mkdir",
                path=str(dir_path),
                error_type=exc.__class__.__name__,
                message=str(exc),
                retryable=False,
            )

    # ============================================================
    # list
    # ============================================================

    def _list_files(self, path: Any, recursive: bool, task_id: str | None) -> Dict[str, Any]:
        try:
            full_path = self.path_manager.resolve_read_path(
                str(path or "."),
                task_id=task_id,
            )
            target_path = Path(full_path)
        except Exception as exc:
            return self._error_result(
                action="list_files",
                path=str(path or "."),
                error_type="invalid_path",
                message=str(exc),
                retryable=False,
            )

        if not target_path.exists():
            return self._error_result(
                action="list_files",
                path=str(target_path),
                error_type="path_not_found",
                message=f"path not found: {target_path}",
                retryable=False,
            )

        if not target_path.is_dir():
            return self._error_result(
                action="list_files",
                path=str(target_path),
                error_type="not_a_directory",
                message=f"not a directory: {target_path}",
                retryable=False,
            )

        try:
            items: List[Dict[str, Any]] = []
            iterator = target_path.rglob("*") if recursive else target_path.glob("*")

            for item in iterator:
                items.append(
                    {
                        "path": str(item),
                        "relative_path": self._relative_path(item),
                        "name": item.name,
                        "is_dir": item.is_dir(),
                        "is_file": item.is_file(),
                    }
                )

            items.sort(key=lambda x: x["relative_path"])

            return self._success_result(
                action="list_files",
                path=target_path,
                summary="list files",
                results=items,
                changed_files=[],
                extra={
                    "recursive": recursive,
                    "count": len(items),
                    "items": items,
                },
            )
        except Exception as exc:
            return self._error_result(
                action="list_files",
                path=str(target_path),
                error_type=exc.__class__.__name__,
                message=str(exc),
                retryable=False,
            )

    # ============================================================
    # exists
    # ============================================================

    def _exists(self, path: Any, task_id: str | None) -> Dict[str, Any]:
        try:
            full_path = self.path_manager.resolve_read_path(
                str(path),
                task_id=task_id,
            )
            target_path = Path(full_path)
        except Exception as exc:
            return self._error_result(
                action="exists",
                path=str(path or ""),
                error_type="invalid_path",
                message=str(exc),
                retryable=False,
            )

        exists_result = {
            "path": str(target_path),
            "relative_path": self._relative_path(target_path),
            "exists": target_path.exists(),
            "is_file": target_path.is_file(),
            "is_dir": target_path.is_dir(),
        }

        return self._success_result(
            action="exists",
            path=target_path,
            summary="exists check",
            results=[exists_result],
            changed_files=[],
            extra=exists_result,
        )

    # ============================================================
    # helpers
    # ============================================================

    def _relative_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.workspace_root))
        except Exception:
            return str(path)

    def _success_result(
        self,
        action: str,
        path: Path,
        summary: str,
        results: List[Dict[str, Any]],
        changed_files: List[str],
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        response = {
            "ok": True,
            "tool": self.name,
            "action": action,
            "path": str(path),
            "relative_path": self._relative_path(path),
            "workspace_root": str(self.workspace_root),
            "summary": summary,
            "changed_files": changed_files,
            "evidence": [str(path)],
            "results": results,
            "error": None,
        }
        if extra:
            response.update(extra)
        return response

    def _error_result(
        self,
        action: str,
        path: str,
        error_type: str,
        message: str,
        retryable: bool,
    ) -> Dict[str, Any]:
        return {
            "ok": False,
            "tool": self.name,
            "action": action,
            "path": path,
            "relative_path": "",
            "workspace_root": str(self.workspace_root),
            "summary": "",
            "changed_files": [],
            "evidence": [path] if path else [],
            "results": [],
            "error": {
                "type": error_type,
                "message": message,
                "retryable": retryable,
            },
        }