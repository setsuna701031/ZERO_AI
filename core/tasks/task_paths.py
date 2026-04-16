from __future__ import annotations

import os
from typing import Any, Dict, List


class TaskPathManager:
    """
    統一管理 ZERO Task OS 的 workspace / task / shared / sandbox 路徑。

    收束後規則：

    1. 有 task_id 時
       - 寫入預設走 sandbox
       - 讀取相對路徑時，sandbox 優先，shared fallback

    2. 沒有 task_id 時
       - 寫入相對路徑預設走 shared
       - 讀取相對路徑預設走 shared
       - '.' 代表 workspace_root，方便 workspace-level list / inspect

    3. 明確指定：
       - shared/... 或 workspace/shared/...   -> shared
       - sandbox/... 或 workspace/sandbox/... -> sandbox（需要 task_id）

    4. 一律拒絕絕對路徑與 workspace 外逃
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
        return self._join_under_base(self.task_dir(task_id), cleaned)

    def file_in_sandbox(self, task_id: str, relative_path: str) -> str:
        cleaned = self._normalize_relative_path(relative_path)
        return self._join_under_base(self.sandbox_dir(task_id), cleaned)

    def file_in_shared(self, relative_path: str) -> str:
        cleaned = self._normalize_relative_path(relative_path)
        scope, relative = self._split_scope(cleaned)
        if scope == "shared":
            cleaned = relative
        return self._join_under_base(self.shared_root, cleaned)

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
    # path resolve - write
    # ============================================================

    def resolve_path(
        self,
        raw_path: str,
        *,
        task: Dict[str, Any] | None = None,
        task_id: str | None = None,
        default_scope: str = "sandbox",
    ) -> str:
        return self.resolve_write_path(
            raw_path,
            task=task,
            task_id=task_id,
            default_scope=default_scope,
        )

    def resolve_write_path(
        self,
        raw_path: str,
        *,
        task: Dict[str, Any] | None = None,
        task_id: str | None = None,
        default_scope: str = "sandbox",
    ) -> str:
        """
        寫入規則：

        - shared/... 或 workspace/shared/...   -> workspace/shared/...
        - sandbox/... 或 workspace/sandbox/... -> workspace/tasks/<task_id>/sandbox/...
        - 一般相對路徑：
            * 有 task_id -> 預設 sandbox
            * 沒 task_id -> 預設 shared
        - 絕對路徑 -> 拒絕
        """
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("raw_path is empty")

        if os.path.isabs(raw_path):
            raise ValueError(f"absolute path not allowed: {raw_path}")

        resolved_task_id = self._extract_task_id(task=task, task_id=task_id)
        normalized = self._normalize_relative_path(raw_path)
        scope, relative = self._split_scope(normalized)

        if scope == "shared":
            final_path = self._join_under_base(self.shared_root, relative)
            return self._ensure_inside_workspace(final_path)

        if scope == "sandbox":
            if not resolved_task_id:
                raise ValueError("sandbox path requires task_id")
            final_path = self._join_under_base(self.sandbox_dir(resolved_task_id), relative)
            return self._ensure_inside_workspace(final_path)

        effective_default_scope = str(default_scope).strip().lower()

        if effective_default_scope == "shared":
            final_path = self._join_under_base(self.shared_root, normalized)
            return self._ensure_inside_workspace(final_path)

        if effective_default_scope == "sandbox" and resolved_task_id:
            final_path = self._join_under_base(self.sandbox_dir(resolved_task_id), normalized)
            return self._ensure_inside_workspace(final_path)

        # 主線友善 fallback：
        # 沒 task_id 時，相對路徑寫入預設走 shared
        final_path = self._join_under_base(self.shared_root, normalized)
        return self._ensure_inside_workspace(final_path)

    # ============================================================
    # path resolve - read
    # ============================================================

    def resolve_read_path(
        self,
        raw_path: str,
        *,
        task: Dict[str, Any] | None = None,
        task_id: str | None = None,
        prefer_scopes: tuple[str, ...] = ("sandbox", "shared"),
        return_fallback_candidate_if_missing: bool = True,
    ) -> str:
        """
        讀取規則：

        1. 明確 shared/... 或 workspace/shared/...  -> 直接 shared
        2. 明確 sandbox/... 或 workspace/sandbox/... -> 直接 sandbox
        3. 一般相對路徑：
           - 有 task_id: sandbox 優先，shared fallback
           - 沒 task_id: shared
        4. '.' -> workspace_root
        """
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("raw_path is empty")

        if os.path.isabs(raw_path):
            raise ValueError(f"absolute path not allowed: {raw_path}")

        normalized = self._normalize_relative_path(raw_path)
        resolved_task_id = self._extract_task_id(task=task, task_id=task_id)

        if normalized == ".":
            return self.workspace_root

        scope, _ = self._split_scope(normalized)

        if scope == "shared":
            return self.resolve_write_path(
                normalized,
                task=task,
                task_id=resolved_task_id,
                default_scope="shared",
            )

        if scope == "sandbox":
            return self.resolve_write_path(
                normalized,
                task=task,
                task_id=resolved_task_id,
                default_scope="sandbox",
            )

        candidates = self.resolve_read_candidates(
            raw_path,
            task=task,
            task_id=resolved_task_id,
            prefer_scopes=prefer_scopes,
        )

        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate

        if return_fallback_candidate_if_missing and candidates:
            return candidates[0]

        raise FileNotFoundError(f"read target not found: {raw_path}")

    def resolve_read_candidates(
        self,
        raw_path: str,
        *,
        task: Dict[str, Any] | None = None,
        task_id: str | None = None,
        prefer_scopes: tuple[str, ...] = ("sandbox", "shared"),
    ) -> List[str]:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("raw_path is empty")

        if os.path.isabs(raw_path):
            raise ValueError(f"absolute path not allowed: {raw_path}")

        normalized = self._normalize_relative_path(raw_path)
        scope, relative = self._split_scope(normalized)
        resolved_task_id = self._extract_task_id(task=task, task_id=task_id)

        if normalized == ".":
            return [self.workspace_root]

        if scope == "shared":
            return [
                self._ensure_inside_workspace(self._join_under_base(self.shared_root, relative))
            ]

        if scope == "sandbox":
            if not resolved_task_id:
                raise ValueError("sandbox path requires task_id")
            return [
                self._ensure_inside_workspace(
                    self._join_under_base(self.sandbox_dir(resolved_task_id), relative)
                )
            ]

        candidates: List[str] = []

        # 沒 task_id 時，主線讀取預設走 shared
        if not resolved_task_id:
            candidates.append(
                self._ensure_inside_workspace(
                    self._join_under_base(self.shared_root, normalized)
                )
            )
            return candidates

        for scope_name in prefer_scopes:
            scope_name = str(scope_name).strip().lower()

            if scope_name == "sandbox":
                candidate = self._join_under_base(self.sandbox_dir(resolved_task_id), normalized)
                candidates.append(self._ensure_inside_workspace(candidate))
                continue

            if scope_name == "shared":
                candidate = self._join_under_base(self.shared_root, normalized)
                candidates.append(self._ensure_inside_workspace(candidate))
                continue

            raise ValueError(f"unsupported scope in prefer_scopes: {scope_name}")

        if not candidates:
            raise ValueError("no read candidates available; task_id may be missing")

        return candidates

    # ============================================================
    # command cwd
    # ============================================================

    def resolve_command_cwd(
        self,
        *,
        task: Dict[str, Any] | None = None,
        prefer_workspace_root: bool = False,
    ) -> str:
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

        if text == "":
            return ""

        if text == ".":
            return "."

        if text.startswith(".." + os.sep) or text == "..":
            raise ValueError(f"path escapes workspace: {value}")

        return text

    def _split_scope(self, normalized_path: str) -> tuple[str, str]:
        """
        scope:
        - shared
        - sandbox
        - relative
        """
        unix_style = normalized_path.replace("\\", "/").strip("/")

        if unix_style == "":
            return "relative", ""

        if unix_style == ".":
            return "relative", "."

        if unix_style == "shared":
            return "shared", ""

        if unix_style.startswith("shared/"):
            return "shared", unix_style[len("shared/"):]

        if unix_style == "workspace/shared":
            return "shared", ""

        if unix_style.startswith("workspace/shared/"):
            return "shared", unix_style[len("workspace/shared/"):]

        if unix_style == "sandbox":
            return "sandbox", ""

        if unix_style.startswith("sandbox/"):
            return "sandbox", unix_style[len("sandbox/"):]

        if unix_style == "workspace/sandbox":
            return "sandbox", ""

        if unix_style.startswith("workspace/sandbox/"):
            return "sandbox", unix_style[len("workspace/sandbox/"):]

        return "relative", normalized_path

    def _join_under_base(self, base: str, relative: str) -> str:
        cleaned = str(relative or "").strip()

        if cleaned in ("", "."):
            return os.path.abspath(base)

        return os.path.abspath(os.path.join(base, cleaned))

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