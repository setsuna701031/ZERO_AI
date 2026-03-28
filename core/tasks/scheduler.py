from __future__ import annotations

import heapq
import time
from typing import Any, Dict, List, Optional, Tuple


class TaskScheduler:
    """
    ZERO Priority + Dependency + Preemptive + Retry Scheduler

    支援：
    - priority queue
    - preemption
    - pause / resume
    - dependency waiting / release
    - retry policy
    - blocked state when dependency failed/canceled/blocked

    狀態：
    - waiting   : 等 dependency
    - queued    : 可執行，等待 scheduler
    - running   : 執行中
    - paused    : 被高優先任務搶占
    - retrying  : 失敗後等待重試
    - finished  : 完成
    - failed    : 最終失敗
    - canceled  : 取消
    - blocked   : 因 dependency 失敗而無法再執行
    """

    def __init__(self, task_manager: Any = None, task_runtime: Any = None) -> None:
        self.task_manager = task_manager
        self.task_runtime = task_runtime

        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._pending_heap: List[Tuple[int, int, str]] = []
        self._paused_stack: List[str] = []
        self._current_task_name: Optional[str] = None
        self._sequence: int = 0
        self._task_counter: int = 0
        self._tick_counter: int = 0

    # =========================================================
    # Public
    # =========================================================

    def submit_task(
        self,
        task_or_goal: Dict[str, Any] | str,
        priority: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        dependencies: Optional[List[str]] = None,
        max_retries: Optional[int] = None,
        retry_delay_ticks: Optional[int] = None,
    ) -> Dict[str, Any]:
        task = self._normalize_task_input(
            task_or_goal=task_or_goal,
            priority=priority,
            metadata=metadata,
            dependencies=dependencies,
            max_retries=max_retries,
            retry_delay_ticks=retry_delay_ticks,
        )

        task_name = str(task.get("task_name", "")).strip()
        if not task_name:
            raise ValueError("Task must contain non-empty task_name.")

        self._tasks[task_name] = task
        self._sync_task_to_manager(task_name)

        dep_block_reason = self._dependency_block_reason(task)
        deps_ready = self._dependencies_satisfied(task)

        if dep_block_reason:
            self._set_task_status(task_name, "blocked")
            self._append_task_log(
                task_name,
                f"Task blocked on submit: {task_name} | reason={dep_block_reason}",
            )
            action = "blocked"
            summary = f"Task blocked by dependency state: {task_name}"
        elif deps_ready:
            self._set_task_status(task_name, "queued")
            self._push_pending(task_name)
            action = "queued"
            summary = f"Task queued: {task_name}"
        else:
            self._set_task_status(task_name, "waiting")
            action = "waiting"
            summary = f"Task waiting for dependencies: {task_name}"

        running_task = self.get_current_task()
        if running_task is not None and deps_ready and not dep_block_reason:
            running_priority = self._get_priority(running_task)
            new_priority = self._get_priority(task)

            if new_priority > running_priority:
                preempted_task = self._preempt_current_task(
                    reason=f"higher_priority_task_arrived:{task_name}"
                )
                return {
                    "success": True,
                    "action": "queued_and_preempted",
                    "task": self.get_task(task_name),
                    "preempted_task": preempted_task,
                    "summary": (
                        f"Task queued with preemption: {task_name} "
                        f"(priority={new_priority})"
                    ),
                    "error": None,
                }

        return {
            "success": True,
            "action": action,
            "task": self.get_task(task_name),
            "summary": summary,
            "error": None,
        }

    def run_once(self) -> Dict[str, Any]:
        self._tick_counter += 1

        if self.task_runtime is None:
            return {
                "success": False,
                "status": "scheduler_error",
                "summary": "Task runtime is not configured.",
                "data": {},
                "error": "task_runtime is required",
            }

        self._promote_retrying_tasks()
        self._release_waiting_tasks()
        self._block_waiting_tasks_due_to_failed_dependencies()

        current_task = self.get_current_task()

        if current_task is None:
            next_task = self._select_next_task()
            if next_task is None:
                self._promote_retrying_tasks()
                self._release_waiting_tasks()
                self._block_waiting_tasks_due_to_failed_dependencies()
                return {
                    "success": True,
                    "status": "idle",
                    "summary": "Scheduler idle: no runnable task.",
                    "data": {
                        "current_task": None,
                        "queued_count": self.get_queued_count(),
                        "paused_count": self.get_paused_count(),
                        "waiting_count": self.get_waiting_count(),
                        "retrying_count": self.get_retrying_count(),
                        "blocked_count": self.get_blocked_count(),
                        "tick": self._tick_counter,
                    },
                    "error": None,
                }

            self._current_task_name = str(next_task.get("task_name", "")).strip()
            self._set_task_status(self._current_task_name, "running")
            current_task = self.get_task(self._current_task_name)

        if current_task is None:
            return {
                "success": False,
                "status": "scheduler_error",
                "summary": "Current task missing after selection.",
                "data": {"tick": self._tick_counter},
                "error": "current_task_missing",
            }

        task_name = str(current_task.get("task_name", "")).strip()

        try:
            runtime_result = self._run_runtime(current_task)
        except Exception as exc:
            runtime_result = {
                "success": False,
                "status": "failed",
                "summary": f"Task execution failed: {task_name}",
                "data": {},
                "error": str(exc),
            }

        normalized = self._normalize_runtime_result(runtime_result)

        self._refresh_task_from_manager(task_name)

        latest_task = self.get_task(task_name)
        latest_status = str((latest_task or {}).get("status", "")).strip().lower()
        runtime_status = str(normalized.get("status", "")).strip().lower()

        if latest_task is not None and runtime_status in {"finished", "canceled", "retrying"}:
            self._set_task_status(task_name, runtime_status)
            self._refresh_task_from_manager(task_name)
            latest_task = self.get_task(task_name)
            latest_status = str((latest_task or {}).get("status", "")).strip().lower()

        final_status = latest_status or runtime_status or "running"

        if final_status == "finished":
            self._append_task_log(task_name, f"Task finished: {task_name}")
            self._current_task_name = None
            self._promote_retrying_tasks()
            self._release_waiting_tasks()
            self._block_waiting_tasks_due_to_failed_dependencies()
            self._resume_next_paused_if_any()

        elif final_status == "failed":
            retry_result = self._handle_task_failure(task_name, normalized.get("error"))
            self._refresh_task_from_manager(task_name)
            latest_task = self.get_task(task_name)
            final_status = retry_result["status"]
            normalized["summary"] = retry_result["summary"]
            normalized["error"] = retry_result["error"]
            normalized["success"] = final_status not in {"failed"}
            self._current_task_name = None

            self._promote_retrying_tasks()
            self._release_waiting_tasks()
            self._block_waiting_tasks_due_to_failed_dependencies()

        elif final_status == "retrying":
            self._append_task_log(task_name, f"Task entered retrying: {task_name}")
            self._current_task_name = None
            normalized["success"] = False

            self._promote_retrying_tasks()
            self._release_waiting_tasks()
            self._block_waiting_tasks_due_to_failed_dependencies()
            self._refresh_task_from_manager(task_name)

        elif final_status == "canceled":
            self._append_task_log(task_name, f"Task canceled: {task_name}")
            self._current_task_name = None
            self._promote_retrying_tasks()
            self._release_waiting_tasks()
            self._block_waiting_tasks_due_to_failed_dependencies()

        else:
            self._refresh_task_from_manager(task_name)
            latest_task = self.get_task(task_name)
            final_status = str((latest_task or {}).get("status", final_status)).strip().lower() or final_status

        return {
            "success": normalized["success"],
            "status": final_status,
            "summary": normalized["summary"],
            "data": {
                "task": self.get_task(task_name),
                "runtime_result": normalized["data"],
                "current_task": self.get_current_task(),
                "queued_count": self.get_queued_count(),
                "paused_count": self.get_paused_count(),
                "waiting_count": self.get_waiting_count(),
                "retrying_count": self.get_retrying_count(),
                "blocked_count": self.get_blocked_count(),
                "tick": self._tick_counter,
            },
            "error": normalized["error"],
        }

    def has_work(self) -> bool:
        return (
            self._current_task_name is not None
            or bool(self._pending_heap)
            or bool(self._paused_stack)
            or self.get_waiting_count() > 0
            or self.get_retrying_count() > 0
        )

    def get_current_task(self) -> Optional[Dict[str, Any]]:
        if not self._current_task_name:
            return None
        return self.get_task(self._current_task_name)

    def get_task(self, task_name: str) -> Optional[Dict[str, Any]]:
        clean_name = str(task_name or "").strip()
        if not clean_name:
            return None

        local_task = self._tasks.get(clean_name)
        if isinstance(local_task, dict):
            return local_task

        if self.task_manager is not None:
            get_task_method = getattr(self.task_manager, "get_task", None)
            if callable(get_task_method):
                try:
                    manager_task = get_task_method(clean_name)
                    if isinstance(manager_task, dict):
                        self._tasks[clean_name] = dict(manager_task)
                        return self._tasks[clean_name]
                except Exception:
                    pass

        return None

    def get_scheduler_state(self) -> Dict[str, Any]:
        waiting_names: List[str] = []
        retrying_names: List[str] = []
        blocked_names: List[str] = []

        for name, task in self._tasks.items():
            if not isinstance(task, dict):
                continue
            status = str(task.get("status", "")).strip().lower()
            if status == "waiting":
                waiting_names.append(name)
            elif status == "retrying":
                retrying_names.append(name)
            elif status == "blocked":
                blocked_names.append(name)

        return {
            "current_task_name": self._current_task_name,
            "queued_task_names": self._peek_pending_names(),
            "paused_task_names": list(self._paused_stack),
            "waiting_task_names": waiting_names,
            "retrying_task_names": retrying_names,
            "blocked_task_names": blocked_names,
            "queued_count": self.get_queued_count(),
            "paused_count": self.get_paused_count(),
            "waiting_count": len(waiting_names),
            "retrying_count": len(retrying_names),
            "blocked_count": len(blocked_names),
            "tick": self._tick_counter,
            "has_work": self.has_work(),
        }

    def get_queued_count(self) -> int:
        return len(self._pending_heap)

    def get_paused_count(self) -> int:
        return len(self._paused_stack)

    def get_waiting_count(self) -> int:
        return self._count_status("waiting")

    def get_retrying_count(self) -> int:
        return self._count_status("retrying")

    def get_blocked_count(self) -> int:
        return self._count_status("blocked")

    # =========================================================
    # Internal - task build
    # =========================================================

    def _normalize_task_input(
        self,
        task_or_goal: Dict[str, Any] | str,
        priority: Optional[int],
        metadata: Optional[Dict[str, Any]],
        dependencies: Optional[List[str]],
        max_retries: Optional[int],
        retry_delay_ticks: Optional[int],
    ) -> Dict[str, Any]:
        if isinstance(task_or_goal, dict):
            task = dict(task_or_goal)
            task_name = str(task.get("task_name", "")).strip()
            if not task_name:
                task_name = self._generate_task_name()
                task["task_name"] = task_name

            goal = str(task.get("goal", task.get("title", task_name))).strip()
            title = str(task.get("title", goal)).strip()

            task["goal"] = goal
            task["title"] = title
        else:
            goal = str(task_or_goal).strip()
            if not goal:
                raise ValueError("Goal cannot be empty.")

            task_name = self._generate_task_name()
            task = {
                "task_name": task_name,
                "id": task_name,
                "task_id": task_name,
                "goal": goal,
                "title": goal,
                "status": "created",
                "priority": 0,
                "dependencies": [],
                "created_at": time.time(),
                "updated_at": time.time(),
            }

        task_deps = task.get("dependencies", [])
        if not isinstance(task_deps, list):
            task_deps = []

        if dependencies is not None:
            task_deps = dependencies

        normalized_deps: List[str] = []
        seen = set()
        for dep in task_deps:
            dep_name = str(dep or "").strip()
            if not dep_name:
                continue
            if dep_name == task.get("task_name"):
                continue
            if dep_name in seen:
                continue
            seen.add(dep_name)
            normalized_deps.append(dep_name)

        task["dependencies"] = normalized_deps

        if metadata and isinstance(metadata, dict):
            existing_meta = task.get("metadata", {})
            if not isinstance(existing_meta, dict):
                existing_meta = {}
            merged_meta = dict(existing_meta)
            merged_meta.update(metadata)
            task["metadata"] = merged_meta

        final_priority = self._coerce_priority(
            priority if priority is not None else task.get("priority", 0)
        )
        task["priority"] = final_priority

        final_max_retries = self._coerce_non_negative_int(
            max_retries if max_retries is not None else task.get("max_retries", 0)
        )
        final_retry_delay = self._coerce_non_negative_int(
            retry_delay_ticks
            if retry_delay_ticks is not None
            else task.get("retry_delay_ticks", 0)
        )

        task["max_retries"] = final_max_retries
        task["retry_delay_ticks"] = final_retry_delay
        task["retry_count"] = self._coerce_non_negative_int(task.get("retry_count", 0))
        task["next_retry_tick"] = self._coerce_non_negative_int(task.get("next_retry_tick", 0))
        task["last_error"] = task.get("last_error")

        if "created_at" not in task:
            task["created_at"] = time.time()
        task["updated_at"] = time.time()

        return task

    def _generate_task_name(self) -> str:
        self._task_counter += 1

        while True:
            candidate = f"task_{self._task_counter:04d}"
            if candidate not in self._tasks:
                return candidate
            self._task_counter += 1

    # =========================================================
    # Internal - dependency
    # =========================================================

    def _dependencies_satisfied(self, task: Dict[str, Any]) -> bool:
        deps = task.get("dependencies", [])
        if not isinstance(deps, list) or not deps:
            return True

        for dep_name in deps:
            dep_task = self.get_task(str(dep_name))
            if dep_task is None:
                return False

            dep_status = str(dep_task.get("status", "")).strip().lower()
            if dep_status != "finished":
                return False

        return True

    def _dependency_block_reason(self, task: Dict[str, Any]) -> Optional[str]:
        deps = task.get("dependencies", [])
        if not isinstance(deps, list) or not deps:
            return None

        for dep_name in deps:
            dep_task = self.get_task(str(dep_name))
            if dep_task is None:
                continue

            dep_status = str(dep_task.get("status", "")).strip().lower()
            if dep_status in {"failed", "blocked", "canceled"}:
                return f"dependency_{dep_name}_{dep_status}"

        return None

    def _release_waiting_tasks(self) -> None:
        released_any = True

        while released_any:
            released_any = False

            for task_name, task in list(self._tasks.items()):
                if not isinstance(task, dict):
                    continue

                status = str(task.get("status", "")).strip().lower()
                if status != "waiting":
                    continue

                block_reason = self._dependency_block_reason(task)
                if block_reason:
                    self._set_task_status(task_name, "blocked")
                    self._append_task_log(
                        task_name,
                        f"Task blocked: {task_name} | reason={block_reason}",
                    )
                    continue

                if self._dependencies_satisfied(task):
                    self._set_task_status(task_name, "queued")
                    self._push_pending(task_name)
                    self._append_task_log(
                        task_name,
                        f"Dependencies satisfied, task queued: {task_name}",
                    )
                    released_any = True

    def _block_waiting_tasks_due_to_failed_dependencies(self) -> None:
        for task_name, task in list(self._tasks.items()):
            if not isinstance(task, dict):
                continue

            status = str(task.get("status", "")).strip().lower()
            if status != "waiting":
                continue

            block_reason = self._dependency_block_reason(task)
            if not block_reason:
                continue

            self._set_task_status(task_name, "blocked")
            self._append_task_log(
                task_name,
                f"Task blocked: {task_name} | reason={block_reason}",
            )

    # =========================================================
    # Internal - retry
    # =========================================================

    def _handle_task_failure(self, task_name: str, error: Any) -> Dict[str, Any]:
        task = self.get_task(task_name)
        if task is None:
            return {
                "status": "failed",
                "summary": f"Task failed: {task_name}",
                "error": str(error) if error is not None else None,
            }

        retry_count = self._coerce_non_negative_int(task.get("retry_count", 0))
        max_retries = self._coerce_non_negative_int(task.get("max_retries", 0))
        retry_delay = self._coerce_non_negative_int(task.get("retry_delay_ticks", 0))

        task["last_error"] = str(error) if error is not None else None

        if retry_count < max_retries:
            retry_count += 1
            next_retry_tick = self._tick_counter + retry_delay + 1

            task["retry_count"] = retry_count
            task["next_retry_tick"] = next_retry_tick

            # 核心修正：失敗後先進 retrying，不直接 queued
            self._set_task_status(task_name, "retrying")

            self._append_task_log(
                task_name,
                (
                    f"Task retry scheduled: {task_name} | "
                    f"retry_count={retry_count}/{max_retries} | "
                    f"next_retry_tick={next_retry_tick} | "
                    f"error={task.get('last_error')}"
                ),
            )

            return {
                "status": "retrying",
                "summary": (
                    f"Task retry scheduled: {task_name} "
                    f"({retry_count}/{max_retries})"
                ),
                "error": task.get("last_error"),
            }

        self._set_task_status(task_name, "failed")
        self._append_task_log(
            task_name,
            (
                f"Task permanently failed: {task_name} | "
                f"retry_count={retry_count}/{max_retries} | "
                f"error={task.get('last_error')}"
            ),
        )

        return {
            "status": "failed",
            "summary": f"Task permanently failed: {task_name}",
            "error": task.get("last_error"),
        }

    def _promote_retrying_tasks(self) -> None:
        for task_name, task in list(self._tasks.items()):
            if not isinstance(task, dict):
                continue

            status = str(task.get("status", "")).strip().lower()
            if status != "retrying":
                continue

            next_retry_tick = self._coerce_non_negative_int(task.get("next_retry_tick", 0))

            # 還沒到時間，就維持 retrying
            if self._tick_counter < next_retry_tick:
                continue

            block_reason = self._dependency_block_reason(task)
            if block_reason:
                self._set_task_status(task_name, "blocked")
                self._append_task_log(
                    task_name,
                    f"Retrying task blocked: {task_name} | reason={block_reason}",
                )
                continue

            if not self._dependencies_satisfied(task):
                self._set_task_status(task_name, "waiting")
                self._append_task_log(
                    task_name,
                    f"Retrying task returned to waiting: {task_name}",
                )
                continue

            # 到點才重新進 queue
            self._set_task_status(task_name, "queued")
            self._push_pending(task_name)
            self._append_task_log(
                task_name,
                f"Retrying task re-queued: {task_name}",
            )

    # =========================================================
    # Internal - queue control
    # =========================================================

    def _is_in_pending_heap(self, task_name: str) -> bool:
        for _, _, existing_name in self._pending_heap:
            if existing_name == task_name:
                return True
        return False

    def _push_pending(self, task_name: str) -> None:
        task = self.get_task(task_name)
        if task is None:
            return

        if self._is_in_pending_heap(task_name):
            return

        priority = self._get_priority(task)
        heapq.heappush(self._pending_heap, (-priority, self._sequence, task_name))
        self._sequence += 1

    def _select_next_task(self) -> Optional[Dict[str, Any]]:
        if self._paused_stack:
            resumed_task_name = self._paused_stack.pop()
            resume_task = self.get_task(resumed_task_name)
            if resume_task is not None:
                self._resume_task(resume_task)
                return self.get_task(resumed_task_name)

        while self._pending_heap:
            _neg_priority, _sequence, task_name = heapq.heappop(self._pending_heap)
            task = self.get_task(task_name)
            if task is None:
                continue

            status = str(task.get("status", "")).strip().lower()

            if status in {"finished", "failed", "canceled", "blocked"}:
                continue

            if status == "retrying":
                continue

            if not self._dependencies_satisfied(task):
                block_reason = self._dependency_block_reason(task)
                if block_reason:
                    self._set_task_status(task_name, "blocked")
                    self._append_task_log(
                        task_name,
                        f"Task blocked during selection: {task_name} | reason={block_reason}",
                    )
                else:
                    self._set_task_status(task_name, "waiting")
                continue

            if status == "paused":
                self._resume_task(task)
            else:
                self._set_task_status(task_name, "running")

            return self.get_task(task_name)

        return None

    def _resume_next_paused_if_any(self) -> None:
        if not self._paused_stack:
            return

        resumed_task_name = self._paused_stack.pop()
        resumed_task = self.get_task(resumed_task_name)
        if resumed_task is None:
            return

        self._resume_task(resumed_task)
        self._push_pending(resumed_task_name)

    def _preempt_current_task(self, reason: str) -> Optional[Dict[str, Any]]:
        current_task = self.get_current_task()
        if current_task is None:
            return None

        task_name = str(current_task.get("task_name", "")).strip()
        if not task_name:
            return None

        pause_method = getattr(self.task_runtime, "pause_task", None)
        if callable(pause_method):
            try:
                pause_method(current_task, reason=reason)
            except Exception:
                pass

        self._append_task_log(task_name, f"Task paused: {task_name} | reason={reason}")
        self._set_task_status(task_name, "paused")

        if task_name not in self._paused_stack:
            self._paused_stack.append(task_name)

        self._current_task_name = None
        return self.get_task(task_name)

    def _resume_task(self, task: Dict[str, Any]) -> None:
        task_name = str(task.get("task_name", "")).strip()
        if not task_name:
            return

        resume_method = getattr(self.task_runtime, "resume_task", None)
        if callable(resume_method):
            try:
                resume_method(task)
            except Exception:
                pass

        self._append_task_log(task_name, f"Task resumed: {task_name}")
        self._set_task_status(task_name, "running")

    def _peek_pending_names(self) -> List[str]:
        ordered = sorted(self._pending_heap)
        return [item[2] for item in ordered]

    # =========================================================
    # Internal - runtime dispatch
    # =========================================================

    def _run_runtime(self, task: Dict[str, Any]) -> Any:
        runtime = self.task_runtime

        for method_name in ("run_task_slice", "run_step", "run_once", "run_task"):
            method = getattr(runtime, method_name, None)
            if callable(method):
                return method(task)

        raise RuntimeError(
            "TaskRuntime has no supported method: "
            "run_task_slice / run_step / run_once / run_task"
        )

    def _normalize_runtime_result(self, runtime_result: Any) -> Dict[str, Any]:
        if isinstance(runtime_result, dict):
            status = str(runtime_result.get("status", "")).strip().lower()
            summary = str(runtime_result.get("summary", "Task executed."))
            data = runtime_result.get("data", runtime_result)
            error = runtime_result.get("error")
            success = bool(runtime_result.get("success", status not in {"failed", "retrying"}))
            return {
                "success": success,
                "status": status,
                "summary": summary,
                "data": data,
                "error": error,
            }

        if isinstance(runtime_result, str):
            return {
                "success": True,
                "status": "finished",
                "summary": "Task executed.",
                "data": {"answer": runtime_result},
                "error": None,
            }

        if runtime_result is None:
            return {
                "success": True,
                "status": "finished",
                "summary": "Task executed with no result.",
                "data": {},
                "error": None,
            }

        return {
            "success": True,
            "status": "finished",
            "summary": "Task executed.",
            "data": {"result": runtime_result},
            "error": None,
        }

    # =========================================================
    # Internal - task status
    # =========================================================

    def _refresh_task_from_manager(self, task_name: str) -> None:
        clean_name = str(task_name or "").strip()
        if not clean_name or self.task_manager is None:
            return

        get_task_method = getattr(self.task_manager, "get_task", None)
        if not callable(get_task_method):
            return

        try:
            manager_task = get_task_method(clean_name)
        except Exception:
            return

        if not isinstance(manager_task, dict):
            return

        local_task = self._tasks.get(clean_name, {})
        if not isinstance(local_task, dict):
            local_task = {}

        merged = dict(local_task)
        merged.update(manager_task)
        self._tasks[clean_name] = merged

    def _sync_task_to_manager(self, task_name: str) -> None:
        clean_name = str(task_name or "").strip()
        if not clean_name:
            return

        task = self._tasks.get(clean_name)
        if not isinstance(task, dict):
            return

        if self.task_manager is None:
            return

        existing_task: Dict[str, Any] = {}
        get_task_method = getattr(self.task_manager, "get_task", None)
        if callable(get_task_method):
            try:
                loaded = get_task_method(clean_name)
                if isinstance(loaded, dict):
                    existing_task = dict(loaded)
            except Exception:
                existing_task = {}

        merged = dict(existing_task)
        merged.update(task)

        upsert_method = getattr(self.task_manager, "upsert_task", None)
        if callable(upsert_method):
            try:
                upsert_method(merged)
                return
            except Exception:
                pass

    def _set_task_status(self, task_name: str, status: str) -> None:
        clean_name = str(task_name or "").strip()
        if not clean_name:
            return

        self._refresh_task_from_manager(clean_name)

        if clean_name in self._tasks and isinstance(self._tasks[clean_name], dict):
            self._tasks[clean_name]["status"] = status
            self._tasks[clean_name]["updated_at"] = time.time()

        self._sync_task_to_manager(clean_name)

        if self.task_manager is not None:
            update_method = getattr(self.task_manager, "update_task_status", None)
            if callable(update_method):
                try:
                    update_method(clean_name, status)
                except Exception:
                    pass

        self._refresh_task_from_manager(clean_name)

    def _append_task_log(self, task_name: str, text: str) -> None:
        try:
            if self.task_runtime is None:
                return

            workspace_root = getattr(self.task_runtime, "workspace_root", None)
            if workspace_root is None:
                return

            task_dir = workspace_root / task_name
            task_dir.mkdir(parents=True, exist_ok=True)
            log_file = task_dir / "log.txt"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass

    def _count_status(self, target_status: str) -> int:
        count = 0
        for _, task in self._tasks.items():
            if not isinstance(task, dict):
                continue
            status = str(task.get("status", "")).strip().lower()
            if status == target_status:
                count += 1
        return count

    def _get_priority(self, task: Dict[str, Any]) -> int:
        return self._coerce_priority(task.get("priority", 0))

    def _coerce_priority(self, value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 0

    def _coerce_non_negative_int(self, value: Any) -> int:
        try:
            parsed = int(value)
            return parsed if parsed >= 0 else 0
        except Exception:
            return 0