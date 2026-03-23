from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional


class WorkspaceTool:
    name = "workspace_tool"
    description = "Safe file operations inside the workspace directory."

    def __init__(self, workspace_root: Path | str) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def execute(self, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = payload or {}

        if not isinstance(payload, dict):
            raise ValueError("payload must be a dict.")

        action = payload.get("action", "")
        kwargs = dict(payload)
        kwargs.pop("action", None)

        return self.run(action=action, **kwargs)

    def run(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        action = (action or "").strip().lower()

        if not action:
            raise ValueError("action is required.")

        if action == "list_files":
            return self._list_files(
                path=kwargs.get("path", "."),
                recursive=bool(kwargs.get("recursive", False)),
            )

        if action == "read_file":
            return self._read_file(
                path=kwargs["path"],
                encoding=kwargs.get("encoding", "utf-8"),
            )

        if action == "write_file":
            return self._write_file(
                path=kwargs["path"],
                content=kwargs.get("content", ""),
                encoding=kwargs.get("encoding", "utf-8"),
                overwrite=bool(kwargs.get("overwrite", True)),
            )

        if action == "append_file":
            return self._append_file(
                path=kwargs["path"],
                content=kwargs.get("content", ""),
                encoding=kwargs.get("encoding", "utf-8"),
            )

        if action == "make_dir":
            return self._make_dir(
                path=kwargs["path"],
            )

        raise ValueError(f"Unsupported action: {action}")

    def _resolve_path(self, relative_path: str) -> Path:
        if relative_path is None:
            raise ValueError("path cannot be None.")

        relative_path = str(relative_path).strip()
        if relative_path == "":
            raise ValueError("path cannot be empty.")

        target = (self.workspace_root / relative_path).resolve()

        try:
            target.relative_to(self.workspace_root)
        except ValueError as exc:
            raise ValueError("Path escapes workspace root, operation denied.") from exc

        return target

    def _rel(self, path: Path) -> str:
        rel = str(path.relative_to(self.workspace_root))
        return rel.replace("\\", "/")

    def _list_files(self, path: str = ".", recursive: bool = False) -> Dict[str, Any]:
        target = self._resolve_path(path)

        if not target.exists():
            raise FileNotFoundError(f"Path not found: {target}")

        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {target}")

        items: List[Dict[str, Any]] = []

        iterator = target.rglob("*") if recursive else target.iterdir()

        for item in iterator:
            items.append(
                {
                    "path": self._rel(item),
                    "type": "dir" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None,
                }
            )

        items.sort(key=lambda x: (x["type"] != "dir", x["path"]))

        rel = self._rel(target)

        return {
            "ok": True,
            "success": True,
            "tool_name": self.name,
            "summary": f"Listed files under: {rel}",
            "action": "list_files",
            "path": rel,
            "items": items,
            "count": len(items),
            "changed_files": [],
            "evidence": [],
            "results": items,
        }

    def _read_file(self, path: str, encoding: str = "utf-8") -> Dict[str, Any]:
        target = self._resolve_path(path)

        if not target.exists():
            raise FileNotFoundError(f"File not found: {target}")

        if not target.is_file():
            raise FileNotFoundError(f"Not a file: {target}")

        content = target.read_text(encoding=encoding)
        rel = self._rel(target)

        return {
            "ok": True,
            "success": True,
            "tool_name": self.name,
            "summary": f"Read file: {rel}",
            "action": "read_file",
            "path": rel,
            "content": content,
            "encoding": encoding,
            "changed_files": [],
            "evidence": [],
            "results": [],
        }

    def _write_file(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
        overwrite: bool = True,
    ) -> Dict[str, Any]:
        target = self._resolve_path(path)

        if target.exists() and not overwrite:
            raise FileExistsError(f"File already exists: {target}")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding=encoding)

        rel = self._rel(target)

        return {
            "ok": True,
            "success": True,
            "tool_name": self.name,
            "summary": f"Wrote file: {rel}",
            "action": "write_file",
            "path": rel,
            "changed_files": [rel],
            "evidence": [],
            "results": [],
        }

    def _append_file(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
    ) -> Dict[str, Any]:
        target = self._resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        with target.open("a", encoding=encoding) as f:
            f.write(content)

        rel = self._rel(target)

        return {
            "ok": True,
            "success": True,
            "tool_name": self.name,
            "summary": f"Appended file: {rel}",
            "action": "append_file",
            "path": rel,
            "changed_files": [rel],
            "evidence": [],
            "results": [],
        }

    def _make_dir(self, path: str) -> Dict[str, Any]:
        target = self._resolve_path(path)
        target.mkdir(parents=True, exist_ok=True)

        rel = self._rel(target)

        return {
            "ok": True,
            "success": True,
            "tool_name": self.name,
            "summary": f"Created directory: {rel}",
            "action": "make_dir",
            "path": rel,
            "changed_files": [rel],
            "evidence": [],
            "results": [],
        }