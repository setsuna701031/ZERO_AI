from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


class WorkspaceTool:
    """
    ZERO Workspace Tool

    支援：
    - read_file
    - write_file
    - append_file
    - exists
    - list_dir
    - make_dir
    - delete_file

    這版重點：
    - 讀不到檔案一定回傳 success=False
    - 不再把 missing file 當成成功
    - 讓 task_runtime 能正確判定 tool step failed
    """

    name = "workspace_tool"

    def __init__(self, workspace_root: Path | str) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    # =========================================================
    # Public
    # =========================================================

    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {
                "success": False,
                "error": "payload must be a dict",
            }

        action = str(payload.get("action", "")).strip().lower()
        if not action:
            return {
                "success": False,
                "error": "missing action",
            }

        if action == "read_file":
            return self.read_file(payload.get("path"))

        if action == "write_file":
            return self.write_file(
                path=payload.get("path"),
                content=payload.get("content", ""),
                overwrite=bool(payload.get("overwrite", True)),
            )

        if action == "append_file":
            return self.append_file(
                path=payload.get("path"),
                content=payload.get("content", ""),
            )

        if action == "exists":
            return self.exists(payload.get("path"))

        if action == "list_dir":
            return self.list_dir(payload.get("path", ""))

        if action == "make_dir":
            return self.make_dir(payload.get("path"))

        if action == "delete_file":
            return self.delete_file(payload.get("path"))

        return {
            "success": False,
            "error": f"unsupported action: {action}",
        }

    def run(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        payload = {"action": action}
        payload.update(kwargs)
        return self.execute(payload)

    # =========================================================
    # File Ops
    # =========================================================

    def read_file(self, path: Any) -> Dict[str, Any]:
        try:
            target = self._resolve_path(path)
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

        if not target.exists():
            return {
                "success": False,
                "error": f"file not found: {target}",
                "path": str(target),
            }

        if not target.is_file():
            return {
                "success": False,
                "error": f"path is not a file: {target}",
                "path": str(target),
            }

        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return {
                "success": False,
                "error": f"file is not utf-8 text: {target}",
                "path": str(target),
            }
        except Exception as exc:
            return {
                "success": False,
                "error": f"failed to read file: {exc}",
                "path": str(target),
            }

        return {
            "success": True,
            "action": "read_file",
            "path": str(target),
            "content": content,
            "size": len(content),
        }

    def write_file(self, path: Any, content: Any, overwrite: bool = True) -> Dict[str, Any]:
        try:
            target = self._resolve_path(path)
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

        if target.exists() and not overwrite:
            return {
                "success": False,
                "error": f"file already exists: {target}",
                "path": str(target),
            }

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            text = "" if content is None else str(content)
            target.write_text(text, encoding="utf-8")
        except Exception as exc:
            return {
                "success": False,
                "error": f"failed to write file: {exc}",
                "path": str(target),
            }

        return {
            "success": True,
            "action": "write_file",
            "path": str(target),
            "written_chars": len("" if content is None else str(content)),
        }

    def append_file(self, path: Any, content: Any) -> Dict[str, Any]:
        try:
            target = self._resolve_path(path)
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            text = "" if content is None else str(content)
            with open(target, "a", encoding="utf-8") as f:
                f.write(text)
        except Exception as exc:
            return {
                "success": False,
                "error": f"failed to append file: {exc}",
                "path": str(target),
            }

        return {
            "success": True,
            "action": "append_file",
            "path": str(target),
            "appended_chars": len("" if content is None else str(content)),
        }

    def delete_file(self, path: Any) -> Dict[str, Any]:
        try:
            target = self._resolve_path(path)
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

        if not target.exists():
            return {
                "success": False,
                "error": f"file not found: {target}",
                "path": str(target),
            }

        if not target.is_file():
            return {
                "success": False,
                "error": f"path is not a file: {target}",
                "path": str(target),
            }

        try:
            target.unlink()
        except Exception as exc:
            return {
                "success": False,
                "error": f"failed to delete file: {exc}",
                "path": str(target),
            }

        return {
            "success": True,
            "action": "delete_file",
            "path": str(target),
        }

    def exists(self, path: Any) -> Dict[str, Any]:
        try:
            target = self._resolve_path(path)
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

        return {
            "success": True,
            "action": "exists",
            "path": str(target),
            "exists": target.exists(),
            "is_file": target.is_file(),
            "is_dir": target.is_dir(),
        }

    def list_dir(self, path: Any = "") -> Dict[str, Any]:
        try:
            target = self._resolve_path(path or ".")
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

        if not target.exists():
            return {
                "success": False,
                "error": f"directory not found: {target}",
                "path": str(target),
            }

        if not target.is_dir():
            return {
                "success": False,
                "error": f"path is not a directory: {target}",
                "path": str(target),
            }

        try:
            items: List[Dict[str, Any]] = []
            for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                items.append(
                    {
                        "name": child.name,
                        "path": str(child),
                        "is_dir": child.is_dir(),
                        "is_file": child.is_file(),
                    }
                )
        except Exception as exc:
            return {
                "success": False,
                "error": f"failed to list directory: {exc}",
                "path": str(target),
            }

        return {
            "success": True,
            "action": "list_dir",
            "path": str(target),
            "items": items,
            "count": len(items),
        }

    def make_dir(self, path: Any) -> Dict[str, Any]:
        try:
            target = self._resolve_path(path)
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

        try:
            target.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            return {
                "success": False,
                "error": f"failed to make directory: {exc}",
                "path": str(target),
            }

        return {
            "success": True,
            "action": "make_dir",
            "path": str(target),
        }

    # =========================================================
    # Helpers
    # =========================================================

    def _resolve_path(self, raw_path: Any) -> Path:
        text = str(raw_path or "").strip()
        if not text:
            raise ValueError("missing path")

        path_obj = Path(text)

        if path_obj.is_absolute():
            resolved = path_obj.resolve()
        else:
            resolved = (self.workspace_root / path_obj).resolve()

        try:
            resolved.relative_to(self.workspace_root)
        except ValueError:
            raise ValueError(f"path escapes workspace root: {resolved}")

        return resolved