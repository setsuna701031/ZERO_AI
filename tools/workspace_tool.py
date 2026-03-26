from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional


class WorkspaceTool:
    """
    ZERO Workspace Tool
    """

    name = "workspace_tool"

    def __init__(
        self,
        workspace_root: str = "workspace",
        project_root: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self.project_root = Path(project_root).resolve() if project_root else Path.cwd().resolve()
        self.workspace_root = self._resolve_workspace_root(workspace_root)

        if self.workspace_root is None:
            raise ValueError("workspace_root is not set")

        self.workspace_root.mkdir(parents=True, exist_ok=True)
        (self.workspace_root / "tasks").mkdir(parents=True, exist_ok=True)
        (self.workspace_root / "temp").mkdir(parents=True, exist_ok=True)
        (self.workspace_root / "logs").mkdir(parents=True, exist_ok=True)
        (self.workspace_root / "memory").mkdir(parents=True, exist_ok=True)
        (self.workspace_root / "test").mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # execute
    # ------------------------------------------------------------------

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = params or {}
        action = (action or "").strip()

        if action == "create_dir":
            return self.create_dir(**params)

        if action == "write_file":
            return self.write_file(**params)

        if action == "append_file":
            return self.append_file(**params)

        if action == "read_file":
            return self.read_file(**params)

        if action == "exists":
            return self.exists(**params)

        if action == "list_dir":
            return self.list_dir(**params)

        if action == "delete_file":
            return self.delete_file(**params)

        if action == "delete_dir":
            return self.delete_dir(**params)

        return self._error(f"unsupported workspace action: {action}")

    # ------------------------------------------------------------------
    # file operations
    # ------------------------------------------------------------------

    def create_dir(
        self,
        path: str,
        task_id: Optional[str] = None,
        use_task_files_dir: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        target = self._resolve_target_path(path, task_id, use_task_files_dir, True)
        target.mkdir(parents=True, exist_ok=True)

        return self._success({
            "path": str(target),
            "exists": target.exists(),
        })

    def write_file(
        self,
        path: str,
        content: str = "",
        task_id: Optional[str] = None,
        use_task_files_dir: bool = True,
        encoding: str = "utf-8",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        target = self._resolve_target_path(path, task_id, use_task_files_dir, True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("" if content is None else str(content), encoding=encoding)

        return self._success({
            "path": str(target),
            "size": target.stat().st_size if target.exists() else 0,
        })

    def append_file(
        self,
        path: str,
        content: str = "",
        task_id: Optional[str] = None,
        use_task_files_dir: bool = True,
        encoding: str = "utf-8",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        target = self._resolve_target_path(path, task_id, use_task_files_dir, True)
        target.parent.mkdir(parents=True, exist_ok=True)

        with target.open("a", encoding=encoding) as f:
            f.write("" if content is None else str(content))

        return self._success({
            "path": str(target),
            "size": target.stat().st_size if target.exists() else 0,
        })

    def read_file(
        self,
        path: str,
        task_id: Optional[str] = None,
        use_task_files_dir: bool = True,
        encoding: str = "utf-8",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        target = self._resolve_target_path(path, task_id, use_task_files_dir, False)

        if not target.exists():
            return self._error(f"file not found: {target}")

        content = target.read_text(encoding=encoding)

        return self._success({
            "path": str(target),
            "content": content,
            "size": len(content),
        })

    def exists(
        self,
        path: str,
        task_id: Optional[str] = None,
        use_task_files_dir: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        target = self._resolve_target_path(path, task_id, use_task_files_dir, False)

        return self._success({
            "path": str(target),
            "exists": target.exists(),
            "is_file": target.is_file(),
            "is_dir": target.is_dir(),
        })

    def list_dir(
        self,
        path: str = "",
        task_id: Optional[str] = None,
        use_task_files_dir: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        target = self._resolve_target_path(path or ".", task_id, use_task_files_dir, False)

        if not target.exists():
            return self._error(f"directory not found: {target}")

        items = []
        for p in target.iterdir():
            items.append({
                "name": p.name,
                "is_file": p.is_file(),
                "is_dir": p.is_dir(),
            })

        return self._success({
            "path": str(target),
            "items": items,
            "count": len(items),
        })

    def delete_file(
        self,
        path: str,
        task_id: Optional[str] = None,
        use_task_files_dir: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        target = self._resolve_target_path(path, task_id, use_task_files_dir, False)

        if target.exists() and target.is_file():
            target.unlink()

        return self._success({"path": str(target)})

    def delete_dir(
        self,
        path: str,
        task_id: Optional[str] = None,
        use_task_files_dir: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        target = self._resolve_target_path(path, task_id, use_task_files_dir, False)

        if target.exists() and target.is_dir():
            shutil.rmtree(target)

        return self._success({"path": str(target)})

    # ------------------------------------------------------------------
    # path helpers
    # ------------------------------------------------------------------

    def _resolve_workspace_root(self, workspace_root: str) -> Optional[Path]:
        if not workspace_root:
            return None

        root = Path(workspace_root)

        if not root.is_absolute():
            root = self.project_root / workspace_root

        return root.resolve()

    def _resolve_target_path(
        self,
        path: str,
        task_id: Optional[str],
        prefer_task_files_dir: bool,
        allow_nonexistent: bool,
    ) -> Path:
        base_dir = self.workspace_root

        if task_id and prefer_task_files_dir:
            base_dir = self.workspace_root / "tasks" / task_id / "files"
            base_dir.mkdir(parents=True, exist_ok=True)

        target = Path(path)

        if not target.is_absolute():
            target = base_dir / path

        target = target.resolve()

        if not allow_nonexistent and not target.exists():
            return target

        return target

    # ------------------------------------------------------------------
    # result helpers
    # ------------------------------------------------------------------

    def _success(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True,
            "message": "workspace operation success",
            "data": data,
        }

    def _error(self, message: str) -> Dict[str, Any]:
        return {
            "success": False,
            "message": message,
            "data": {},
        }