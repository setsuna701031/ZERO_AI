from __future__ import annotations

import os
from typing import Any, Dict


class TaskPathManager:
    """
    統一管理 ZERO Task OS 的 workspace / task / shared / sandbox 路徑。

    原則：
    - workspace/tasks.json 是全域任務索引
    - workspace/tasks/<task_id>/... 是單一任務工作目錄
    - workspace/shared/... 是跨任務共享區
    - workspace/tasks/<task_id>/sandbox/... 是任務私有工作區
    - 其他模組不要自己手拼路徑，全部走這個 manager
    """

    def __init__(self, workspace_root: str = "workspace") -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        self.tasks_root = os.path.join(self.workspace_root, "tasks")
        self.shared_root = os.path.join(self.workspace_root, "shared")
        self.tasks_index_file = os.path.join(self.workspace_root, "tasks.json")
        self.scheduler_state_file = os.path.join(self.workspace_root, "scheduler_state.json")
        self.runtime_root = os.path.join(self.workspace_root, "runtime")
        self.logs_root = os.path.join(self.workspace_root, "logs")
        self.memory_root = os.path.join(self.workspace_root, "memory")
        self.knowledge_root = os.path.join(self.workspace_root, "knowledge")
        self.cache_root = os.path.join(self.workspace_root, "cache")

    # ============================================================
    # workspace-level paths
    # ============================================================

    def ensure_workspace(self) -> None:
        os.makedirs(self.workspace_root, exist_ok=True)
        os.makedirs(self.tasks_root, exist_ok=True)
        os.makedirs(self.shared_root, exist_ok=True)
        os.makedirs(self.runtime_root, exist_ok=True)
        os.makedirs(self.logs_root, exist_ok=True)
        os.makedirs(self.memory_root, exist_ok=True)
        os.makedirs(self.knowledge_root, exist_ok=True)
        os.makedirs(self.cache_root, exist_ok=True)

    def get_workspace_paths(self) -> Dict[str, str]:
        return {
            "workspace_root": self.workspace_root,
            "tasks_root": self.tasks_root,
            "shared_root": self.shared_root,
            "tasks_index_file": self.tasks_index_file,
            "scheduler_state_file": self.scheduler_state_file,
            "runtime_root": self.runtime_root,
            "logs_root": self.logs_root,
            "memory_root": self.memory_root,
            "knowledge_root": self.knowledge_root,
            "cache_root": self.cache_root,
        }

    # ============================================================
    # task-level paths
    # ============================================================

    def task_dir(self, task_id: str) -> str:
        return os.path.join(self.tasks_root, str(task_id).strip())

    def sandbox_dir(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "sandbox")

    def plan_file(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "plan.json")

    def runtime_state_file(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "runtime_state.json")

    def result_file(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "result.json")

    def execution_log_file(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "execution_log.json")

    def task_snapshot_file(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "task.json")

    def task_log_file(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "task.log")

    def runner_trace_file(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "task_runner_trace.log")

    def runtime_trace_file(self, task_id: str) -> str:
        return os.path.join(self.task_dir(task_id), "task_runtime_trace.log")

    def file_in_task_dir(self, task_id: str, relative_path: str) -> str:
        cleaned = self._normalize_relative_path(relative_path)
        return os.path.join(self.task_dir(task_id), cleaned)

    def file_in_sandbox(self, task_id: str, relative_path: str) -> str:
        cleaned = self._normalize_relative_path(relative_path)
        return os.path.join(self.sandbox_dir(task_id), cleaned)

    def file_in_shared(self, relative_path: str) -> str:
        cleaned = self._normalize_relative_path(relative_path)
        if cleaned.startswith("shared" + os.sep):
            cleaned = cleaned[len("shared" + os.sep):]
        elif cleaned == "shared":
            cleaned = ""
        return os.path.join(self.shared_root, cleaned)

    def get_task_paths(self, task_id: str) -> Dict[str, str]:
        task_id = str(task_id).strip()
        return {
            "task_id": task_id,
            "task_dir": self.task_dir(task_id),
            "sandbox_dir": self.sandbox_dir(task_id),
            "plan_file": self.plan_file(task_id),
            "runtime_state_file": self.runtime_state_file(task_id),
            "result_file": self.result_file(task_id),
            "execution_log_file": self.execution_log_file(task_id),
            "task_file": self.task_snapshot_file(task_id),
            "log_file": self.task_log_file(task_id),
            "runner_trace_file": self.runner_trace_file(task_id),
            "runtime_trace_file": self.runtime_trace_file(task_id),
        }

    def ensure_task_dir(self, task_id: str) -> str:
        task_dir = self.task_dir(task_id)
        os.makedirs(task_dir, exist_ok=True)
        return task_dir

    def ensure_task_paths(self, task_id: str) -> Dict[str, str]:
        self.ensure_workspace()
        self.ensure_task_dir(task_id)
        os.makedirs(self.sandbox_dir(task_id), exist_ok=True)
        return self.get_task_paths(task_id)

    # ============================================================
    # path resolve
    # ============================================================

    def resolve_path(
        self,
        raw_path: str,
        *,
        task: Dict[str, Any] | None = None,
        task_id: str | None = None,
        default_scope: str = "sandbox",
    ) -> str:
        """
        規則：
        - shared/...   -> workspace/shared/...
        - sandbox/...  -> workspace/tasks/<task_id>/sandbox/...
        - 一般相對路徑   -> 預設走 sandbox
        - 絕對路徑       -> 直接拒絕（避免亂寫系統）
        """
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("raw_path is empty")

        if os.path.isabs(raw_path):
            raise ValueError(f"absolute path not allowed: {raw_path}")

        resolved_task_id = self._extract_task_id(task=task, task_id=task_id)
        normalized = self._normalize_relative_path(raw_path)
        unix_style = normalized.replace("\\", "/")

        if unix_style.startswith("shared/"):
            relative = unix_style[len("shared/"):]
            final_path = os.path.join(self.shared_root, self._normalize_relative_path(relative))
            return self._ensure_inside_workspace(final_path)

        if unix_style == "shared":
            return self._ensure_inside_workspace(self.shared_root)

        if unix_style.startswith("sandbox/"):
            if not resolved_task_id:
                raise ValueError("sandbox path requires task_id")
            relative = unix_style[len("sandbox/"):]
            final_path = os.path.join(self.sandbox_dir(resolved_task_id), self._normalize_relative_path(relative))
            return self._ensure_inside_workspace(final_path)

        if unix_style == "sandbox":
            if not resolved_task_id:
                raise ValueError("sandbox path requires task_id")
            return self._ensure_inside_workspace(self.sandbox_dir(resolved_task_id))

        if default_scope == "shared":
            final_path = os.path.join(self.shared_root, normalized)
            return self._ensure_inside_workspace(final_path)

        if not resolved_task_id:
            raise ValueError("task_id required for sandbox-relative path")

        final_path = os.path.join(self.sandbox_dir(resolved_task_id), normalized)
        return self._ensure_inside_workspace(final_path)

    def resolve_command_cwd(
        self,
        *,
        task: Dict[str, Any] | None = None,
        prefer_workspace_root: bool = False,
    ) -> str:
        """
        command 的 cwd 規則：
        - 一般 task command 預設跑 task_dir
        - 若需要讓 command 能以 `python shared/xxx.py` 形式執行，
          可選 workspace_root
        """
        if prefer_workspace_root:
            return self.workspace_root

        if isinstance(task, dict):
            task_dir = str(task.get("task_dir", "") or "").strip()
            if task_dir:
                return task_dir

            task_id = self._extract_task_id(task=task, task_id=None)
            if task_id:
                return self.task_dir(task_id)

        return self.workspace_root

    # ============================================================
    # task helpers
    # ============================================================

    def enrich_task(self, task: Dict[str, object]) -> Dict[str, object]:
        """
        把路徑欄位補到 task dict 裡。
        不修改外部傳入物件，回傳新 dict。
        """
        if not isinstance(task, dict):
            raise TypeError("task must be dict")

        task_id = self._extract_task_id(task=task, task_id=None)
        if not task_id:
            raise ValueError("task missing task_id/task_name/id")

        enriched = dict(task)
        paths = self.ensure_task_paths(task_id)

        enriched["task_id"] = task_id
        enriched["task_name"] = task_id
        enriched["workspace_root"] = self.workspace_root
        enriched["workspace_dir"] = self.tasks_root
        enriched["shared_dir"] = self.shared_root
        enriched["task_dir"] = paths["task_dir"]
        enriched["sandbox_dir"] = paths["sandbox_dir"]
        enriched["plan_file"] = paths["plan_file"]
        enriched["runtime_state_file"] = paths["runtime_state_file"]
        enriched["result_file"] = paths["result_file"]
        enriched["execution_log_file"] = paths["execution_log_file"]
        enriched["log_file"] = paths["log_file"]

        return enriched

    # ============================================================
    # internal helpers
    # ============================================================

    def _extract_task_id(
        self,
        *,
        task: Dict[str, Any] | None,
        task_id: str | None,
    ) -> str:
        if isinstance(task_id, str) and task_id.strip():
            return task_id.strip()

        if isinstance(task, dict):
            value = str(
                task.get("task_id")
                or task.get("task_name")
                or task.get("id")
                or ""
            ).strip()
            return value

        return ""

    def _normalize_relative_path(self, value: str) -> str:
        text = str(value).strip().replace("/", os.sep).replace("\\", os.sep)
        text = os.path.normpath(text)

        if text in ("", "."):
            return ""

        if text.startswith(".." + os.sep) or text == "..":
            raise ValueError(f"path escapes workspace: {value}")

        return text

    def _ensure_inside_workspace(self, path: str) -> str:
        full = os.path.abspath(path)
        workspace = os.path.abspath(self.workspace_root)

        try:
            common = os.path.commonpath([workspace, full])
        except ValueError:
            raise ValueError(f"path outside workspace: {path}")

        if common != workspace:
            raise ValueError(f"path outside workspace: {path}")

        return full