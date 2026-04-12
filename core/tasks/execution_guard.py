from __future__ import annotations

import os
import re
import shlex
from typing import Any, Dict


class ExecutionGuard:
    """
    最小可用執行守門員（B 方案收束版）

    目標：
    1. 所有 write_file / read_file / command 都先經過這裡
    2. 限制檔案操作只能在 workspace_root 之下
    3. command 預設關閉
    4. 收束期只有限放行安全 python command
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
            command = str(step.get("command") or "").strip()
            if not command:
                return {"ok": False, "error": "command step missing command"}

            return self._check_command(command=command, task_dir=task_dir_abs)

        return {
            "ok": False,
            "error": f"unsupported step type: {step_type}",
        }

    def _check_command(self, command: str, task_dir: str) -> Dict[str, Any]:
        if self.allow_commands:
            return {"ok": True}

        normalized = str(command or "").strip()
        lowered = normalized.lower()

        # 收束期白名單：
        # 1. python -c "print('hello')" 類型
        # 2. python / py 執行 workspace 內腳本
        if self._is_safe_inline_python(lowered):
            return {"ok": True, "guard_mode": "safe_python_inline"}

        script_check = self._extract_python_script_path(normalized)
        if script_check is not None:
            script_path = self._resolve_path(raw_path=script_check, task_dir=task_dir)
            if not self._is_under_workspace(script_path):
                return {
                    "ok": False,
                    "error": f"python script blocked outside workspace: {script_path}",
                }
            return {
                "ok": True,
                "guard_mode": "safe_python_script",
                "resolved_script_path": script_path,
            }

        return {
            "ok": False,
            "error": "command execution blocked by guard",
        }

    def _is_safe_inline_python(self, lowered_command: str) -> bool:
        # 只放行非常小範圍的 inline python 測試
        patterns = [
            r'^python\s+-c\s+"print\(.+\)"$',
            r"^python\s+-c\s+'print\(.+\)'$",
            r'^py\s+-c\s+"print\(.+\)"$',
            r"^py\s+-c\s+'print\(.+\)'$",
        ]
        return any(re.match(p, lowered_command) for p in patterns)

    def _extract_python_script_path(self, command: str) -> str | None:
        try:
            parts = shlex.split(command, posix=False)
        except Exception:
            parts = command.split()

        if len(parts) < 2:
            return None

        exe = str(parts[0]).strip().lower()
        if exe not in {"python", "py", "python.exe", "py.exe"}:
            return None

        # python -c ... 不算腳本
        if len(parts) >= 2 and str(parts[1]).strip().lower() == "-c":
            return None

        script_path = str(parts[1]).strip().strip('"').strip("'")
        if not script_path:
            return None

        return script_path

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