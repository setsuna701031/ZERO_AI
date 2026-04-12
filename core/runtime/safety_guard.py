from __future__ import annotations

import copy
import os
import re
from typing import Any, Dict, List, Optional


class SafetyGuard:
    """
    ZERO Safety Guard v1

    目標：
    1. 阻擋危險 command
    2. 阻擋 path traversal（..）
    3. 阻擋 workspace 外的絕對路徑寫入/讀取
    4. single-shot 只能落在 workspace/shared
    5. task mode 只能落在該 task 的 sandbox

    設計原則：
    - command 預設保守
    - file IO 預設只能在受控 workspace 內
    - guard 只做 pre-check，不負責真正執行
    """

    def __init__(
        self,
        workspace_root: str,
        shared_dir: str,
        debug: bool = False,
    ) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        self.shared_dir = os.path.abspath(shared_dir)
        self.debug = debug

        self.blocked_command_patterns: List[str] = [
            r"\brm\s+-rf\b",
            r"\brm\s+-r\b",
            r"\brmdir\b",
            r"\bdel\b",
            r"\berase\b",
            r"\bformat\b",
            r"\bshutdown\b",
            r"\breboot\b",
            r"\bpoweroff\b",
            r"\bmkfs\b",
            r"\bdd\b",
            r"\bdiskpart\b",
            r"\breg\s+delete\b",
            r"\btakeown\b",
            r"\bicacls\b",
            r"\bRemove-Item\b",
            r"\bSet-Content\b",
            r"\bAdd-Content\b",
            r"\bOut-File\b",
            r"\bMove-Item\b",
            r"\bCopy-Item\b",
            r"\bRename-Item\b",
            r"\bgit\s+reset\s+--hard\b",
            r"\bgit\s+clean\s+-fd\b",
            r"\bgit\s+clean\s+-xdf\b",
        ]

        self.allowed_readonly_command_prefixes: List[str] = [
            "python",
            "py",
            "python3",
            "dir",
            "type",
            "echo",
            "git status",
            "git diff",
            "git log",
            "where",
            "which",
            "pwd",
            "cd",
            "ls",
            "cat",
        ]

    # ============================================================
    # public
    # ============================================================

    def check_step(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        executor: Any = None,
    ) -> Dict[str, Any]:
        step_copy = copy.deepcopy(step or {})
        step_type = str(step_copy.get("type", "")).strip().lower()

        if not step_type:
            return self._deny("step type missing", step_copy)

        if step_type == "command":
            return self._check_command(step_copy)

        if step_type in {"write_file", "workspace_write"}:
            return self._check_write_file(step_copy, task=task, executor=executor)

        if step_type in {"read_file", "workspace_read"}:
            return self._check_read_file(step_copy, task=task, executor=executor)

        # 其他 step 先放行
        return self._allow(step_copy)

    # ============================================================
    # command guard
    # ============================================================

    def _check_command(self, step: Dict[str, Any]) -> Dict[str, Any]:
        command = str(step.get("command", "")).strip()
        if not command:
            return self._deny("command missing", step)

        normalized = self._normalize_spaces(command).lower()

        for pattern in self.blocked_command_patterns:
            if re.search(pattern, normalized, flags=re.IGNORECASE):
                return self._deny(f"blocked dangerous command: {command}", step)

        # 阻擋 shell chaining，避免混雜危險命令
        for token in ["&&", "||", ";"]:
            if token in command:
                return self._deny(f"blocked chained command token: {token}", step)

        # 只允許相對保守的前綴
        if not self._is_command_prefix_allowed(normalized):
            return self._deny(f"command not allowed by policy: {command}", step)

        return self._allow(step)

    def _is_command_prefix_allowed(self, normalized_command: str) -> bool:
        for prefix in self.allowed_readonly_command_prefixes:
            if normalized_command == prefix or normalized_command.startswith(prefix + " "):
                return True
        return False

    # ============================================================
    # file guard
    # ============================================================

    def _check_write_file(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        executor: Any,
    ) -> Dict[str, Any]:
        path = str(step.get("path", "")).strip()
        if not path:
            return self._deny("path missing", step)

        bad = self._check_raw_path_string(path)
        if bad is not None:
            return self._deny(bad, step)

        if executor is None:
            return self._deny("executor missing for path resolution", step)

        try:
            resolved = executor.resolve_file_path(relative_path=path, task=task)
        except Exception as e:
            return self._deny(f"path resolve failed: {e}", step)

        allowed_base = self._get_allowed_base_for_task(task=task)
        if not self._is_under_base(resolved, allowed_base):
            return self._deny(
                f"write path escaped allowed base: {resolved}",
                step,
                extra={"resolved_path": resolved, "allowed_base": allowed_base},
            )

        return self._allow(step, extra={"resolved_path": resolved})

    def _check_read_file(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        executor: Any,
    ) -> Dict[str, Any]:
        path = str(step.get("path", "")).strip()
        if not path:
            return self._deny("path missing", step)

        bad = self._check_raw_path_string(path)
        if bad is not None:
            return self._deny(bad, step)

        if executor is None:
            return self._deny("executor missing for path resolution", step)

        try:
            resolved = executor.resolve_file_path(relative_path=path, task=task)
        except Exception as e:
            return self._deny(f"path resolve failed: {e}", step)

        allowed_base = self._get_allowed_base_for_task(task=task)
        if not self._is_under_base(resolved, allowed_base):
            return self._deny(
                f"read path escaped allowed base: {resolved}",
                step,
                extra={"resolved_path": resolved, "allowed_base": allowed_base},
            )

        return self._allow(step, extra={"resolved_path": resolved})

    def _check_raw_path_string(self, raw_path: str) -> Optional[str]:
        normalized = raw_path.replace("\\", "/").strip()

        if not normalized:
            return "empty path"

        if ".." in normalized.split("/"):
            return "parent traversal '..' is not allowed"

        return None

    def _get_allowed_base_for_task(self, task: Optional[Dict[str, Any]]) -> str:
        if not isinstance(task, dict):
            return self.shared_dir

        if task.get("is_pseudo_task") is True:
            return self.shared_dir

        sandbox_dir = task.get("sandbox_dir")
        if isinstance(sandbox_dir, str) and sandbox_dir.strip():
            return os.path.abspath(sandbox_dir)

        task_dir = task.get("task_dir")
        if isinstance(task_dir, str) and task_dir.strip():
            return os.path.abspath(os.path.join(task_dir, "sandbox"))

        return self.shared_dir

    def _is_under_base(self, target_path: str, base_dir: str) -> bool:
        try:
            target_abs = os.path.abspath(target_path)
            base_abs = os.path.abspath(base_dir)
            common = os.path.commonpath([target_abs, base_abs])
            return common == base_abs
        except Exception:
            return False

    # ============================================================
    # result helpers
    # ============================================================

    def _allow(self, step: Dict[str, Any], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": True,
            "allowed": True,
            "error": None,
            "step": copy.deepcopy(step),
        }
        if isinstance(extra, dict):
            payload.update(extra)
        return payload

    def _deny(
        self,
        error: str,
        step: Dict[str, Any],
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": False,
            "allowed": False,
            "error": error,
            "step": copy.deepcopy(step),
        }
        if isinstance(extra, dict):
            payload.update(extra)
        return payload

    def _normalize_spaces(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "").strip())