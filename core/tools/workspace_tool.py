# core/tools/workspace_tool.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


class WorkspaceTool:
    name = "workspace"
    description = "Read and write files in workspace."

    def __init__(self, workspace_root: Path | str):
        self.workspace_root = Path(workspace_root).resolve()

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(args, dict):
            return self._error("args must be dict")

        action = str(args.get("action") or "").strip().lower()
        path = args.get("path")
        content = args.get("content")
        recursive = bool(args.get("recursive", True))

        if not action:
            return self._error("action is required")

        if action in {"read", "read_file"}:
            return self._read_file(path)

        if action in {"write", "write_file", "write_text", "save_file"}:
            return self._write_file(path, content)

        if action in {"append", "append_file"}:
            return self._append_file(path, content)

        if action in {"mkdir", "make_dir", "make_directory", "create_dir", "create_directory"}:
            return self._mkdir(path)

        if action in {"list", "list_files"}:
            return self._list_files(path, recursive=recursive)

        if action == "exists":
            return self._exists(path)

        return self._error(f"unknown action: {action}")

    def _resolve_path(self, path: Any) -> Path:
        if not path:
            raise ValueError("path is empty")

        raw_path = Path(str(path))

        if raw_path.is_absolute():
            candidate = raw_path.resolve()
        else:
            candidate = (self.workspace_root / raw_path).resolve()

        try:
            candidate.relative_to(self.workspace_root)
        except ValueError:
            raise ValueError(f"path escapes workspace: {candidate}")

        return candidate

    def _read_file(self, path: Any) -> Dict[str, Any]:
        try:
            file_path = self._resolve_path(path)
        except Exception as exc:
            return self._error(str(exc))

        if not file_path.exists():
            return self._error(f"file not found: {file_path}")

        if not file_path.is_file():
            return self._error(f"not a file: {file_path}")

        try:
            text = file_path.read_text(encoding="utf-8")
            return {
                "success": True,
                "action": "read_file",
                "path": str(file_path),
                "relative_path": str(file_path.relative_to(self.workspace_root)),
                "content": text,
            }
        except Exception as exc:
            return self._error(str(exc))

    def _write_file(self, path: Any, content: Any) -> Dict[str, Any]:
        try:
            file_path = self._resolve_path(path)
        except Exception as exc:
            return self._error(str(exc))

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            text = "" if content is None else str(content)
            file_path.write_text(text, encoding="utf-8")
            return {
                "success": True,
                "action": "write_file",
                "path": str(file_path),
                "relative_path": str(file_path.relative_to(self.workspace_root)),
                "bytes_written": len(text.encode("utf-8")),
                "chars_written": len(text),
            }
        except Exception as exc:
            return self._error(str(exc))

    def _append_file(self, path: Any, content: Any) -> Dict[str, Any]:
        try:
            file_path = self._resolve_path(path)
        except Exception as exc:
            return self._error(str(exc))

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            text = "" if content is None else str(content)
            with file_path.open("a", encoding="utf-8") as f:
                f.write(text)

            return {
                "success": True,
                "action": "append_file",
                "path": str(file_path),
                "relative_path": str(file_path.relative_to(self.workspace_root)),
                "bytes_appended": len(text.encode("utf-8")),
                "chars_appended": len(text),
            }
        except Exception as exc:
            return self._error(str(exc))

    def _mkdir(self, path: Any) -> Dict[str, Any]:
        try:
            dir_path = self._resolve_path(path)
        except Exception as exc:
            return self._error(str(exc))

        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            return {
                "success": True,
                "action": "mkdir",
                "path": str(dir_path),
                "relative_path": str(dir_path.relative_to(self.workspace_root)),
            }
        except Exception as exc:
            return self._error(str(exc))

    def _list_files(self, path: Any, recursive: bool = True) -> Dict[str, Any]:
        try:
            target_path = self._resolve_path(path or ".")
        except Exception as exc:
            return self._error(str(exc))

        if not target_path.exists():
            return self._error(f"path not found: {target_path}")

        if not target_path.is_dir():
            return self._error(f"not a directory: {target_path}")

        try:
            items: List[Dict[str, Any]] = []

            iterator = target_path.rglob("*") if recursive else target_path.glob("*")

            for item in iterator:
                relative_path = item.relative_to(self.workspace_root)
                items.append(
                    {
                        "path": str(item),
                        "relative_path": str(relative_path),
                        "name": item.name,
                        "is_dir": item.is_dir(),
                        "is_file": item.is_file(),
                    }
                )

            items.sort(key=lambda x: x["relative_path"])

            return {
                "success": True,
                "action": "list_files",
                "path": str(target_path),
                "relative_path": str(target_path.relative_to(self.workspace_root)),
                "recursive": recursive,
                "count": len(items),
                "items": items,
            }
        except Exception as exc:
            return self._error(str(exc))

    def _exists(self, path: Any) -> Dict[str, Any]:
        try:
            target_path = self._resolve_path(path)
        except Exception as exc:
            return self._error(str(exc))

        return {
            "success": True,
            "action": "exists",
            "path": str(target_path),
            "relative_path": str(target_path.relative_to(self.workspace_root)),
            "exists": target_path.exists(),
            "is_file": target_path.is_file(),
            "is_dir": target_path.is_dir(),
        }

    def _error(self, message: str) -> Dict[str, Any]:
        return {
            "success": False,
            "error": message,
        }