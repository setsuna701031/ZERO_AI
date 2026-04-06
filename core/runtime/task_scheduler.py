from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from .task_queue import TaskQueue
from .task_runner import TaskRunner


class TaskScheduler:
    """
    ZERO Runtime Task Scheduler

    角色：
    - 管理 ready queue
    - rebuild ready queue
    - dependency ready 判斷
    - 從 ready queue 選 task
    - 呼叫 TaskRunner 跑一個 tick
    - 不負責 step execution 細節
    - 不負責 planner
    - 不負責 repository persistence 細節

    相容需求：
    1. ZeroSystem._build_scheduler(...) 目前會傳很多 kwargs
    2. ZeroSystem.tick() 目前仍會呼叫 self.scheduler.run_one_step(task)
    3. 未來可逐步切到真正 scheduler.tick(task_repo=...)
    """

    def __init__(
        self,
        task_repo: Any = None,
        task_manager: Any = None,
        workspace_dir: Optional[str] = None,
        runtime_store: Any = None,
        queue: Optional[List[str]] = None,
        debug: bool = False,
        step_executor: Any = None,
        tool_registry: Any = None,
        task_runtime: Any = None,
        task_runner: Any = None,
        task_step_executor_adapter: Any = None,
        step_executor_adapter: Any = None,
        executor: Any = None,
        runtime_executor: Any = None,
        task_executor: Any = None,
        **kwargs: Any,
    ) -> None:
        self.task_repo = task_repo if task_repo is not None else task_manager
        self.workspace_dir = workspace_dir or "workspace"
        self.runtime_store = runtime_store
        self.debug = debug

        self.step_executor = step_executor
        self.tool_registry = tool_registry
        self.task_runtime = task_runtime
        self.task_step_executor_adapter = task_step_executor_adapter
        self.step_executor_adapter = step_executor_adapter
        self.executor = executor
        self.runtime_executor = runtime_executor
        self.task_executor = task_executor
        self.extra_kwargs = dict(kwargs)

        self.task_queue = TaskQueue()
        self.current_tick = 0

        # 相容舊欄位名稱
        self.queue = self.task_queue.snapshot()

        self.task_runner_error: Optional[str] = None
        self.task_runner_build_trace: List[str] = []

        if task_runner is not None:
            self.task_runner = task_runner
            self.task_runner_error = None
            self.task_runner_build_trace.append("external task_runner provided")
        else:
            self.task_runner = self._build_default_task_runner()

        # 若外部有傳 queue 初始內容，先放進 ready queue
        if isinstance(queue, list):
            for item in queue:
                if isinstance(item, str) and item.strip():
                    self.task_queue.enqueue(item.strip())

        self._sync_queue_snapshot()

    # ============================================================
    # public api
    # ============================================================

    def boot(self) -> Dict[str, Any]:
        self._sync_queue_snapshot()
        return {
            "ok": True,
            "message": "task scheduler booted",
            "tick": self.current_tick,
            "ready_queue": self.task_queue.snapshot(),
            "workspace_dir": self.workspace_dir,
            "has_task_runner": self.task_runner is not None,
            "task_runner_error": self.task_runner_error,
            "task_runner_build_trace": copy.deepcopy(self.task_runner_build_trace),
        }

    def status(self) -> Dict[str, Any]:
        self._sync_queue_snapshot()
        return {
            "ok": True,
            "tick": self.current_tick,
            "ready_queue": self.task_queue.snapshot(),
            "ready_queue_size": len(self.task_queue.snapshot()),
            "workspace_dir": self.workspace_dir,
            "has_task_runner": self.task_runner is not None,
            "has_task_repo": self.task_repo is not None,
            "task_runner_error": self.task_runner_error,
            "task_runner_build_trace": copy.deepcopy(self.task_runner_build_trace),
        }

    def enqueue(self, task_id: str) -> bool:
        task_id = str(task_id or "").strip()
        if not task_id:
            return False

        self.task_queue.enqueue(task_id)
        self._sync_queue_snapshot()
        return True

    def enqueue_task(self, task_id: str) -> bool:
        return self.enqueue(task_id)

    def dequeue(self) -> Optional[str]:
        task_id = self.task_queue.dequeue()
        self._sync_queue_snapshot()
        return task_id

    def list_queue(self) -> List[str]:
        self._sync_queue_snapshot()
        return self.task_queue.snapshot()

    def rebuild_ready_queue(self, task_repo: Any = None) -> List[str]:
        """
        從 task repository 掃描可執行 task，放進 ready queue。

        規則：
        - queued / ready / retrying 可進候選
        - blocked / waiting 若 dependency 已滿足，也可進 ready
        - terminal status 不進 queue
        """
        repo = task_repo if task_repo is not None else self.task_repo
        if repo is None:
            self._sync_queue_snapshot()
            return self.task_queue.snapshot()

        tasks = self._repo_list_tasks(repo)

        for task in tasks:
            if not isinstance(task, dict):
                continue

            task_id = self._task_id(task)
            if not task_id:
                continue

            status = self._normalize_status(task.get("status"))
            if self._is_terminal_status(status):
                continue

            deps = self._normalize_depends_on(task.get("depends_on", []))
            deps_ready = self._dependencies_ready(repo, deps)

            if status in ("queued", "ready", "retrying"):
                if deps_ready:
                    self.task_queue.enqueue(task_id)
                continue

            if status in ("blocked", "waiting"):
                if deps_ready:
                    self.task_queue.enqueue(task_id)
                continue

        self._sync_queue_snapshot()
        return self.task_queue.snapshot()

    def tick(
        self,
        task_repo: Any = None,
        current_tick: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        真正的 scheduler tick：

        1. rebuild ready queue
        2. dequeue 一個 task
        3. load task
        4. 呼叫 runner.run_task_tick(...)
        """
        if current_tick is None:
            self.current_tick += 1
        else:
            self.current_tick = int(current_tick)

        repo = task_repo if task_repo is not None else self.task_repo

        self.rebuild_ready_queue(task_repo=repo)

        task_id = self.task_queue.dequeue()
        self._sync_queue_snapshot()

        if not task_id:
            return {
                "ok": True,
                "action": "scheduler_idle",
                "tick": self.current_tick,
                "message": "no ready task",
                "ready_queue": self.task_queue.snapshot(),
            }

        if repo is None:
            return {
                "ok": False,
                "action": "scheduler_error",
                "tick": self.current_tick,
                "message": "task repo not available",
                "task_id": task_id,
                "ready_queue": self.task_queue.snapshot(),
            }

        task = self._repo_get_task(repo, task_id)
        if not isinstance(task, dict):
            return {
                "ok": False,
                "action": "scheduler_error",
                "tick": self.current_tick,
                "message": f"task not found: {task_id}",
                "task_id": task_id,
                "ready_queue": self.task_queue.snapshot(),
            }

        return self.run_one_step(task=copy.deepcopy(task), current_tick=self.current_tick)

    def run_one(self, task: Dict[str, Any], current_tick: Optional[int] = None) -> Dict[str, Any]:
        return self.run_one_step(task=task, current_tick=current_tick)

    def run_one_step(
        self,
        task: Dict[str, Any],
        current_tick: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        相容你現在 ZeroSystem.tick() 的入口。
        目前 ZeroSystem 還是直接呼叫這個，所以這裡一定要保留。
        """
        if current_tick is None:
            self.current_tick += 1
        else:
            self.current_tick = int(current_tick)

        if not isinstance(task, dict):
            return {
                "ok": False,
                "action": "scheduler_invalid_task",
                "tick": self.current_tick,
                "message": "task must be dict",
                "error": "task must be dict",
            }

        task_id = self._task_id(task)
        task_name = task.get("task_name") or task_id or "unknown_task"

        if not task_id:
            return {
                "ok": False,
                "action": "scheduler_invalid_task",
                "tick": self.current_tick,
                "message": "task_id missing",
                "error": "task_id missing",
                "task_name": task_name,
            }

        if self.task_runner is None:
            self.task_runner = self._build_default_task_runner()

        if self.task_runner is None:
            return {
                "ok": False,
                "action": "scheduler_no_runner",
                "tick": self.current_tick,
                "message": "task_runner not available",
                "error": self.task_runner_error or "task_runner not available",
                "task_id": task_id,
                "task_name": task_name,
                "task_runner_build_trace": copy.deepcopy(self.task_runner_build_trace),
            }

        status = self._normalize_status(task.get("status"))
        if self._is_terminal_status(status):
            return {
                "ok": False,
                "action": "scheduler_skip_terminal",
                "tick": self.current_tick,
                "message": f"task already terminal: {status}",
                "task_id": task_id,
                "task_name": task_name,
                "status": status,
            }

        dependency_status_map = self._build_dependency_status_map(task)

        self._trace(task, "scheduler_before_runner", {
            "tick": self.current_tick,
            "task_id": task_id,
            "task_name": task_name,
            "status": status,
            "dependency_status_map": dependency_status_map,
            "ready_queue": self.task_queue.snapshot(),
        })

        # 先讓 runtime 做 dependency 判斷，避免 runner 永遠拿空 map
        if self.task_runtime is not None and hasattr(self.task_runtime, "check_blocked_by_dependencies"):
            try:
                dep_result = self.task_runtime.check_blocked_by_dependencies(
                    task=copy.deepcopy(task),
                    dependency_status_map=dependency_status_map,
                    current_tick=self.current_tick,
                )
                self._trace(task, "scheduler_dependency_check", dep_result)

                if isinstance(dep_result, dict) and dep_result.get("blocked") is True:
                    return {
                        "ok": True,
                        "action": "task_blocked",
                        "tick": self.current_tick,
                        "task_id": task_id,
                        "task_name": task_name,
                        "status": dep_result.get("status", "blocked"),
                        "message": dep_result.get("message", "task blocked"),
                        "final_answer": "",
                        "execution_log": [],
                        "current_step_index": task.get("current_step_index", 0),
                        "step_count": len(task.get("steps", [])) if isinstance(task.get("steps"), list) else 0,
                        "raw_result": dep_result,
                    }
            except Exception as e:
                self._trace(task, "scheduler_dependency_check_exception", {"error": str(e)})

        # 正式交給 runner 跑一個 tick
        try:
            runner_result = self.task_runner.run_task_tick(
                task=copy.deepcopy(task),
                current_tick=self.current_tick,
            )
        except Exception as e:
            error_result = {
                "ok": False,
                "action": "scheduler_runner_exception",
                "tick": self.current_tick,
                "task_id": task_id,
                "task_name": task_name,
                "status": "failed",
                "message": "task runner exception",
                "error": str(e),
            }
            self._trace(task, "scheduler_runner_exception", error_result)
            return error_result

        normalized = self._normalize_runner_result(task, runner_result)

        self._trace(task, "scheduler_after_runner", normalized)
        return normalized

    # ============================================================
    # helpers
    # ============================================================

    def _build_default_task_runner(self) -> Optional[TaskRunner]:
        self.task_runner_build_trace = []

        candidate_executor_names = [
            "step_executor",
            "task_step_executor_adapter",
            "step_executor_adapter",
            "executor",
            "runtime_executor",
            "task_executor",
        ]

        candidate_executors: List[Tuple[str, Any]] = []
        for name in candidate_executor_names:
            value = getattr(self, name, None)
            if value is not None:
                candidate_executors.append((name, value))

        if not candidate_executors:
            self.task_runner_error = (
                "no executor available; checked: "
                + ", ".join(candidate_executor_names)
            )
            self.task_runner_build_trace.append(self.task_runner_error)
            return None

        constructor_attempts: List[Dict[str, Any]] = []

        for executor_name, executor_value in candidate_executors:
            constructor_attempts.extend(
                [
                    {
                        "label": f"{executor_name}: step_executor + task_runtime + replanner + verifier + debug",
                        "kwargs": {
                            "step_executor": executor_value,
                            "task_runtime": self.task_runtime,
                            "replanner": self.extra_kwargs.get("replanner"),
                            "verifier": self.extra_kwargs.get("verifier"),
                            "debug": bool(self.debug),
                        },
                    },
                    {
                        "label": f"{executor_name}: step_executor + task_runtime + debug",
                        "kwargs": {
                            "step_executor": executor_value,
                            "task_runtime": self.task_runtime,
                            "debug": bool(self.debug),
                        },
                    },
                    {
                        "label": f"{executor_name}: step_executor + task_runtime",
                        "kwargs": {
                            "step_executor": executor_value,
                            "task_runtime": self.task_runtime,
                        },
                    },
                    {
                        "label": f"{executor_name}: step_executor only",
                        "kwargs": {
                            "step_executor": executor_value,
                        },
                    },
                    {
                        "label": f"{executor_name}: executor + task_runtime + debug",
                        "kwargs": {
                            "executor": executor_value,
                            "task_runtime": self.task_runtime,
                            "debug": bool(self.debug),
                        },
                    },
                    {
                        "label": f"{executor_name}: executor only",
                        "kwargs": {
                            "executor": executor_value,
                        },
                    },
                ]
            )

        errors: List[str] = []

        for attempt in constructor_attempts:
            label = str(attempt.get("label") or "unknown_attempt")
            kwargs = dict(attempt.get("kwargs") or {})
            try:
                runner = TaskRunner(**kwargs)
                self.task_runner_error = None
                self.task_runner_build_trace.append(f"build success: {label}")
                return runner
            except Exception as e:
                err = f"{label} -> {type(e).__name__}: {e}"
                errors.append(err)
                self.task_runner_build_trace.append(err)

        self.task_runner_error = "failed to build TaskRunner; " + " | ".join(errors)
        return None

    def _normalize_runner_result(
        self,
        task: Dict[str, Any],
        runner_result: Any,
    ) -> Dict[str, Any]:
        task_id = self._task_id(task)
        task_name = task.get("task_name") or task_id or "unknown_task"
        step_count = len(task.get("steps", [])) if isinstance(task.get("steps"), list) else 0
        current_step_index = int(task.get("current_step_index", 0) or 0)

        if not isinstance(runner_result, dict):
            return {
                "ok": False,
                "action": "scheduler_invalid_runner_result",
                "tick": self.current_tick,
                "task_id": task_id,
                "task_name": task_name,
                "status": "failed",
                "message": "runner returned invalid result",
                "error": f"invalid runner result type: {type(runner_result).__name__}",
                "final_answer": "",
                "execution_log": [],
                "current_step_index": current_step_index,
                "step_count": step_count,
                "raw_result": runner_result,
            }

        state_from_runner = runner_result.get("task")
        if isinstance(state_from_runner, dict):
            current_step_index = int(state_from_runner.get("current_step_index", current_step_index) or 0)
            state_steps = state_from_runner.get("steps", [])
            state_steps_total = state_from_runner.get("steps_total")
            if isinstance(state_steps_total, int):
                step_count = state_steps_total
            elif isinstance(state_steps, list):
                step_count = len(state_steps)

        status = runner_result.get("status")
        if not status and isinstance(state_from_runner, dict):
            status = state_from_runner.get("status")
        if not status:
            status = self._normalize_status(task.get("status"))

        execution_log = []
        if isinstance(runner_result.get("execution_log"), list):
            execution_log = copy.deepcopy(runner_result.get("execution_log"))
        elif isinstance(state_from_runner, dict) and isinstance(state_from_runner.get("execution_log"), list):
            execution_log = copy.deepcopy(state_from_runner.get("execution_log"))

        final_answer = runner_result.get("final_answer", "")
        if not final_answer and isinstance(state_from_runner, dict):
            final_answer = state_from_runner.get("final_answer", "")

        return {
            "ok": bool(runner_result.get("ok", False)),
            "action": runner_result.get("action", ""),
            "tick": self.current_tick,
            "task_id": task_id,
            "task_name": runner_result.get("task_name") or task_name,
            "status": status,
            "message": runner_result.get("message", ""),
            "error": runner_result.get("error"),
            "final_answer": final_answer,
            "execution_log": execution_log,
            "current_step_index": current_step_index,
            "step_count": step_count,
            "raw_result": copy.deepcopy(runner_result),
        }

    def _build_dependency_status_map(self, task: Dict[str, Any]) -> Dict[str, str]:
        repo = self.task_repo
        if repo is None:
            return {}

        depends_on = self._normalize_depends_on(task.get("depends_on", []))
        if not depends_on:
            return {}

        status_map: Dict[str, str] = {}
        for dep_task_id in depends_on:
            dep_task = self._repo_get_task(repo, dep_task_id)
            if isinstance(dep_task, dict):
                status_map[dep_task_id] = self._normalize_status(dep_task.get("status"))
            else:
                status_map[dep_task_id] = "unknown"
        return status_map

    def _dependencies_ready(self, repo: Any, deps: List[str]) -> bool:
        if not deps:
            return True

        for dep_task_id in deps:
            dep_task = self._repo_get_task(repo, dep_task_id)
            if not isinstance(dep_task, dict):
                return False

            dep_status = self._normalize_status(dep_task.get("status"))
            if dep_status != "finished":
                return False

        return True

    def _repo_list_tasks(self, repo: Any) -> List[Dict[str, Any]]:
        if repo is None:
            return []

        if hasattr(repo, "list_tasks"):
            try:
                tasks = repo.list_tasks()
                if isinstance(tasks, list):
                    return [t for t in tasks if isinstance(t, dict)]
            except Exception:
                return []

        if hasattr(repo, "tasks"):
            try:
                tasks_obj = getattr(repo, "tasks")
                if isinstance(tasks_obj, dict):
                    return [t for t in tasks_obj.values() if isinstance(t, dict)]
                if isinstance(tasks_obj, list):
                    return [t for t in tasks_obj if isinstance(t, dict)]
            except Exception:
                return []

        return []

    def _repo_get_task(self, repo: Any, task_id: str) -> Optional[Dict[str, Any]]:
        if repo is None:
            return None

        if hasattr(repo, "get_task"):
            try:
                task = repo.get_task(task_id)
                if isinstance(task, dict):
                    return task
            except Exception:
                return None

        if hasattr(repo, "tasks"):
            try:
                tasks_obj = getattr(repo, "tasks")
                if isinstance(tasks_obj, dict):
                    task = tasks_obj.get(task_id)
                    if isinstance(task, dict):
                        return task
            except Exception:
                return None

        return None

    def _task_id(self, task: Dict[str, Any]) -> str:
        return str(
            task.get("task_id")
            or task.get("task_name")
            or task.get("id")
            or ""
        ).strip()

    def _normalize_status(self, status: Any) -> str:
        return str(status or "").strip().lower()

    def _normalize_depends_on(self, value: Any) -> List[str]:
        if value is None:
            return []

        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []

        if isinstance(value, list):
            result: List[str] = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    result.append(item.strip())
            return result

        return []

    def _is_terminal_status(self, status: str) -> bool:
        return status in ("finished", "failed", "cancelled", "timeout")

    def _sync_queue_snapshot(self) -> None:
        self.queue = self.task_queue.snapshot()

    def _trace(self, task: Dict[str, Any], label: str, payload: Dict[str, Any]) -> None:
        if not self.debug:
            return

        task_name = task.get("task_name") or task.get("task_id") or task.get("id") or "unknown_task"
        print(f"[TaskScheduler] {task_name} | {label} | {payload}")