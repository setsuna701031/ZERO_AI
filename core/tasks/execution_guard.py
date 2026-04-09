from __future__ import annotations

import os
from typing import Any, Dict, Optional


class ExecutionGuard:
    """
    最小可用執行守門員

    目標：
    1. 所有 write_file / read_file / command 都先經過這裡
    2. 限制寫入只能在 workspace_root 之下
    3. command 預設關閉，避免先炸
    """

    def __init__(
        self,
        workspace_root: str,
        shared_dir: str,
        allow_commands: bool = False,
    ) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        self.shared_dir = os.path.abspath(shared_dir)
        self.allow_commands = bool(allow_commands)

    def check_step(
        self,
        step: Dict[str, Any],
        task_dir: str,
    ) -> Dict[str, Any]:
        step_type = str(step.get("type") or "").strip().lower()
        task_dir_abs = os.path.abspath(task_dir)

        if step_type == "noop":
            return {"ok": True}

        if step_type == "write_file":
            raw_path = str(step.get("path") or "").strip()
            if not raw_path:
                return {"ok": False, "error": "write_file step missing path"}

            full_path = self._resolve_path(raw_path=raw_path, task_dir=task_dir_abs)
            if not self._is_under_workspace(full_path):
                return {
                    "ok": False,
                    "error": f"write_file blocked: path outside workspace: {full_path}",
                }

            return {
                "ok": True,
                "resolved_path": full_path,
            }

        if step_type == "read_file":
            raw_path = str(step.get("path") or "").strip()
            if not raw_path:
                return {"ok": False, "error": "read_file step missing path"}

            full_path = self._resolve_path(raw_path=raw_path, task_dir=task_dir_abs)
            if not self._is_under_workspace(full_path):
                return {
                    "ok": False,
                    "error": f"read_file blocked: path outside workspace: {full_path}",
                }

            return {
                "ok": True,
                "resolved_path": full_path,
            }

        if step_type == "command":
            if not self.allow_commands:
                return {
                    "ok": False,
                    "error": "command execution blocked by guard",
                }

            return {"ok": True}

        return {
            "ok": False,
            "error": f"unsupported step type: {step_type}",
        }

    def _resolve_path(self, raw_path: str, task_dir: str) -> str:
        normalized = str(raw_path or "").replace("\\", "/").strip()

        if os.path.isabs(normalized):
            return os.path.abspath(normalized)

        if normalized.startswith("shared/"):
            relative_part = normalized[len("shared/"):].strip("/")
            return os.path.abspath(os.path.join(self.shared_dir, relative_part))

        return os.path.abspath(os.path.join(task_dir, normalized))

    def _is_under_workspace(self, path: str) -> bool:
        try:
            common = os.path.commonpath([self.workspace_root, os.path.abspath(path)])
            return common == self.workspace_root
        except Exception:
            return False