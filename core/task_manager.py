from __future__ import annotations

import copy
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Union


TASK_STATUS_QUEUED = "queued"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_FINISHED = "finished"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_RETRYING = "retrying"
TASK_STATUS_WAITING = "waiting"
TASK_STATUS_BLOCKED = "blocked"
TASK_STATUS_PAUSED = "paused"
TASK_STATUS_CANCELED = "canceled"

PENDING_STATUSES = {
    TASK_STATUS_QUEUED,
    TASK_STATUS_RUNNING,
    TASK_STATUS_RETRYING,
    TASK_STATUS_WAITING,
    TASK_STATUS_BLOCKED,
    TASK_STATUS_PAUSED,
}

TERMINAL_STATUSES = {
    TASK_STATUS_FINISHED,
    TASK_STATUS_FAILED,
    TASK_STATUS_CANCELED,
}


@dataclass
class Task:
    task_id: str
    title: str
    goal: str

    task_name: str = ""
    status: str = TASK_STATUS_QUEUED
    priority: int = 0

    steps: List[Dict[str, Any]] = field(default_factory=list)
    current_step_index: int = 0
    steps_total: int = 0

    results: List[Dict[str, Any]] = field(default_factory=list)
    step_results: List[Dict[str, Any]] = field(default_factory=list)
    last_step_result: Optional[Dict[str, Any]] = None
    final_result: Optional[Dict[str, Any]] = None
    final_answer: str = ""

    planner_result: Dict[str, Any] = field(default_factory=dict)

    history: List[str] = field(default_factory=lambda: [TASK_STATUS_QUEUED])
    execution_log: List[Dict[str, Any]] = field(default_factory=list)

    retry_count: int = 0
    max_retries: int = 0
    retry_delay: int = 0
    next_retry_tick: int = 0
    timeout_ticks: int = 0
    wait_until_tick: int = 0
    last_error: str = ""

    replan_count: int = 0
    replanned: bool = False
    replan_reason: str = ""
    max_replans: int = 0

    created_tick: int = 0
    last_run_tick: Optional[int] = None
    last_failure_tick: Optional[int] = None
    finished_tick: Optional[int] = None

    workspace_dir: str = ""
    task_dir: str = ""
    runtime_state_file: str = ""
    plan_file: str = ""
    log_file: str = ""

    created_at: str = ""
    updated_at: str = ""

    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        extra = data.pop("extra", {}) or {}
        if isinstance(extra, dict):
            data.update(extra)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        if not isinstance(data, dict):
            raise TypeError("Task.from_dict expects dict")

        known_fields = {
            "task_id",
            "title",
            "goal",
            "task_name",
            "status",
            "priority",
            "steps",
            "current_step_index",
            "steps_total",
            "results",
            "step_results",
            "last_step_result",
            "final_result",
            "final_answer",
            "planner_result",
            "history",
            "execution_log",
            "retry_count",
            "max_retries",
            "retry_delay",
            "next_retry_tick",
            "timeout_ticks",
            "wait_until_tick",
            "last_error",
            "replan_count",
            "replanned",
            "replan_reason",
            "max_replans",
            "created_tick",
            "last_run_tick",
            "last_failure_tick",
            "finished_tick",
            "workspace_dir",
            "task_dir",
            "runtime_state_file",
            "plan_file",
            "log_file",
            "created_at",
            "updated_at",
            "extra",
        }

        payload = copy.deepcopy(data)

        task_id = str(
            payload.get("task_id")
            or payload.get("id")
            or payload.get("task_name")
            or ""
        ).strip()
        if not task_id:
            raise ValueError("Task dict missing task_id/id/task_name")

        task_name = str(payload.get("task_name") or task_id).strip()
        title = str(payload.get("title") or payload.get("goal") or task_name).strip()
        goal = str(payload.get("goal") or title).strip()

        extra = {k: copy.deepcopy(v) for k, v in payload.items() if k not in known_fields and k != "id"}

        return cls(
            task_id=task_id,
            title=title,
            goal=goal,
            task_name=task_name,
            status=str(payload.get("status", TASK_STATUS_QUEUED)),
            priority=int(payload.get("priority", 0)),
            steps=copy.deepcopy(payload.get("steps", [])) if isinstance(payload.get("steps", []), list) else [],
            current_step_index=int(payload.get("current_step_index", 0)),
            steps_total=int(payload.get("steps_total", len(payload.get("steps", [])) if isinstance(payload.get("steps", []), list) else 0)),
            results=copy.deepcopy(payload.get("results", [])) if isinstance(payload.get("results", []), list) else [],
            step_results=copy.deepcopy(payload.get("step_results", [])) if isinstance(payload.get("step_results", []), list) else [],
            last_step_result=copy.deepcopy(payload.get("last_step_result")),
            final_result=copy.deepcopy(payload.get("final_result")),
            final_answer=str(payload.get("final_answer", "")),
            planner_result=copy.deepcopy(payload.get("planner_result", {})) if isinstance(payload.get("planner_result", {}), dict) else {},
            history=_normalize_history(payload.get("history", [TASK_STATUS_QUEUED])),
            execution_log=copy.deepcopy(payload.get("execution_log", [])) if isinstance(payload.get("execution_log", []), list) else [],
            retry_count=int(payload.get("retry_count", 0)),
            max_retries=int(payload.get("max_retries", payload.get("retry", payload.get("max_retry", 0)))),
            retry_delay=int(payload.get("retry_delay", payload.get("delay", 0))),
            next_retry_tick=int(payload.get("next_retry_tick", 0)),
            timeout_ticks=int(payload.get("timeout_ticks", payload.get("timeout", 0))),
            wait_until_tick=int(payload.get("wait_until_tick", 0)),
            last_error=str(payload.get("last_error", "")),
            replan_count=int(payload.get("replan_count", 0)),
            replanned=bool(payload.get("replanned", False)),
            replan_reason=str(payload.get("replan_reason", "")),
            max_replans=int(payload.get("max_replans", 0)),
            created_tick=int(payload.get("created_tick", 0)),
            last_run_tick=payload.get("last_run_tick"),
            last_failure_tick=payload.get("last_failure_tick"),
            finished_tick=payload.get("finished_tick"),
            workspace_dir=str(payload.get("workspace_dir", "")),
            task_dir=str(payload.get("task_dir", "")),
            runtime_state_file=str(payload.get("runtime_state_file", "")),
            plan_file=str(payload.get("plan_file", "")),
            log_file=str(payload.get("log_file", "")),
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
            extra=extra,
        )


class TaskManager:
    """
    ZERO Task Manager

    這版重點：
    - tasks.json 放在 workspace/data/tasks.json
    - 建立 task 時就補齊：
        workspace_dir
        task_dir
        runtime_state_file
        plan_file
        log_file
    - 與 TaskScheduler / TaskRunner / TaskRuntime 相容
    """

    def __init__(
        self,
        workspace_root: str = "workspace",
        tasks_file: Optional[str] = None,
        auto_create_dirs: bool = True,
    ) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        self.data_dir = os.path.join(self.workspace_root, "data")
        self.tasks_workspace_dir = os.path.join(self.workspace_root, "tasks")
        self.tasks_file = os.path.abspath(tasks_file) if tasks_file else os.path.join(self.data_dir, "tasks.json")
        self.auto_create_dirs = auto_create_dirs

        if self.auto_create_dirs:
            os.makedirs(self.workspace_root, exist_ok=True)
            os.makedirs(self.data_dir, exist_ok=True)
            os.makedirs(self.tasks_workspace_dir, exist_ok=True)

        self._db = self._load_db()

    # ============================================================
    # public api
    # ============================================================

    def create_task(
        self,
        goal: str,
        *,
        title: Optional[str] = None,
        steps: Optional[List[Dict[str, Any]]] = None,
        planner_result: Optional[Dict[str, Any]] = None,
        priority: int = 0,
        max_retries: int = 0,
        retry_delay: int = 0,
        timeout_ticks: int = 0,
        max_replans: int = 0,
        status: str = TASK_STATUS_QUEUED,
        **extra: Any,
    ) -> Task:
        goal_text = str(goal or "").strip()
        if not goal_text:
            raise ValueError("goal cannot be empty")

        task_id = self._next_task_id()
        task_name = task_id

        task_dir = os.path.join(self.tasks_workspace_dir, task_name)
        runtime_state_file = os.path.join(task_dir, "runtime_state.json")
        plan_file = os.path.join(task_dir, "plan.json")
        log_file = os.path.join(task_dir, "task.log")

        if self.auto_create_dirs:
            os.makedirs(task_dir, exist_ok=True)

        safe_steps = copy.deepcopy(steps if isinstance(steps, list) else [])
        safe_planner_result = copy.deepcopy(planner_result if isinstance(planner_result, dict) else {})

        task = Task(
            task_id=task_id,
            task_name=task_name,
            title=str(title or goal_text),
            goal=goal_text,
            status=status,
            priority=int(priority),
            steps=safe_steps,
            current_step_index=0,
            steps_total=len(safe_steps),
            planner_result=safe_planner_result,
            history=[status] if status else [TASK_STATUS_QUEUED],
            execution_log=[],
            retry_count=0,
            max_retries=int(max_retries),
            retry_delay=int(retry_delay),
            next_retry_tick=0,
            timeout_ticks=int(timeout_ticks),
            wait_until_tick=0,
            last_error="",
            replan_count=0,
            replanned=False,
            replan_reason="",
            max_replans=int(max_replans),
            created_tick=0,
            last_run_tick=None,
            last_failure_tick=None,
            finished_tick=None,
            workspace_dir=self.tasks_workspace_dir,
            task_dir=task_dir,
            runtime_state_file=runtime_state_file,
            plan_file=plan_file,
            log_file=log_file,
            created_at="",
            updated_at="",
            extra=copy.deepcopy(extra),
        )

        self._upsert_task(task)
        return copy.deepcopy(task)

    def add_task(self, task: Union[Task, Dict[str, Any]]) -> Task:
        normalized = self._normalize_task_input(task)
        self._ensure_task_paths(normalized)
        self._upsert_task(normalized)
        return copy.deepcopy(normalized)

    def save_task(self, task: Union[Task, Dict[str, Any]]) -> Task:
        normalized = self._normalize_task_input(task)
        self._ensure_task_paths(normalized)
        self._upsert_task(normalized)
        return copy.deepcopy(normalized)

    def load_task(self, task_id_or_name: str) -> Optional[Task]:
        task_dict = self._find_task_dict(task_id_or_name)
        if task_dict is None:
            return None
        task = Task.from_dict(task_dict)
        self._ensure_task_paths(task)
        return task

    def get_task(self, task_id_or_name: str) -> Optional[Task]:
        return self.load_task(task_id_or_name)

    def get_task_dict(self, task_id_or_name: str) -> Optional[Dict[str, Any]]:
        task = self.load_task(task_id_or_name)
        if task is None:
            return None
        return task.to_dict()

    def list_tasks(self) -> List[Task]:
        items: List[Task] = []
        for raw in self._db.get("tasks", []):
            try:
                task = Task.from_dict(raw)
                self._ensure_task_paths(task)
                items.append(task)
            except Exception:
                continue
        return items

    def list_task_dicts(self) -> List[Dict[str, Any]]:
        return [task.to_dict() for task in self.list_tasks()]

    def get_pending_tasks(self) -> List[Task]:
        tasks = [task for task in self.list_tasks() if task.status in PENDING_STATUSES]
        tasks.sort(key=lambda x: (-int(x.priority), x.task_id))
        return tasks

    def update_task_status(
        self,
        task_id_or_name: str,
        status: str,
        *,
        error: Optional[str] = None,
    ) -> Optional[Task]:
        task = self.load_task(task_id_or_name)
        if task is None:
            return None

        old_status = task.status
        new_status = str(status or old_status).strip() or old_status
        task.status = new_status

        if error is not None:
            task.last_error = str(error)

        if not task.history:
            task.history = [new_status]
        elif task.history[-1] != new_status and f"{old_status} -> {new_status}" != task.history[-1]:
            task.history.append(f"{old_status} -> {new_status}")

        self._upsert_task(task)
        return copy.deepcopy(task)

    def update_task(self, task_id_or_name: str, updates: Dict[str, Any]) -> Optional[Task]:
        if not isinstance(updates, dict):
            raise TypeError("updates must be dict")

        task = self.load_task(task_id_or_name)
        if task is None:
            return None

        task_dict = task.to_dict()
        for key, value in updates.items():
            task_dict[key] = copy.deepcopy(value)

        updated = self._normalize_task_input(task_dict)
        self._ensure_task_paths(updated)
        self._upsert_task(updated)
        return copy.deepcopy(updated)

    def delete_task(self, task_id_or_name: str) -> bool:
        items = self._db.get("tasks", [])
        before = len(items)

        self._db["tasks"] = [
            item for item in items
            if str(item.get("task_id") or item.get("id") or item.get("task_name")) != str(task_id_or_name)
            and str(item.get("task_name") or item.get("task_id") or item.get("id")) != str(task_id_or_name)
        ]

        changed = len(self._db["tasks"]) != before
        if changed:
            self._save_db()
        return changed

    def append_execution_log(
        self,
        task_id_or_name: str,
        event: Dict[str, Any],
    ) -> Optional[Task]:
        task = self.load_task(task_id_or_name)
        if task is None:
            return None

        if not isinstance(task.execution_log, list):
            task.execution_log = []

        task.execution_log.append(copy.deepcopy(event if isinstance(event, dict) else {"event": str(event)}))
        self._upsert_task(task)
        return copy.deepcopy(task)

    def append_step_result(
        self,
        task_id_or_name: str,
        result: Dict[str, Any],
    ) -> Optional[Task]:
        task = self.load_task(task_id_or_name)
        if task is None:
            return None

        safe_result = copy.deepcopy(result if isinstance(result, dict) else {"result": result})

        if not isinstance(task.step_results, list):
            task.step_results = []
        if not isinstance(task.results, list):
            task.results = []

        task.step_results.append(safe_result)
        task.results.append(safe_result)
        task.last_step_result = copy.deepcopy(safe_result)

        self._upsert_task(task)
        return copy.deepcopy(task)

    def set_final_answer(self, task_id_or_name: str, final_answer: str) -> Optional[Task]:
        task = self.load_task(task_id_or_name)
        if task is None:
            return None

        task.final_answer = str(final_answer or "")
        self._upsert_task(task)
        return copy.deepcopy(task)

    def sync_runtime_to_task(
        self,
        task_id_or_name: str,
        runtime_state: Dict[str, Any],
    ) -> Optional[Task]:
        """
        把 runtime_state.json 的關鍵欄位同步回 tasks.json
        """
        task = self.load_task(task_id_or_name)
        if task is None:
            return None

        if not isinstance(runtime_state, dict):
            return copy.deepcopy(task)

        for key in (
            "status",
            "retry_count",
            "max_retries",
            "retry_delay",
            "next_retry_tick",
            "timeout_ticks",
            "wait_until_tick",
            "last_error",
            "current_step_index",
            "steps_total",
            "last_step_result",
            "final_answer",
            "replan_count",
            "replanned",
            "steps",
            "results",
            "execution_log",
            "history",
            "last_run_tick",
            "last_failure_tick",
            "finished_tick",
        ):
            if key in runtime_state:
                setattr(task, key, copy.deepcopy(runtime_state[key]))

        self._ensure_task_paths(task)
        self._upsert_task(task)
        return copy.deepcopy(task)

    def export_tasks_data(self) -> Dict[str, Any]:
        return copy.deepcopy(self._db)

    # ============================================================
    # internal
    # ============================================================

    def _load_db(self) -> Dict[str, Any]:
        if not os.path.exists(self.tasks_file):
            data = {"tasks": []}
            self._write_json(self.tasks_file, data)
            return data

        try:
            with open(self.tasks_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"tasks": []}

        if not isinstance(data, dict):
            data = {"tasks": []}

        tasks = data.get("tasks", [])
        if not isinstance(tasks, list):
            tasks = []

        data["tasks"] = tasks
        return data

    def _save_db(self) -> None:
        self._write_json(self.tasks_file, self._db)

    def _write_json(self, path: str, data: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _normalize_task_input(self, task: Union[Task, Dict[str, Any]]) -> Task:
        if isinstance(task, Task):
            normalized = copy.deepcopy(task)
        elif isinstance(task, dict):
            normalized = Task.from_dict(task)
        else:
            raise TypeError("task must be Task or dict")

        self._ensure_task_paths(normalized)
        if not normalized.task_name:
            normalized.task_name = normalized.task_id
        if not normalized.title:
            normalized.title = normalized.goal or normalized.task_name
        if not normalized.goal:
            normalized.goal = normalized.title or normalized.task_name
        if not isinstance(normalized.history, list) or not normalized.history:
            normalized.history = [normalized.status or TASK_STATUS_QUEUED]
        if not isinstance(normalized.steps, list):
            normalized.steps = []
        if not isinstance(normalized.results, list):
            normalized.results = []
        if not isinstance(normalized.step_results, list):
            normalized.step_results = []
        if not isinstance(normalized.execution_log, list):
            normalized.execution_log = []
        if normalized.steps_total < len(normalized.steps):
            normalized.steps_total = len(normalized.steps)

        return normalized

    def _ensure_task_paths(self, task: Task) -> None:
        task.task_name = str(task.task_name or task.task_id).strip()
        if not task.task_name:
            task.task_name = str(task.task_id).strip()

        if not task.workspace_dir:
            task.workspace_dir = self.tasks_workspace_dir

        if not task.task_dir:
            task.task_dir = os.path.join(task.workspace_dir, task.task_name)

        if not task.runtime_state_file:
            task.runtime_state_file = os.path.join(task.task_dir, "runtime_state.json")

        if not task.plan_file:
            task.plan_file = os.path.join(task.task_dir, "plan.json")

        if not task.log_file:
            task.log_file = os.path.join(task.task_dir, "task.log")

        if self.auto_create_dirs:
            os.makedirs(task.task_dir, exist_ok=True)

    def _find_task_dict(self, task_id_or_name: str) -> Optional[Dict[str, Any]]:
        key = str(task_id_or_name).strip()
        if not key:
            return None

        for item in self._db.get("tasks", []):
            task_id = str(item.get("task_id") or item.get("id") or "").strip()
            task_name = str(item.get("task_name") or "").strip()
            if key == task_id or key == task_name:
                return copy.deepcopy(item)

        return None

    def _upsert_task(self, task: Task) -> None:
        safe_task = self._normalize_task_input(task)
        task_dict = safe_task.to_dict()

        replaced = False
        items = self._db.get("tasks", [])
        for i, item in enumerate(items):
            existing_id = str(item.get("task_id") or item.get("id") or "").strip()
            existing_name = str(item.get("task_name") or "").strip()
            if safe_task.task_id == existing_id or safe_task.task_name == existing_name:
                items[i] = copy.deepcopy(task_dict)
                replaced = True
                break

        if not replaced:
            items.append(copy.deepcopy(task_dict))

        self._db["tasks"] = items
        self._save_db()

    def _next_task_id(self) -> str:
        max_num = 0
        for item in self._db.get("tasks", []):
            raw = str(item.get("task_id") or item.get("id") or item.get("task_name") or "")
            if raw.startswith("task_"):
                suffix = raw.split("task_", 1)[-1]
                if suffix.isdigit():
                    max_num = max(max_num, int(suffix))
        return f"task_{max_num + 1:04d}"


def _normalize_history(value: Any) -> List[str]:
    if isinstance(value, list):
        result = [str(x) for x in value if str(x).strip()]
        return result or [TASK_STATUS_QUEUED]

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return [TASK_STATUS_QUEUED]

        if "->" in text:
            parts = [part.strip() for part in text.split("->") if part.strip()]
            return parts or [TASK_STATUS_QUEUED]

        return [text]

    return [TASK_STATUS_QUEUED]