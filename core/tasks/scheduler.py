from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from core.planning.replanner import Replanner
from core.runtime.task_scheduler import TaskScheduler as RuntimeTaskScheduler
from core.tasks.execution_guard import ExecutionGuard
from core.tasks.task_repository import TaskRepository
from core.tasks.task_workspace import TaskWorkspace
from core.tasks.task_result_summarizer import build_simple_final_answer
from core.tasks.scheduler_core.task_dispatcher import TaskDispatcher
from core.tasks.scheduler_core.task_scheduler_queue import (
    STATUS_FAILED,
    STATUS_FINISHED,
    STATUS_QUEUED,
    ScheduledTask,
    TaskSchedulerQueue,
)
from core.tasks.scheduler_core.worker_pool import WorkerPool
from core.tools.execution_trace import ExecutionTrace


SCHEDULER_BUILD = "DAG_EXECUTE_SAFETY_LOCK_V7_TASK_PLANNER_SYNC_AND_HYDRATION"

STATUS_CREATED = "created"
STATUS_BLOCKED = "blocked"

TERMINAL_STATUSES = {
    "finished",
    "done",
    "success",
    "completed",
    "failed",
    "error",
    "cancelled",
    STATUS_FINISHED,
    STATUS_FAILED,
}

READY_STATUSES = {
    "queued",
    "ready",
    "retry",
    STATUS_QUEUED,
}


class Scheduler(RuntimeTaskScheduler):
    """
    收束版 Scheduler + ExecutionTrace

    本版修正：
    1. task mode 優先走 agent_loop 外掛 planner / llm_planner，不再只靠舊本地單步 planner
    2. task mode 補上 ensure_file step 支援
    3. task-local 檔案預設落在 task sandbox，而不是 task_dir 根目錄
    4. task hydration / result 回寫保持一致
    5. finished task 應該真的帶出 steps / results / final_answer
    """

    def __init__(
        self,
        self_task_repo: Any = None,
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
        max_worker_slots: int = 1,
        allow_commands: bool = False,
        replanner: Any = None,
        llm_client: Any = None,
        max_scheduler_rounds_per_tick: int = 50,
        default_max_replans: int = 3,
        **kwargs: Any,
    ) -> None:
        resolved_workspace_dir = workspace_dir or "workspace"
        real_task_repo = task_repo if task_repo is not None else self_task_repo

        if real_task_repo is None:
            db_path = os.path.join(resolved_workspace_dir, "tasks.json")
            real_task_repo = TaskRepository(db_path=db_path)

        super().__init__(
            task_repo=real_task_repo,
            task_manager=task_manager,
            workspace_dir=resolved_workspace_dir,
            runtime_store=runtime_store,
            queue=queue,
            debug=debug,
            step_executor=step_executor,
            tool_registry=tool_registry,
            task_runtime=task_runtime,
            task_runner=task_runner,
            task_step_executor_adapter=task_step_executor_adapter,
            step_executor_adapter=step_executor_adapter,
            executor=executor,
            runtime_executor=runtime_executor,
            task_executor=task_executor,
            **kwargs,
        )

        self.task_repo = real_task_repo
        self.task_manager = task_manager
        self.workspace_dir = resolved_workspace_dir
        self.task_runtime = task_runtime
        self.task_runner = task_runner
        self.agent_loop = kwargs.get("agent_loop", None)
        self.max_scheduler_rounds_per_tick = max(1, int(max_scheduler_rounds_per_tick))
        self.default_max_replans = max(1, int(default_max_replans))
        self.llm_client = llm_client

        self.task_workspace = TaskWorkspace(os.path.join(self.workspace_dir, "tasks"))
        self.workspace_root = os.path.abspath(self.workspace_dir)
        self.tasks_root = os.path.join(self.workspace_root, "tasks")
        self.shared_dir = os.path.join(self.workspace_root, "shared")
        os.makedirs(self.shared_dir, exist_ok=True)
        os.makedirs(self.tasks_root, exist_ok=True)

        self.scheduler_queue = TaskSchedulerQueue()
        self.worker_pool = WorkerPool(max_workers=max(1, int(max_worker_slots)))
        self.dispatcher = TaskDispatcher(
            queue=self.scheduler_queue,
            worker_pool=self.worker_pool,
        )

        self.execution_guard = ExecutionGuard(
            workspace_root=self.workspace_root,
            shared_dir=self.shared_dir,
            allow_commands=allow_commands,
        )

        if replanner is not None:
            self.replanner = replanner
        else:
            self.replanner = Replanner(llm_client=llm_client)

    # ------------------------------------------------------------
    # 相容舊介面
    # ------------------------------------------------------------

    def run_next(self) -> Dict[str, Any]:
        return self.tick()

    def run_one(
        self,
        task: Optional[Dict[str, Any]] = None,
        current_tick: Optional[int] = None,
    ) -> Dict[str, Any]:
        if isinstance(task, dict):
            return self.run_one_step(task=task, current_tick=current_tick)
        return self.tick(current_tick=current_tick)

    def run_once(self) -> Dict[str, Any]:
        return self.tick()

    def rebuild_queue_from_repo(self) -> List[str]:
        return self.rebuild_ready_queue()

    # ------------------------------------------------------------
    # 主循環
    # ------------------------------------------------------------

    def tick(self, current_tick: Optional[int] = None) -> Dict[str, Any]:
        self.current_tick = (
            int(current_tick)
            if current_tick is not None
            else int(getattr(self, "current_tick", 0)) + 1
        )

        self._unblock_tasks_if_dependencies_done()

        all_executed_results: List[Dict[str, Any]] = []
        total_dispatched = 0
        last_synced: List[str] = []
        rounds_used = 0

        for _ in range(self.max_scheduler_rounds_per_tick):
            rounds_used += 1
            last_synced = self.rebuild_ready_queue()

            dispatch_results = self.dispatcher.dispatch_until_full()
            if not dispatch_results:
                break

            total_dispatched += len(dispatch_results)
            round_executed = self._execute_dispatch_round(
                dispatch_results=dispatch_results,
                current_tick=self.current_tick,
            )
            if not round_executed:
                break

            all_executed_results.extend(round_executed)

            if self._scheduler_dispatch_idle():
                break

        return self._build_tick_result(
            rounds_used=rounds_used,
            total_dispatched=total_dispatched,
            last_synced=last_synced,
            all_executed_results=all_executed_results,
        )

    def _execute_dispatch_round(
        self,
        dispatch_results: List[Any],
        current_tick: int,
    ) -> List[Dict[str, Any]]:
        round_executed: List[Dict[str, Any]] = []

        for dispatch_result in dispatch_results:
            handled = self._handle_dispatch_result(
                dispatch_result=dispatch_result,
                current_tick=current_tick,
            )
            if handled is not None:
                round_executed.append(handled)

        return round_executed

    def _handle_dispatch_result(
        self,
        dispatch_result: Any,
        current_tick: int,
    ) -> Optional[Dict[str, Any]]:
        if not getattr(dispatch_result, "dispatched", False) or getattr(dispatch_result, "task", None) is None:
            return None

        scheduled_task = dispatch_result.task
        task_id = str(getattr(scheduled_task, "task_id", "") or "").strip()
        if not task_id:
            return None

        repo_task = self._get_task_from_repo(task_id)
        if not isinstance(repo_task, dict):
            return self._handle_missing_repo_task(task_id=task_id)

        repo_task = self._hydrate_task_from_workspace(repo_task)
        current_status = str(repo_task.get("status") or "").strip().lower()
        if current_status in TERMINAL_STATUSES:
            self.worker_pool.release_by_task(task_id)
            return {
                "ok": True,
                "task_id": task_id,
                "status": current_status,
                "message": "task already terminal, skipped",
            }

        try:
            runner_result = self.run_one_step(task=repo_task, current_tick=current_tick)
        except Exception as e:
            return self._handle_run_one_step_exception(task_id=task_id, error=e)

        return self._finalize_dispatched_task(
            dispatch_result=dispatch_result,
            repo_task=repo_task,
            runner_result=runner_result,
        )

    def _handle_missing_repo_task(self, task_id: str) -> Dict[str, Any]:
        self.dispatcher.fail_task(
            task_id=task_id,
            error="task missing from repository",
            requeue_on_retry=False,
        )
        self._mark_repo_task_failed(task_id=task_id, error="task missing from repository")
        return {
            "ok": False,
            "task_id": task_id,
            "status": STATUS_FAILED,
            "error": "task missing from repository",
        }

    def _handle_run_one_step_exception(
        self,
        task_id: str,
        error: Exception,
    ) -> Dict[str, Any]:
        fail_result = self.dispatcher.fail_task(
            task_id=task_id,
            error=f"run_one_step exception: {error}",
            requeue_on_retry=False,
        )
        self._mark_repo_task_failed(task_id=task_id, error=f"run_one_step exception: {error}")
        return {
            "ok": False,
            "task_id": task_id,
            "status": fail_result.get("final_status", STATUS_FAILED),
            "error": str(error),
        }

    def _finalize_dispatched_task(
        self,
        dispatch_result: Any,
        repo_task: Dict[str, Any],
        runner_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        scheduled_task = dispatch_result.task
        task_id = str(getattr(scheduled_task, "task_id", "") or "").strip()

        refreshed_repo_task = self._get_task_from_repo(task_id)
        effective_status, effective_final_answer = self._extract_effective_status_and_answer(
            original_task=repo_task,
            refreshed_task=refreshed_repo_task,
            runner_result=runner_result,
        )

        if effective_status in {"done", "finished", STATUS_FINISHED, "success", "completed"}:
            self.dispatcher.complete_task(task_id=task_id, result=effective_final_answer)
            self._mark_repo_task_finished(task_id=task_id, result=effective_final_answer)

        elif effective_status in {"failed", STATUS_FAILED, "error"}:
            fail_error = str(
                (runner_result or {}).get("error")
                or effective_final_answer
                or "task failed"
            )
            self.dispatcher.fail_task(
                task_id=task_id,
                error=fail_error,
                requeue_on_retry=False,
            )
            self._mark_repo_task_failed(task_id=task_id, error=fail_error)

        elif effective_status in {STATUS_BLOCKED}:
            self.worker_pool.release_by_task(task_id)
            blocked_reason = str((runner_result or {}).get("blocked_reason") or "")
            self._sync_blocked_state(task_id=task_id, blocked_reason=blocked_reason)

        elif effective_status in {"queued", STATUS_QUEUED, "retry", "ready", "running"}:
            self.worker_pool.release_by_task(task_id)
            if self._can_requeue_task(task_id):
                self.scheduler_queue.requeue(task_id=task_id, priority=scheduled_task.priority)
                self._mark_repo_task_queued(
                    task_id=task_id,
                    error=str((runner_result or {}).get("error") or ""),
                )

        else:
            self.worker_pool.release_by_task(task_id)

        return {
            "ok": bool((runner_result or {}).get("ok", True)),
            "task_id": task_id,
            "worker_id": getattr(dispatch_result, "worker_id", None),
            "status": effective_status,
            "final_answer": effective_final_answer,
            "result": runner_result,
        }

    def _scheduler_dispatch_idle(self) -> bool:
        snapshot = self.dispatcher.snapshot()
        queue_stats = snapshot.get("queue", {})
        worker_stats = snapshot.get("workers", {})
        return (
            int(queue_stats.get("queued_count", 0) or 0) <= 0
            and int(worker_stats.get("running_count", 0) or 0) <= 0
        )

    def _build_tick_result(
        self,
        rounds_used: int,
        total_dispatched: int,
        last_synced: List[str],
        all_executed_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        snapshot = self.dispatcher.snapshot()
        queue_stats = snapshot.get("queue", {})
        worker_stats = snapshot.get("workers", {})

        return {
            "ok": True,
            "scheduler_build": SCHEDULER_BUILD,
            "tick": self.current_tick,
            "rounds_used": rounds_used,
            "max_scheduler_rounds_per_tick": self.max_scheduler_rounds_per_tick,
            "synced_task_ids": last_synced,
            "dispatched_count": total_dispatched,
            "executed_count": len(all_executed_results),
            "executed_results": all_executed_results,
            "snapshot": {
                "queue": queue_stats,
                "workers": worker_stats,
                "queued_count": queue_stats.get("queued_count", 0),
                "total_count": queue_stats.get("total_count", 0),
                "running_count": worker_stats.get("running_count", 0),
                "ready_queue": self.dispatcher.list_queued(),
                "running_tasks": self.dispatcher.list_running(),
            },
        }

    def _can_requeue_task(self, task_id: str) -> bool:
        task = self._get_task_from_repo(task_id)
        if not isinstance(task, dict):
            return False

        status = str(task.get("status") or "").strip().lower()
        if status in TERMINAL_STATUSES:
            return False

        deps_ready, _ = self._task_dependencies_satisfied(task)
        return deps_ready

    # ------------------------------------------------------------
    # runtime scheduler sync
    # ------------------------------------------------------------

    def _resolve_agent_loop(self) -> Any:
        agent_loop = getattr(self, "agent_loop", None)
        if agent_loop is not None:
            return agent_loop

        task_manager = getattr(self, "task_manager", None)
        if task_manager is not None:
            manager_loop = getattr(task_manager, "agent_loop", None)
            if manager_loop is not None:
                return manager_loop

        return None

    def _run_task_via_agent_loop(
        self,
        task: Dict[str, Any],
        current_tick: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        agent_loop = self._resolve_agent_loop()
        if agent_loop is None:
            return None

        run_fn = getattr(agent_loop, "run_task_loop", None)
        if not callable(run_fn):
            run_fn = getattr(agent_loop, "run_task", None)
        if not callable(run_fn):
            return None

        effective_task = self._hydrate_task_from_workspace(copy.deepcopy(task))
        effective_user_input = str(effective_task.get("goal") or "").strip()
        original_plan = effective_task.get("planner_result")
        if not isinstance(original_plan, dict):
            original_plan = None

        try:
            result = run_fn(
                task=effective_task,
                current_tick=current_tick,
                user_input=effective_user_input,
                original_plan=original_plan,
            )
        except TypeError:
            try:
                result = run_fn(
                    task=effective_task,
                    current_tick=current_tick,
                )
            except TypeError:
                result = run_fn(effective_task)

        if not isinstance(result, dict):
            return {
                "ok": bool(result),
                "mode": "task_loop",
                "action": "agent_loop_result",
                "task_id": self._extract_task_id(effective_task),
                "status": str(effective_task.get("status") or "running"),
                "raw_result": result,
            }

        result.setdefault("mode", "task_loop")
        return result

    def run_one_step(
        self,
        task: Dict[str, Any],
        current_tick: Optional[int] = None,
    ) -> Dict[str, Any]:
        task = self._hydrate_task_from_workspace(task)

        current_status = str(task.get("status") or "").strip().lower()
        if current_status in TERMINAL_STATUSES:
            result = self._build_terminal_skip_runner_result(task=task)
            self._sync_runtime_back_to_repo(task=task, runner_result=result)
            return result

        loop_result = self._run_task_via_agent_loop_with_fallback_check(
            task=task,
            current_tick=current_tick,
        )
        if loop_result is not None:
            return loop_result

        result = self._run_simple_task_tick(task=task, current_tick=current_tick)
        self._sync_runner_result_and_requeue_if_ready(task=task, runner_result=result)
        return result

    def _build_terminal_skip_runner_result(
        self,
        task: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "ok": True,
            "action": "terminal_skip",
            "task_id": self._extract_task_id(task),
            "status": str(task.get("status") or "").strip().lower(),
            "final_answer": task.get("final_answer", ""),
        }

    def _run_task_via_agent_loop_with_fallback_check(
        self,
        task: Dict[str, Any],
        current_tick: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        agent_loop = self._resolve_explicit_agent_loop()
        run_task_loop_fn = getattr(agent_loop, "run_task_loop", None) if agent_loop is not None else None
        if not callable(run_task_loop_fn):
            return None

        runner_result: Optional[Dict[str, Any]] = None
        loop_error_text = ""

        try:
            runner_result = run_task_loop_fn(
                task=copy.deepcopy(task),
                current_tick=current_tick if current_tick is not None else getattr(self, "current_tick", 0),
                user_input=str(task.get("goal") or ""),
                original_plan=copy.deepcopy(task.get("planner_result") or {}),
            )
        except Exception as e:
            loop_error_text = str(e).strip()
            runner_result = None

        if isinstance(runner_result, dict):
            loop_error_text = str(runner_result.get("error") or "").strip()

        if self._should_fallback_to_simple_runner(runner_result=runner_result, loop_error_text=loop_error_text):
            if self._is_simple_runner_eligible_fallback(loop_error_text=loop_error_text):
                return None

            result = runner_result if isinstance(runner_result, dict) else {
                "ok": False,
                "action": "loop_failed",
                "status": "failed",
                "error": loop_error_text or "agent loop failed",
            }
            self._sync_runner_result_and_requeue_if_ready(task=task, runner_result=result)
            return result

        self._sync_runner_result_and_requeue_if_ready(task=task, runner_result=runner_result)
        return runner_result

    def _resolve_explicit_agent_loop(self) -> Any:
        agent_loop = getattr(self, "agent_loop", None)
        if agent_loop is None:
            agent_loop = getattr(self, "_agent_loop", None)
        return agent_loop

    def _should_fallback_to_simple_runner(
        self,
        runner_result: Optional[Dict[str, Any]],
        loop_error_text: str,
    ) -> bool:
        if not isinstance(runner_result, dict):
            return True

        if loop_error_text:
            return True

        action_text = str(runner_result.get("action") or "").strip().lower()
        status_text = str(runner_result.get("status") or "").strip().lower()

        if action_text in {"failed", "exception_failed"} and loop_error_text:
            return True

        if status_text in {"failed", "error"} and loop_error_text:
            return True

        return False

    def _is_simple_runner_eligible_fallback(
        self,
        loop_error_text: str,
    ) -> bool:
        lower_error = str(loop_error_text or "").lower()
        sandbox_path_error = (
            "task_id required for sandbox-relative path" in lower_error
            or "path resolve failed" in lower_error
        )
        if sandbox_path_error:
            return True

        fallback_like_errors = [
            "unsupported step type",
            "step_executor",
            "path resolve failed",
            "sandbox-relative path",
        ]
        return any(token in lower_error for token in fallback_like_errors)

    def _sync_runner_result_and_requeue_if_ready(
        self,
        task: Dict[str, Any],
        runner_result: Dict[str, Any],
    ) -> None:
        self._sync_runtime_back_to_repo(task=task, runner_result=runner_result)

        refreshed_task = self._get_task_from_repo(self._extract_task_id(task))
        if not isinstance(refreshed_task, dict):
            return

        refreshed_status = str(refreshed_task.get("status") or "").strip().lower()
        if refreshed_status in {"queued", STATUS_QUEUED, "retry", "ready"}:
            self._enqueue_repo_task_if_ready(refreshed_task, overwrite=True)

    # ------------------------------------------------------------
    # simple fallback executor
    # ------------------------------------------------------------

    def _run_simple_task_tick(
        self,
        task: Dict[str, Any],
        current_tick: Optional[int] = None,
    ) -> Dict[str, Any]:
        if current_tick is not None:
            self.current_tick = int(current_tick)

        task = self._hydrate_task_from_workspace(task)

        task_id = self._extract_task_id(task)
        task_name = str(task.get("task_name") or task_id or "unknown_task")
        task_status = str(task.get("status") or "").strip().lower()
        trace = self._load_trace_for_task(task)

        if task_status in TERMINAL_STATUSES:
            return self._handle_simple_terminal_task(
                task=task,
                trace=trace,
                task_id=task_id,
                task_name=task_name,
                task_status=task_status,
            )

        deps_ready, blocked_reason = self._task_dependencies_satisfied(task)
        if not deps_ready:
            return self._handle_simple_blocked_task(
                task=task,
                trace=trace,
                task_id=task_id,
                task_name=task_name,
                blocked_reason=blocked_reason,
            )

        steps, current_step_index, execution_log, results, step_results, last_step_result = (
            self._load_simple_task_state(task)
        )

        if current_step_index >= len(steps):
            return self._handle_simple_finished_task(
                task=task,
                trace=trace,
                task_id=task_id,
                task_name=task_name,
                current_step_index=current_step_index,
                steps=steps,
                execution_log=execution_log,
                results=results,
                step_results=step_results,
                last_step_result=last_step_result,
            )

        step = steps[current_step_index]
        if not isinstance(step, dict):
            return self._handle_simple_invalid_step(
                task=task,
                trace=trace,
                task_id=task_id,
                task_name=task_name,
                results=results,
                step_results=step_results,
                last_step_result=last_step_result,
            )

        try:
            step_result = self._execute_simple_step(task=task, step=step)
        except Exception as e:
            return self._handle_simple_step_exception(
                task=task,
                trace=trace,
                task_id=task_id,
                task_name=task_name,
                current_step_index=current_step_index,
                step=step,
                error=e,
                execution_log=execution_log,
                results=results,
                step_results=step_results,
                last_step_result=last_step_result,
            )

        return self._handle_simple_step_success(
            task=task,
            trace=trace,
            task_id=task_id,
            task_name=task_name,
            current_step_index=current_step_index,
            step=step,
            step_result=step_result,
            steps=steps,
            execution_log=execution_log,
            results=results,
            step_results=step_results,
            last_step_result=last_step_result,
        )

    def _load_simple_task_state(
        self,
        task: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], int, List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Any]:
        steps = task.get("steps", [])
        if not isinstance(steps, list):
            steps = []

        current_step_index = int(task.get("current_step_index", 0) or 0)

        execution_log = copy.deepcopy(task.get("execution_log", []))
        if not isinstance(execution_log, list):
            execution_log = []

        results = copy.deepcopy(task.get("results", []))
        if not isinstance(results, list):
            results = []

        step_results = copy.deepcopy(task.get("step_results", results))
        if not isinstance(step_results, list):
            step_results = copy.deepcopy(results)

        last_step_result = copy.deepcopy(task.get("last_step_result"))
        return steps, current_step_index, execution_log, results, step_results, last_step_result

    def _handle_simple_terminal_task(
        self,
        task: Dict[str, Any],
        trace: ExecutionTrace,
        task_id: str,
        task_name: str,
        task_status: str,
    ) -> Dict[str, Any]:
        self._trace_status(
            trace=trace,
            task=task,
            status=task_status,
            tick=self.current_tick,
            final_answer=str(task.get("final_answer") or ""),
            extra={"action": "terminal_skip"},
        )
        self._save_trace_for_task(task=task, trace=trace)
        return {
            "ok": True,
            "action": "terminal_skip",
            "tick": self.current_tick,
            "task_id": task_id,
            "task_name": task_name,
            "status": task_status,
            "message": "task already terminal",
            "final_answer": task.get("final_answer", ""),
        }

    def _handle_simple_blocked_task(
        self,
        task: Dict[str, Any],
        trace: ExecutionTrace,
        task_id: str,
        task_name: str,
        blocked_reason: str,
    ) -> Dict[str, Any]:
        task["status"] = STATUS_BLOCKED
        task["blocked_reason"] = blocked_reason
        task["history"] = self._append_history(task.get("history"), STATUS_BLOCKED)

        self._trace_status(
            trace=trace,
            task=task,
            status=STATUS_BLOCKED,
            tick=self.current_tick,
            final_answer="",
            extra={
                "action": "blocked_by_dependencies",
                "blocked_reason": blocked_reason,
            },
        )
        self._save_trace_for_task(task=task, trace=trace)

        return {
            "ok": False,
            "action": "blocked_by_dependencies",
            "tick": self.current_tick,
            "task_id": task_id,
            "task_name": task_name,
            "status": STATUS_BLOCKED,
            "blocked_reason": blocked_reason,
            "error": blocked_reason,
        }

    def _handle_simple_finished_task(
        self,
        task: Dict[str, Any],
        trace: ExecutionTrace,
        task_id: str,
        task_name: str,
        current_step_index: int,
        steps: List[Dict[str, Any]],
        execution_log: List[Dict[str, Any]],
        results: List[Dict[str, Any]],
        step_results: List[Dict[str, Any]],
        last_step_result: Any,
    ) -> Dict[str, Any]:
        task["status"] = "finished"
        task["final_answer"] = str(task.get("final_answer") or self._build_simple_final_answer(results))
        task["finished_tick"] = self.current_tick
        task["last_run_tick"] = self.current_tick
        task["results"] = results
        task["step_results"] = step_results
        task["last_step_result"] = last_step_result
        task["history"] = self._append_history(task.get("history"), "finished")

        self._trace_status(
            trace=trace,
            task=task,
            status="finished",
            tick=self.current_tick,
            final_answer=task["final_answer"],
            extra={
                "action": "simple_task_finished",
                "current_step_index": current_step_index,
                "steps_total": len(steps),
            },
        )
        self._save_trace_for_task(task=task, trace=trace)

        return {
            "ok": True,
            "action": "simple_task_finished",
            "tick": self.current_tick,
            "task_id": task_id,
            "task_name": task_name,
            "status": "finished",
            "message": "task finished",
            "final_answer": task["final_answer"],
            "execution_log": execution_log,
            "results": results,
            "step_results": step_results,
            "last_step_result": last_step_result,
            "current_step_index": current_step_index,
            "step_count": len(steps),
            "steps_total": len(steps),
            "last_run_tick": self.current_tick,
            "finished_tick": self.current_tick,
        }

    def _handle_simple_invalid_step(
        self,
        task: Dict[str, Any],
        trace: ExecutionTrace,
        task_id: str,
        task_name: str,
        results: List[Dict[str, Any]],
        step_results: List[Dict[str, Any]],
        last_step_result: Any,
    ) -> Dict[str, Any]:
        task["status"] = "failed"
        task["last_error"] = "invalid step type"
        task["failure_message"] = "invalid step type"
        task["last_failure_tick"] = self.current_tick
        task["last_run_tick"] = self.current_tick
        task["results"] = results
        task["step_results"] = step_results
        task["last_step_result"] = last_step_result
        task["history"] = self._append_history(task.get("history"), "failed")

        self._trace_status(
            trace=trace,
            task=task,
            status="failed",
            tick=self.current_tick,
            final_answer="",
            extra={
                "action": "simple_invalid_step",
                "error": "invalid step type",
            },
        )
        self._save_trace_for_task(task=task, trace=trace)

        return {
            "ok": False,
            "action": "simple_invalid_step",
            "tick": self.current_tick,
            "task_id": task_id,
            "task_name": task_name,
            "status": "failed",
            "message": "invalid step type",
            "error": "invalid step type",
        }

    def _handle_simple_step_exception(
        self,
        task: Dict[str, Any],
        trace: ExecutionTrace,
        task_id: str,
        task_name: str,
        current_step_index: int,
        step: Dict[str, Any],
        error: Exception,
        execution_log: List[Dict[str, Any]],
        results: List[Dict[str, Any]],
        step_results: List[Dict[str, Any]],
        last_step_result: Any,
    ) -> Dict[str, Any]:
        failed_step_result = {
            "ok": False,
            "step_index": current_step_index,
            "step": copy.deepcopy(step),
            "error": str(error),
        }
        execution_log.append(
            {
                "tick": self.current_tick,
                "step_index": current_step_index,
                "step": copy.deepcopy(step),
                "ok": False,
                "error": str(error),
            }
        )
        results.append(copy.deepcopy(failed_step_result))
        step_results = copy.deepcopy(results)
        last_step_result = copy.deepcopy(failed_step_result)

        task["execution_log"] = execution_log
        task["results"] = results
        task["step_results"] = step_results
        task["last_step_result"] = last_step_result
        task["last_error"] = str(error)
        task["failure_message"] = str(error)
        task["last_failure_tick"] = self.current_tick
        task["last_run_tick"] = self.current_tick

        self._trace_step(
            trace=trace,
            task=task,
            step_index=current_step_index,
            step=step,
            ok=False,
            result=None,
            error=str(error),
            tick=self.current_tick,
        )

        replan_result = self._try_replan_task(task=task)
        task["replan_decision"] = str(replan_result.get("decision") or "")
        task["replan_summary"] = str(replan_result.get("summary") or "")
        task["replan_failed_step_type"] = str(replan_result.get("failed_step_type") or "")
        task["replan_repairable"] = replan_result.get("repairable", None)

        if replan_result.get("replanned"):
            task["status"] = "queued"
            task["replan_reason"] = str(task.get("last_error") or task.get("failure_message") or str(error))
            task["current_step_index"] = 0
            task["history"] = self._append_history(task.get("history"), "replanned")
            task["history"] = self._append_history(task.get("history"), "queued")

            new_steps = task.get("steps", []) if isinstance(task.get("steps"), list) else []
            new_steps_total = len(new_steps)

            self._trace_replan(
                trace=trace,
                task=task,
                tick=self.current_tick,
                replan_result=replan_result,
            )
            self._trace_status(
                trace=trace,
                task=task,
                status="queued",
                tick=self.current_tick,
                final_answer="",
                extra={
                    "action": "simple_step_replanned",
                    "replan_reason": task["replan_reason"],
                    "replan_count": task.get("replan_count", 0),
                    "replan_decision": task.get("replan_decision", ""),
                    "replan_summary": task.get("replan_summary", ""),
                    "replan_failed_step_type": task.get("replan_failed_step_type", ""),
                    "replan_repairable": task.get("replan_repairable", None),
                    "steps_total": new_steps_total,
                },
            )
            self._save_trace_for_task(task=task, trace=trace)

            return {
                "ok": True,
                "action": "simple_step_replanned",
                "tick": self.current_tick,
                "task_id": task_id,
                "task_name": task_name,
                "status": "queued",
                "message": replan_result.get("summary", "task replanned"),
                "execution_log": execution_log,
                "results": results,
                "step_results": step_results,
                "last_step_result": last_step_result,
                "current_step_index": 0,
                "step_count": new_steps_total,
                "steps_total": new_steps_total,
                "last_run_tick": self.current_tick,
                "last_failure_tick": self.current_tick,
                "replan_reason": task["replan_reason"],
                "replan_decision": task.get("replan_decision", ""),
                "replan_summary": task.get("replan_summary", ""),
                "replan_failed_step_type": task.get("replan_failed_step_type", ""),
                "replan_repairable": task.get("replan_repairable", None),
                "replan_result": replan_result,
            }

        task["status"] = "failed"
        task["history"] = self._append_history(task.get("history"), "failed")

        self._trace_status(
            trace=trace,
            task=task,
            status="failed",
            tick=self.current_tick,
            final_answer="",
            extra={
                "action": "simple_step_failed",
                "error": str(error),
                "replan_decision": task.get("replan_decision", ""),
                "replan_summary": task.get("replan_summary", ""),
                "replan_failed_step_type": task.get("replan_failed_step_type", ""),
                "replan_repairable": task.get("replan_repairable", None),
                "replan_result": copy.deepcopy(replan_result),
            },
        )
        self._save_trace_for_task(task=task, trace=trace)

        return {
            "ok": False,
            "action": "simple_step_failed",
            "tick": self.current_tick,
            "task_id": task_id,
            "task_name": task_name,
            "status": "failed",
            "message": "step execution failed",
            "error": str(error),
            "execution_log": execution_log,
            "results": results,
            "step_results": step_results,
            "last_step_result": last_step_result,
            "current_step_index": current_step_index,
            "step_count": len(task.get("steps", [])) if isinstance(task.get("steps"), list) else 0,
            "steps_total": len(task.get("steps", [])) if isinstance(task.get("steps"), list) else 0,
            "last_run_tick": self.current_tick,
            "last_failure_tick": self.current_tick,
            "replan_decision": task.get("replan_decision", ""),
            "replan_summary": task.get("replan_summary", ""),
            "replan_failed_step_type": task.get("replan_failed_step_type", ""),
            "replan_repairable": task.get("replan_repairable", None),
            "replan_result": replan_result,
        }

    def _handle_simple_step_success(
        self,
        task: Dict[str, Any],
        trace: ExecutionTrace,
        task_id: str,
        task_name: str,
        current_step_index: int,
        step: Dict[str, Any],
        step_result: Dict[str, Any],
        steps: List[Dict[str, Any]],
        execution_log: List[Dict[str, Any]],
        results: List[Dict[str, Any]],
        step_results: List[Dict[str, Any]],
        last_step_result: Any,
    ) -> Dict[str, Any]:
        normalized_step_result = {
            "ok": True,
            "step_index": current_step_index,
            "step": copy.deepcopy(step),
            "result": copy.deepcopy(step_result),
        }

        execution_log.append(
            {
                "tick": self.current_tick,
                "step_index": current_step_index,
                "step": copy.deepcopy(step),
                "ok": True,
                "result": copy.deepcopy(step_result),
            }
        )
        results.append(copy.deepcopy(normalized_step_result))
        step_results = copy.deepcopy(results)
        last_step_result = copy.deepcopy(normalized_step_result)

        task["execution_log"] = execution_log
        task["results"] = results
        task["step_results"] = step_results
        task["last_step_result"] = last_step_result
        task["current_step_index"] = current_step_index + 1
        task["last_run_tick"] = self.current_tick

        self._trace_step(
            trace=trace,
            task=task,
            step_index=current_step_index,
            step=step,
            ok=True,
            result=step_result,
            error="",
            tick=self.current_tick,
        )

        if task["current_step_index"] >= len(steps):
            final_answer = self._build_simple_final_answer(
                [x.get("result", x) if isinstance(x, dict) else x for x in results]
            )
            task["status"] = "finished"
            task["final_answer"] = final_answer
            task["finished_tick"] = self.current_tick
            task["history"] = self._append_history(task.get("history"), "finished")

            self._trace_status(
                trace=trace,
                task=task,
                status="finished",
                tick=self.current_tick,
                final_answer=final_answer,
                extra={
                    "action": "simple_task_finished",
                    "current_step_index": task["current_step_index"],
                    "steps_total": len(steps),
                },
            )
            self._save_trace_for_task(task=task, trace=trace)

            return {
                "ok": True,
                "action": "simple_task_finished",
                "tick": self.current_tick,
                "task_id": task_id,
                "task_name": task_name,
                "status": "finished",
                "message": "task finished",
                "final_answer": final_answer,
                "execution_log": execution_log,
                "results": results,
                "step_results": step_results,
                "last_step_result": last_step_result,
                "current_step_index": task["current_step_index"],
                "step_count": len(steps),
                "steps_total": len(steps),
                "last_run_tick": self.current_tick,
                "finished_tick": self.current_tick,
            }

        task["status"] = "queued"
        task["history"] = self._append_history(task.get("history"), "queued")

        self._trace_status(
            trace=trace,
            task=task,
            status="queued",
            tick=self.current_tick,
            final_answer="",
            extra={
                "action": "simple_step_executed",
                "current_step_index": task["current_step_index"],
                "steps_total": len(steps),
            },
        )
        self._save_trace_for_task(task=task, trace=trace)

        return {
            "ok": True,
            "action": "simple_step_executed",
            "tick": self.current_tick,
            "task_id": task_id,
            "task_name": task_name,
            "status": "queued",
            "message": "step executed, waiting next tick",
            "final_answer": "",
            "execution_log": execution_log,
            "results": results,
            "step_results": step_results,
            "last_step_result": last_step_result,
            "current_step_index": task["current_step_index"],
            "step_count": len(steps),
            "steps_total": len(steps),
            "last_run_tick": self.current_tick,
        }

    def _get_failed_step_payload(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task, dict):
            return {}

        last = task.get("last_step_result")
        if isinstance(last, dict):
            step = last.get("step")
            if isinstance(step, dict):
                return copy.deepcopy(step)

        current_step_index = int(task.get("current_step_index", 0) or 0)
        steps = task.get("steps", [])
        if isinstance(steps, list) and 0 <= current_step_index < len(steps):
            maybe_step = steps[current_step_index]
            if isinstance(maybe_step, dict):
                return copy.deepcopy(maybe_step)

        return {}

    def _get_failed_step_type(self, task: Dict[str, Any]) -> str:
        failed_step = self._get_failed_step_payload(task)
        return str(failed_step.get("type") or "").strip().lower()

    def _is_repairable_failure(self, task: Dict[str, Any]) -> Tuple[bool, str]:
        if not isinstance(task, dict):
            return False, "invalid task payload"

        status = str(task.get("status") or "").strip().lower()
        if status not in {"failed", "error", "queued"}:
            return False, f"status not repairable: {status or 'unknown'}"

        replan_count = int(task.get("replan_count", 0) or 0)
        max_replans = int(task.get("max_replans", self.default_max_replans) or self.default_max_replans)
        if replan_count >= max_replans:
            return False, f"replan limit reached: {replan_count}/{max_replans}"

        failed_step_type = self._get_failed_step_type(task)
        allowed_types = {"verify", "read_file", "run_python", "command", "write_file", "llm", "llm_generate"}
        if failed_step_type not in allowed_types:
            return False, f"step type not repairable: {failed_step_type or 'unknown'}"

        error_text = str(task.get("last_error") or task.get("failure_message") or "").strip().lower()
        hard_fail_signals = [
            "unsupported step type",
            "invalid step type",
            "depends_on task not found",
            "self dependency",
            "task already terminal",
        ]
        for signal in hard_fail_signals:
            if signal in error_text:
                return False, f"hard failure: {signal}"

        if failed_step_type == "verify":
            if self._verify_step_failure_repairable(task):
                return True, ""
            return False, "verify failure not repairable"

        return True, ""

    def _canonicalize_steps_for_compare(self, steps: Any) -> List[Dict[str, Any]]:
        if not isinstance(steps, list):
            return []

        canonical: List[Dict[str, Any]] = []
        for item in steps:
            if not isinstance(item, dict):
                canonical.append({"type": str(item)})
                continue

            normalized: Dict[str, Any] = {}
            for key in sorted(item.keys()):
                value = item.get(key)
                normalized[key] = value.strip() if isinstance(value, str) else value
            canonical.append(normalized)

        return canonical

    def _is_meaningful_replan(self, old_steps: Any, new_steps: Any) -> bool:
        return self._canonicalize_steps_for_compare(old_steps) != self._canonicalize_steps_for_compare(new_steps)

    def _try_replan_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task, dict):
            return {
                "ok": False,
                "replanned": False,
                "decision": "error",
                "summary": "invalid task payload",
            }

        failed_step_type = self._get_failed_step_type(task)
        repairable, repairable_reason = self._is_repairable_failure(task)
        if not repairable:
            return {
                "ok": True,
                "replanned": False,
                "decision": "skipped",
                "summary": repairable_reason or "failure not repairable",
                "repairable": False,
                "failed_step_type": failed_step_type,
                "replan_count": int(task.get("replan_count", 0) or 0),
                "max_replans": int(task.get("max_replans", self.default_max_replans) or self.default_max_replans),
            }

        replanner = getattr(self, "replanner", None)
        if replanner is None or not hasattr(replanner, "create_replan_for_task"):
            return {
                "ok": False,
                "replanned": False,
                "decision": "error",
                "summary": "replanner not available",
                "repairable": True,
                "failed_step_type": failed_step_type,
            }

        old_steps = copy.deepcopy(task.get("steps", [])) if isinstance(task.get("steps"), list) else []

        try:
            replan_result = replanner.create_replan_for_task(
                task=copy.deepcopy(task),
                user_input=str(task.get("goal") or ""),
            )
        except Exception as e:
            return {
                "ok": False,
                "replanned": False,
                "decision": "error",
                "summary": f"replanner exception: {e}",
                "repairable": True,
                "failed_step_type": failed_step_type,
            }

        if not isinstance(replan_result, dict):
            return {
                "ok": False,
                "replanned": False,
                "decision": "error",
                "summary": "invalid replanner result",
                "repairable": True,
                "failed_step_type": failed_step_type,
            }

        if not bool(replan_result.get("replanned")):
            return {
                "ok": True,
                "replanned": False,
                "decision": "skipped",
                "summary": str(replan_result.get("summary") or "replan not applied"),
                "repairable": True,
                "failed_step_type": failed_step_type,
                "raw_replan_result": copy.deepcopy(replan_result),
            }

        plan = replan_result.get("plan", {})
        new_steps = plan.get("steps", []) if isinstance(plan, dict) else []
        if not isinstance(new_steps, list) or not new_steps:
            return {
                "ok": False,
                "replanned": False,
                "decision": "error",
                "summary": "replanner returned empty steps",
                "repairable": True,
                "failed_step_type": failed_step_type,
                "raw_replan_result": copy.deepcopy(replan_result),
            }

        if not self._is_meaningful_replan(old_steps, new_steps):
            return {
                "ok": True,
                "replanned": False,
                "decision": "skipped",
                "summary": "replanner returned equivalent steps",
                "repairable": True,
                "failed_step_type": failed_step_type,
                "raw_replan_result": copy.deepcopy(replan_result),
            }

        task["steps"] = copy.deepcopy(new_steps)
        task["steps_total"] = len(new_steps)
        task["current_step_index"] = 0
        task["replan_count"] = int(replan_result.get("replan_count", task.get("replan_count", 0)) or 0)
        task["replanned"] = True
        task["replan_reason"] = str(task.get("last_error") or task.get("failure_message") or "")
        task["planner_result"] = copy.deepcopy(plan)
        task["status"] = "queued"

        return {
            "ok": True,
            "replanned": True,
            "decision": "accepted",
            "summary": str(replan_result.get("summary") or "task replanned"),
            "repairable": True,
            "failed_step_type": failed_step_type,
            "steps_total": len(new_steps),
            "replan_count": task["replan_count"],
            "raw_replan_result": copy.deepcopy(replan_result),
        }

    def _execute_simple_step(
        self,
        task: Dict[str, Any],
        step: Dict[str, Any],
    ) -> Dict[str, Any]:
        step_type = str(step.get("type") or "").strip().lower()
        task_dir = self._resolve_task_dir(task)
        step_scope = self._normalize_step_scope(step.get("scope", None))

        guard_step = copy.deepcopy(step)

        if step_type == "run_python":
            run_path = str(step.get("path") or "").strip()
            if not run_path:
                raise ValueError("run_python step missing path")
            guard_step = {
                "type": "command",
                "command": f'{sys.executable} "{run_path}"',
            }

        elif step_type == "verify":
            step = self._normalize_verify_step(step)
            step_scope = self._normalize_step_scope(step.get("scope", None))
            guard_step = {
                "type": "noop",
                "message": "verify",
            }

        elif step_type == "ensure_file":
            raw_path = str(step.get("path") or "").strip()
            if not raw_path:
                raise ValueError("ensure_file step missing path")
            guard_step = {
                "type": "write_file",
                "path": raw_path,
                "content": "",
            }

        guard_result = self.execution_guard.check_step(step=guard_step, task_dir=task_dir)
        if not bool(guard_result.get("ok")):
            raise PermissionError(str(guard_result.get("error") or "guard blocked execution"))

        if step_type == "noop":
            return {
                "type": "noop",
                "message": str(step.get("message") or "noop ok"),
            }

        if step_type == "ensure_file":
            raw_path = str(step.get("path") or "").strip()
            if not raw_path:
                raise ValueError("ensure_file step missing path")

            full_path = self._resolve_guard_target_path(
                raw_path=raw_path,
                task_dir=task_dir,
                scope=step_scope,
                resolved_path=str(guard_result.get("resolved_path") or ""),
            )

            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            created = False
            if not os.path.exists(full_path):
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write("")
                created = True

            return {
                "type": "ensure_file",
                "path": raw_path,
                "full_path": full_path,
                "scope": step_scope,
                "created": created,
                "preserved_existing": not created,
            }

        if step_type == "write_file":
            raw_path = str(step.get("path") or "").strip()
            if not raw_path:
                raise ValueError("write_file step missing path")

            if bool(step.get("use_previous_text", False)):
                content = self._extract_text_from_previous_result(task)
            else:
                content = step.get("content", "")

            if content is None:
                content = ""
            content = str(content)

            full_path = self._resolve_guard_target_path(
                raw_path=raw_path,
                task_dir=task_dir,
                scope=step_scope,
                resolved_path=str(guard_result.get("resolved_path") or ""),
            )

            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

            return {
                "type": "write_file",
                "path": raw_path,
                "full_path": full_path,
                "scope": step_scope,
                "bytes": len(content.encode("utf-8")),
                "content": content,
                "used_previous_text": bool(step.get("use_previous_text", False)),
            }


        if step_type in {"llm", "llm_generate"}:
            previous_text = self._extract_text_from_previous_result(task)
            prompt_template = str(step.get("prompt_template") or step.get("prompt") or "").strip()
            prompt = prompt_template.replace("{{file_content}}", previous_text)

            step_executor = getattr(self, "step_executor", None)
            result_payload: Dict[str, Any]

            if step_executor is not None:
                try:
                    if hasattr(step_executor, "execute_step") and callable(step_executor.execute_step):
                        step_result = step_executor.execute_step(
                            task=task,
                            step=copy.deepcopy(step),
                            context={"file_content": previous_text},
                            step_index=int(task.get("current_step_index", 0) or 0),
                            step_count=len(task.get("steps", [])) if isinstance(task.get("steps", []), list) else 1,
                            previous_result=task.get("last_step_result"),
                        )
                    elif hasattr(step_executor, "execute") and callable(step_executor.execute):
                        step_result = step_executor.execute(
                            step=copy.deepcopy(step),
                            context={"file_content": previous_text},
                        )
                    else:
                        step_result = None
                except TypeError:
                    try:
                        step_result = step_executor.execute_step(
                            task=task,
                            step=copy.deepcopy(step),
                            context={"file_content": previous_text},
                        )
                    except Exception as e:
                        raise RuntimeError(f"llm step execution failed: {e}")
                except Exception as e:
                    raise RuntimeError(f"llm step execution failed: {e}")

                if isinstance(step_result, dict):
                    result_payload = copy.deepcopy(step_result)
                else:
                    result_payload = {"text": str(step_result or "")}
            elif self.llm_client is not None:
                client = self.llm_client
                if hasattr(client, "chat") and callable(client.chat):
                    llm_out = client.chat(prompt)
                elif hasattr(client, "generate") and callable(client.generate):
                    llm_out = client.generate(prompt)
                else:
                    raise RuntimeError("llm_client has no chat/generate method")
                result_payload = {"text": str(llm_out or "")}
            else:
                raise RuntimeError("no llm backend available for llm step")

            final_text = self._extract_text_from_result_payload(result_payload)
            if not final_text and isinstance(result_payload, dict):
                final_text = str(result_payload)

            return {
                "type": step_type,
                "mode": str(step.get("mode") or ""),
                "prompt": prompt,
                "prompt_template": prompt_template,
                "input_text": previous_text,
                "text": final_text,
                "content": final_text,
                "result": result_payload,
            }

        if step_type == "command":
            command = str(step.get("command") or "").strip()
            if not command:
                raise ValueError("command step missing command")

            completed = subprocess.run(
                command,
                shell=True,
                cwd=task_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            result = {
                "type": "command",
                "command": command,
                "returncode": int(completed.returncode),
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "cwd": task_dir,
            }

            if completed.returncode != 0:
                raise RuntimeError(
                    f"command failed: {command} | returncode={completed.returncode} | stderr={completed.stderr.strip()}"
                )

            return result

        if step_type == "run_python":
            raw_path = str(step.get("path") or "").strip()
            if not raw_path:
                raise ValueError("run_python step missing path")

            full_path = self._resolve_read_path_with_fallback(
                raw_path=raw_path,
                task_dir=task_dir,
                shared_dir=self.shared_dir,
                scope=step_scope,
            )

            read_guard = self.execution_guard.check_step(
                step={"type": "read_file", "path": full_path},
                task_dir=task_dir,
            )
            if not bool(read_guard.get("ok")):
                raise PermissionError(str(read_guard.get("error") or "guard blocked python file read"))

            if not os.path.exists(full_path):
                raise FileNotFoundError(f"python file not found: {full_path}")

            completed = subprocess.run(
                [sys.executable, full_path],
                cwd=task_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            result = {
                "type": "run_python",
                "path": raw_path,
                "full_path": full_path,
                "scope": step_scope,
                "python_executable": sys.executable,
                "returncode": int(completed.returncode),
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "cwd": task_dir,
            }

            if completed.returncode != 0:
                raise RuntimeError(
                    f"python run failed: {raw_path} | returncode={completed.returncode} | stderr={completed.stderr.strip()}"
                )

            return result

        if step_type == "read_file":
            raw_path = str(step.get("path") or "").strip()
            if not raw_path:
                raise ValueError("read_file step missing path")

            full_path = self._resolve_read_path_with_fallback(
                raw_path=raw_path,
                task_dir=task_dir,
                shared_dir=self.shared_dir,
                scope=step_scope,
            )

            guard_check = self.execution_guard.check_step(
                step={"type": "read_file", "path": full_path},
                task_dir=task_dir,
            )
            if not bool(guard_check.get("ok")):
                raise PermissionError(str(guard_check.get("error") or "guard blocked read"))

            if not os.path.exists(full_path):
                raise FileNotFoundError(f"file not found: {full_path}")

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            return {
                "type": "read_file",
                "path": raw_path,
                "full_path": full_path,
                "scope": step_scope,
                "content": content,
            }

        if step_type == "verify":
            step = self._normalize_verify_step(step)
            step_scope = self._normalize_step_scope(step.get("scope", None))
            contains = step.get("contains", None)
            equals = step.get("equals", None)
            exists = step.get("exists", None)
            path = str(step.get("path") or "").strip()

            if contains is None and equals is None and exists is None and not path:
                raise ValueError("verify step requires path / contains / equals / exists")

            target_text = ""
            full_path = ""

            if path:
                full_path = self._resolve_read_path_with_fallback(
                    raw_path=path,
                    task_dir=task_dir,
                    shared_dir=self.shared_dir,
                    scope=step_scope,
                )

                read_guard = self.execution_guard.check_step(
                    step={"type": "read_file", "path": full_path},
                    task_dir=task_dir,
                )
                if not bool(read_guard.get("ok")):
                    raise PermissionError(str(read_guard.get("error") or "guard blocked verify read"))

                file_exists = os.path.exists(full_path)

                if exists is True and not file_exists:
                    raise FileNotFoundError(f"verify file not found: {full_path}")

                if exists is False and file_exists:
                    raise RuntimeError(f"verify failed: file should not exist: {full_path}")

                if (contains is not None or equals is not None or exists is not False) and not file_exists:
                    raise FileNotFoundError(f"verify file not found: {full_path}")

                if file_exists and (contains is not None or equals is not None):
                    with open(full_path, "r", encoding="utf-8") as f:
                        target_text = f.read()
            else:
                last = task.get("last_step_result")
                if isinstance(last, dict):
                    last_result = last.get("result")
                    if isinstance(last_result, dict):
                        if "stdout" in last_result:
                            target_text = str(last_result.get("stdout") or "")
                        elif "content" in last_result:
                            target_text = str(last_result.get("content") or "")
                        else:
                            target_text = json.dumps(last_result, ensure_ascii=False)
                    else:
                        target_text = str(last_result or "")

            if contains is not None:
                contains_text = str(contains)
                if contains_text not in target_text:
                    raise RuntimeError(f"verify contains failed: '{contains_text}' not found")

            if equals is not None:
                expected = str(equals)
                if str(target_text).strip() != expected.strip():
                    raise RuntimeError(
                        f"verify equals failed: expected exact match '{expected}', got '{str(target_text).strip()}'"
                    )

            return {
                "type": "verify",
                "ok": True,
                "path": path,
                "full_path": full_path,
                "scope": step_scope,
                "contains": contains,
                "equals": equals,
                "exists": exists,
                "checked_text": target_text,
                "verified": True,
            }

        raise ValueError(f"unsupported step type: {step_type}")

    def _resolve_task_dir(self, task: Dict[str, Any]) -> str:
        task_dir = str(task.get("task_dir") or "").strip()
        if not task_dir:
            task_name = str(task.get("task_name") or self._extract_task_id(task) or "unknown_task")
            task_dir = os.path.join(self.tasks_root, task_name)

        sandbox_dir = os.path.join(task_dir, "sandbox")
        os.makedirs(sandbox_dir, exist_ok=True)
        return sandbox_dir

    def _normalize_step_scope(self, scope: Any) -> str:
        value = str(scope or "").strip().lower()
        if value in {"task", "shared", "auto"}:
            return value
        return "auto"

    def _resolve_step_path(
        self,
        raw_path: str,
        task_dir: str,
        shared_dir: str,
        scope: str = "auto",
    ) -> str:
        normalized = str(raw_path or "").replace("\\", "/").strip()
        step_scope = self._normalize_step_scope(scope)

        if os.path.isabs(normalized):
            return os.path.abspath(normalized)

        if normalized.startswith("workspace/shared/"):
            relative_part = normalized[len("workspace/shared/"):].strip("/")
            return os.path.abspath(os.path.join(shared_dir, relative_part))

        if normalized.startswith("shared/"):
            relative_part = normalized[len("shared/"):].strip("/")
            return os.path.abspath(os.path.join(shared_dir, relative_part))

        if step_scope == "shared":
            return os.path.abspath(os.path.join(shared_dir, normalized))

        return os.path.abspath(os.path.join(task_dir, normalized))

    def _resolve_read_path_with_fallback(
        self,
        raw_path: str,
        task_dir: str,
        shared_dir: str,
        scope: str = "auto",
    ) -> str:
        normalized = str(raw_path or "").replace("\\", "/").strip()
        step_scope = self._normalize_step_scope(scope)

        if os.path.isabs(normalized):
            return os.path.abspath(normalized)

        if normalized.startswith("workspace/shared/"):
            relative_part = normalized[len("workspace/shared/"):].strip("/")
            return os.path.abspath(os.path.join(shared_dir, relative_part))

        if normalized.startswith("shared/"):
            relative_part = normalized[len("shared/"):].strip("/")
            return os.path.abspath(os.path.join(shared_dir, relative_part))

        task_local = os.path.abspath(os.path.join(task_dir, normalized))
        shared_fallback = os.path.abspath(os.path.join(shared_dir, normalized))

        if step_scope == "task":
            return task_local

        if step_scope == "shared":
            return shared_fallback

        if os.path.exists(task_local):
            return task_local

        if os.path.exists(shared_fallback):
            return shared_fallback

        return task_local

    def _needs_scheduler_path_resolution(self, raw_path: str) -> bool:
        normalized = str(raw_path or "").replace("\\", "/").strip().lower()
        return bool(
            normalized.startswith("shared/")
            or normalized.startswith("workspace/shared/")
            or normalized.startswith("workspace/tasks/")
            or normalized.startswith("tasks/")
        )

    def _resolve_guard_target_path(
        self,
        raw_path: str,
        task_dir: str,
        scope: str = "auto",
        resolved_path: str = "",
    ) -> str:
        if resolved_path:
            normalized_resolved = os.path.abspath(str(resolved_path).strip())
            normalized_raw = str(raw_path or "").replace("\\", "/").strip().lower()
            step_scope = self._normalize_step_scope(scope)

            if step_scope == "shared":
                if normalized_raw.startswith("shared/") or normalized_raw.startswith("workspace/shared/"):
                    return normalized_resolved
            elif step_scope == "task":
                if not (normalized_raw.startswith("shared/") or normalized_raw.startswith("workspace/shared/")):
                    return normalized_resolved
            else:
                return normalized_resolved

        return self._resolve_step_path(
            raw_path=raw_path,
            task_dir=task_dir,
            shared_dir=self.shared_dir,
            scope=scope,
        )


    def _extract_text_from_result_payload(self, payload: Any) -> str:
        if isinstance(payload, str):
            return payload

        if isinstance(payload, dict):
            for key in ("text", "content", "message", "response", "final_answer", "stdout", "checked_text"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            result_block = payload.get("result")
            if isinstance(result_block, dict):
                for key in ("text", "content", "message", "response", "final_answer", "stdout", "checked_text"):
                    value = result_block.get(key)
                    if isinstance(value, str) and value.strip():
                        return value
        return ""

    def _extract_text_from_previous_result(self, task: Dict[str, Any]) -> str:
        if not isinstance(task, dict):
            return ""

        last = task.get("last_step_result")
        if isinstance(last, dict):
            direct = self._extract_text_from_result_payload(last)
            if direct:
                return direct
            result_block = last.get("result")
            direct = self._extract_text_from_result_payload(result_block)
            if direct:
                return direct

        results = task.get("results", [])
        if isinstance(results, list) and results:
            last_item = results[-1]
            direct = self._extract_text_from_result_payload(last_item)
            if direct:
                return direct

        return ""

    def _normalize_public_status_fields(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task, dict):
            return task

        status = str(task.get("status") or STATUS_CREATED).strip().lower() or STATUS_CREATED
        task["status"] = status

        steps = task.get("steps", [])
        if not isinstance(steps, list):
            steps = []
            task["steps"] = steps

        try:
            current_step_index = int(task.get("current_step_index", 0) or 0)
        except Exception:
            current_step_index = 0

        if current_step_index < 0:
            current_step_index = 0

        steps_total = len(steps)
        task["steps_total"] = steps_total

        if status in {"finished", "done", "success", "completed"}:
            current_step_index = steps_total if steps_total >= 0 else 0
            task["current_step"] = None
        else:
            if steps_total <= 0:
                current_step_index = 0
                task["current_step"] = None
            else:
                if current_step_index >= steps_total:
                    current_step_index = max(0, steps_total - 1)
                maybe_step = steps[current_step_index]
                task["current_step"] = copy.deepcopy(maybe_step) if isinstance(maybe_step, dict) else None

        task["current_step_index"] = current_step_index

        task["final_answer"] = str(task.get("final_answer") or "")
        task["last_error"] = str(task.get("last_error") or "")
        task["failure_message"] = str(task.get("failure_message") or "")
        task["blocked_reason"] = str(task.get("blocked_reason") or "")

        state_detail = ""
        if status == STATUS_BLOCKED:
            state_detail = task["blocked_reason"]
        elif status in {"failed", "error"}:
            state_detail = task["last_error"] or task["failure_message"]
        elif status in {"finished", "done", "success", "completed"}:
            state_detail = task["final_answer"]
        task["state_detail"] = str(state_detail or "")

        if not isinstance(task.get("history"), list):
            task["history"] = [status]

        return task

    def _build_simple_final_answer(self, results: List[Dict[str, Any]]) -> str:
        return build_simple_final_answer(results)

    # ------------------------------------------------------------
    # Trace helpers
    # ------------------------------------------------------------

    def _get_trace_file_for_task(self, task: Dict[str, Any]) -> str:
        if not isinstance(task, dict):
            return os.path.join(self.tasks_root, "unknown_task", "trace.json")

        task_dir = str(task.get("task_dir") or "").strip()
        if not task_dir:
            task_id = self._extract_task_id(task) or "unknown_task"
            task_dir = os.path.join(self.tasks_root, task_id)

        os.makedirs(task_dir, exist_ok=True)

        trace_file = str(task.get("trace_file") or "").strip()
        if trace_file:
            return trace_file

        return os.path.join(task_dir, "trace.json")

    def _load_trace_for_task(self, task: Dict[str, Any]) -> ExecutionTrace:
        trace_path = self._get_trace_file_for_task(task)
        trace = ExecutionTrace(trace_file=trace_path)
        trace.load(trace_path)
        task["trace_file"] = trace_path
        return trace

    def _save_trace_for_task(self, task: Dict[str, Any], trace: ExecutionTrace) -> Optional[str]:
        trace_path = self._get_trace_file_for_task(task)
        saved = trace.save(trace_path)
        task["trace_file"] = trace_path
        return saved

    def _trace_summary(
        self,
        trace: ExecutionTrace,
        task: Dict[str, Any],
        summary: str,
        tick: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        trace.add_summary_event(
            task_id=self._extract_task_id(task),
            summary=summary,
            tick=tick,
            extra=copy.deepcopy(extra) if isinstance(extra, dict) else None,
        )

    def _trace_status(
        self,
        trace: ExecutionTrace,
        task: Dict[str, Any],
        status: str,
        tick: Optional[int] = None,
        final_answer: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        trace.add_status_event(
            task_id=self._extract_task_id(task),
            status=status,
            tick=tick,
            final_answer=final_answer,
            extra=copy.deepcopy(extra) if isinstance(extra, dict) else None,
        )

    def _trace_step(
        self,
        trace: ExecutionTrace,
        task: Dict[str, Any],
        step_index: int,
        step: Dict[str, Any],
        ok: bool,
        result: Optional[Dict[str, Any]] = None,
        error: str = "",
        tick: Optional[int] = None,
    ) -> None:
        trace.add_step_event(
            task_id=self._extract_task_id(task),
            step_index=step_index,
            step=copy.deepcopy(step),
            ok=bool(ok),
            result=copy.deepcopy(result) if isinstance(result, dict) else None,
            error=str(error or ""),
            tick=tick,
        )

    def _trace_replan(
        self,
        trace: ExecutionTrace,
        task: Dict[str, Any],
        tick: Optional[int],
        replan_result: Dict[str, Any],
    ) -> None:
        raw_replan_result = replan_result.get("raw_replan_result", {})
        if not isinstance(raw_replan_result, dict):
            raw_replan_result = {}

        plan = raw_replan_result.get("plan", {})
        if not isinstance(plan, dict):
            plan = {}

        meta = plan.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}

        new_steps = plan.get("steps", [])
        if not isinstance(new_steps, list):
            new_steps = []

        trace.add_replan_event(
            task_id=self._extract_task_id(task),
            failed_step_index=int(meta.get("failed_step_index", -1) or -1),
            failed_step_type=str(meta.get("failed_step_type") or ""),
            error_type=str(meta.get("error_type") or ""),
            failed_error=str(meta.get("failed_error") or ""),
            repair_mode=str(meta.get("repair_mode") or ""),
            replan_count=int(replan_result.get("replan_count", task.get("replan_count", 0)) or 0),
            max_replans=int(meta.get("max_replans", task.get("max_replans", 0)) or 0),
            new_steps=copy.deepcopy(new_steps),
            tick=tick,
        )

    # ------------------------------------------------------------
    # 查詢 API
    # ------------------------------------------------------------

    def get_queue_rows(self) -> Dict[str, Any]:
        queued_rows = self.dispatcher.list_queued()
        return {
            "ok": True,
            "scheduler_build": SCHEDULER_BUILD,
            "tick": getattr(self, "current_tick", 0),
            "count": len(queued_rows),
            "rows": [
                {
                    "task_id": row.get("task_id"),
                    "status": row.get("status"),
                    "priority": row.get("priority"),
                    "current_step_index": row.get("current_step_index"),
                }
                for row in queued_rows
            ],
        }

    def get_queue_snapshot(self) -> Dict[str, Any]:
        repo_tasks = self._list_repo_tasks()
        return {
            "ok": True,
            "scheduler_build": SCHEDULER_BUILD,
            "tick": getattr(self, "current_tick", 0),
            "ready_queue": self.dispatcher.list_queued(),
            "ready_queue_size": len(self.dispatcher.list_queued()),
            "running_tasks": self.dispatcher.list_running(),
            "running_count": len(self.dispatcher.list_running()),
            "worker_pool": self.worker_pool.stats(),
            "workspace_dir": self.workspace_dir,
            "workspace_root": self.workspace_root,
            "shared_dir": self.shared_dir,
            "tasks": repo_tasks,
            "task_count": len(repo_tasks),
        }

    # ------------------------------------------------------------
    # 任務操作 API
    # ------------------------------------------------------------

    def _create_task_record(
        self,
        goal: str,
        priority: int = 0,
        max_retries: int = 0,
        retry_delay: int = 0,
        timeout_ticks: int = 0,
        depends_on: Optional[List[str]] = None,
        initial_status: str = STATUS_CREATED,
        blocked_reason: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if not isinstance(goal, str) or not goal.strip():
            return {"ok": False, "error": "goal is empty"}

        if self.task_repo is None:
            self.task_repo = TaskRepository(db_path=os.path.join(self.workspace_dir, "tasks.json"))

        repo = self.task_repo
        create_task_fn = getattr(repo, "create_task", None)
        add_task_fn = getattr(repo, "add_task", None)

        parsed = self._parse_goal_overrides(goal.strip())
        clean_goal = parsed["clean_goal"]

        planner_result = self._plan_goal(clean_goal)

        override_steps = parsed.get("steps")
        if isinstance(override_steps, list):
            planner_result["steps"] = copy.deepcopy(override_steps)
            planner_result["intent"] = "manual_inline"
            planner_result["final_answer"] = f"已規劃 {len(override_steps)} 個步驟"

        steps = planner_result.get("steps", [])
        if not isinstance(steps, list):
            steps = []

        task_name = f"task_{int(time.time() * 1000)}"
        task_dir = os.path.join(self.tasks_root, task_name)
        trace_file = os.path.join(task_dir, "trace.json")

        raw_depends_on = depends_on if depends_on is not None else kwargs.get("depends_on", None)
        if raw_depends_on is None:
            raw_depends_on = parsed.get("depends_on", [])

        resolve_result = self._normalize_depends_on(raw_depends_on=raw_depends_on, self_task_id=task_name)
        if not isinstance(resolve_result, dict) or not resolve_result.get("ok"):
            return {
                "ok": False,
                "scheduler_build": SCHEDULER_BUILD,
                "error": resolve_result.get("error", "depends_on normalization failed")
                if isinstance(resolve_result, dict)
                else "depends_on normalization failed",
                "depends_on_input": raw_depends_on,
            }

        normalized_depends_on = resolve_result["depends_on"]

        task = {
            "task_id": task_name,
            "task_name": task_name,
            "title": clean_goal,
            "goal": clean_goal,
            "status": initial_status,
            "priority": int(priority),
            "current_step_index": 0,
            "steps": copy.deepcopy(steps),
            "steps_total": len(steps),
            "results": [],
            "step_results": [],
            "last_step_result": None,
            "execution_log": [],
            "final_answer": "",
            "retry_count": 0,
            "max_retries": int(max_retries),
            "retry_delay": int(retry_delay),
            "next_retry_tick": 0,
            "timeout_ticks": int(timeout_ticks),
            "wait_until_tick": 0,
            "created_at": int(time.time()),
            "created_tick": getattr(self, "current_tick", 0),
            "last_run_tick": None,
            "last_failure_tick": None,
            "finished_tick": None,
            "depends_on": normalized_depends_on,
            "blocked_reason": blocked_reason,
            "failure_type": None,
            "failure_message": None,
            "last_error": None,
            "cancel_requested": False,
            "cancel_reason": "",
            "planner_result": copy.deepcopy(planner_result),
            "replan_count": 0,
            "replanned": False,
            "replan_reason": "",
            "max_replans": int(kwargs.get("max_replans", self.default_max_replans) or self.default_max_replans),
            "history": [initial_status],
            "workspace_root": self.workspace_root,
            "workspace_dir": self.tasks_root,
            "shared_dir": self.shared_dir,
            "task_dir": task_dir,
            "plan_file": os.path.join(task_dir, "plan.json"),
            "runtime_state_file": os.path.join(task_dir, "runtime_state.json"),
            "trace_file": trace_file,
            "scheduler_build": SCHEDULER_BUILD,
        }

        task = self._refresh_task_public_fields(task)

        try:
            task = self.task_workspace.create_workspace(task)
            self.task_workspace.save_plan(task, planner_result)
            self.task_workspace.save_task_snapshot(task)
        except Exception as e:
            return {
                "ok": False,
                "scheduler_build": SCHEDULER_BUILD,
                "error": f"task workspace init failed: {e}",
            }

        trace = self._load_trace_for_task(task)
        trace.clear()
        self._trace_summary(
            trace=trace,
            task=task,
            summary="task created",
            tick=getattr(self, "current_tick", 0),
            extra={
                "goal": clean_goal,
                "steps_total": len(steps),
                "depends_on": copy.deepcopy(normalized_depends_on),
            },
        )
        self._trace_status(
            trace=trace,
            task=task,
            status=initial_status,
            tick=getattr(self, "current_tick", 0),
            final_answer="",
            extra={"action": "create_task"},
        )
        self._save_trace_for_task(task=task, trace=trace)

        created = False
        try:
            if callable(create_task_fn):
                create_result = create_task_fn(copy.deepcopy(task))
                if isinstance(create_result, dict):
                    created = True
                else:
                    created = bool(create_result)
            elif callable(add_task_fn):
                created = bool(add_task_fn(copy.deepcopy(task)))
            else:
                return {
                    "ok": False,
                    "scheduler_build": SCHEDULER_BUILD,
                    "error": "task repository has no create_task/add_task",
                }
        except Exception as e:
            return {
                "ok": False,
                "scheduler_build": SCHEDULER_BUILD,
                "error": f"failed to create task: {e}",
                "task": task,
            }

        if not created:
            return {
                "ok": False,
                "scheduler_build": SCHEDULER_BUILD,
                "error": "failed to create task",
                "task": task,
            }

        self._force_repo_task_state(
            task_id=task_name,
            desired_status=initial_status,
            blocked_reason=blocked_reason,
            depends_on=normalized_depends_on,
            full_task=task,
        )

        refreshed = self._get_task_from_repo(task_name)
        if isinstance(refreshed, dict):
            task = refreshed

        return {
            "ok": True,
            "scheduler_build": SCHEDULER_BUILD,
            "message": "task created",
            "task_name": task_name,
            "task": task,
            "planner_result": planner_result,
        }

    def create_task(
        self,
        goal: str,
        priority: int = 0,
        max_retries: int = 0,
        retry_delay: int = 0,
        timeout_ticks: int = 0,
        depends_on: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return self._create_task_record(
            goal=goal,
            priority=priority,
            max_retries=max_retries,
            retry_delay=retry_delay,
            timeout_ticks=timeout_ticks,
            depends_on=depends_on,
            initial_status=STATUS_CREATED,
            blocked_reason="",
            **kwargs,
        )

    def submit_task(
        self,
        goal: str,
        priority: int = 0,
        max_retries: int = 0,
        retry_delay: int = 0,
        timeout_ticks: int = 0,
        depends_on: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        created = self._create_task_record(
            goal=goal,
            priority=priority,
            max_retries=max_retries,
            retry_delay=retry_delay,
            timeout_ticks=timeout_ticks,
            depends_on=depends_on,
            initial_status=STATUS_CREATED,
            blocked_reason="",
            **kwargs,
        )
        if not isinstance(created, dict) or not created.get("ok"):
            return created

        task_id = str(created.get("task_name") or "").strip()
        submit_result = self.submit_existing_task(task_id)
        merged = copy.deepcopy(created)
        if isinstance(submit_result, dict):
            merged.update(
                {
                    "submit_result": submit_result,
                    "status": submit_result.get("status"),
                    "message": submit_result.get("message", created.get("message")),
                }
            )
        return merged

    def submit_existing_task(self, task_id: str) -> Dict[str, Any]:
        if not isinstance(task_id, str) or not task_id.strip():
            return {
                "ok": False,
                "scheduler_build": SCHEDULER_BUILD,
                "error": "task_id is empty",
            }

        task_id = task_id.strip()

        task = self._get_task_from_repo(task_id)
        if not isinstance(task, dict):
            return {
                "ok": False,
                "scheduler_build": SCHEDULER_BUILD,
                "error": "task not found",
                "task_id": task_id,
            }

        task = self._hydrate_task_from_workspace(task)
        trace = self._load_trace_for_task(task)

        status = str(task.get("status") or "").strip().lower()
        if status in TERMINAL_STATUSES:
            self._trace_status(
                trace=trace,
                task=task,
                status=status,
                tick=getattr(self, "current_tick", 0),
                final_answer=str(task.get("final_answer") or ""),
                extra={
                    "action": "submit_existing_task_rejected_terminal",
                    "error": "task already terminal",
                },
            )
            self._save_trace_for_task(task=task, trace=trace)
            return {
                "ok": False,
                "scheduler_build": SCHEDULER_BUILD,
                "error": "task already terminal",
                "task_id": task_id,
                "status": status,
            }

        deps_ready, blocked_reason = self._task_dependencies_satisfied(task)

        if deps_ready:
            task["status"] = "queued"
            task["blocked_reason"] = ""
            task["scheduler_build"] = SCHEDULER_BUILD
            task["history"] = self._append_history(task.get("history"), "queued")
            self._persist_task_payload(task_id=task_id, task=task)

            refreshed = self._get_task_from_repo(task_id)
            if isinstance(refreshed, dict):
                self._enqueue_repo_task_if_ready(refreshed, overwrite=True)
                task = refreshed

            self._trace_status(
                trace=trace,
                task=task,
                status="queued",
                tick=getattr(self, "current_tick", 0),
                final_answer="",
                extra={"action": "submit_existing_task"},
            )
            self._save_trace_for_task(task=task, trace=trace)

            return {
                "ok": True,
                "scheduler_build": SCHEDULER_BUILD,
                "task_name": task_id,
                "task_id": task_id,
                "status": "queued",
                "message": "task submitted",
            }

        task["status"] = STATUS_BLOCKED
        task["blocked_reason"] = blocked_reason
        task["last_error"] = ""
        task["failure_message"] = ""
        task["scheduler_build"] = SCHEDULER_BUILD
        task["history"] = self._append_history(task.get("history"), STATUS_BLOCKED)
        self._persist_task_payload(task_id=task_id, task=task)

        self._trace_status(
            trace=trace,
            task=task,
            status=STATUS_BLOCKED,
            tick=getattr(self, "current_tick", 0),
            final_answer="",
            extra={
                "action": "submit_existing_task_blocked",
                "blocked_reason": blocked_reason,
            },
        )
        self._save_trace_for_task(task=task, trace=trace)

        return {
            "ok": True,
            "scheduler_build": SCHEDULER_BUILD,
            "task_name": task_id,
            "task_id": task_id,
            "status": STATUS_BLOCKED,
            "message": "task submitted but blocked by dependencies",
            "blocked_reason": blocked_reason,
        }

    def pause_task(self, task_name: str) -> Dict[str, Any]:
        result = self._set_status(task_name, "paused")
        self.scheduler_queue.cancel(task_name)
        return result

    def resume_task(self, task_name: str) -> Dict[str, Any]:
        task = self._get_task_from_repo(task_name)
        if not isinstance(task, dict):
            return {
                "ok": False,
                "scheduler_build": SCHEDULER_BUILD,
                "error": "task not found",
                "task_name": task_name,
            }

        task_status = str(task.get("status") or "").strip().lower()
        if task_status in TERMINAL_STATUSES:
            return {
                "ok": False,
                "scheduler_build": SCHEDULER_BUILD,
                "error": "task already terminal",
                "task_name": task_name,
                "status": task_status,
            }

        deps_ready, blocked_reason = self._task_dependencies_satisfied(task)
        if deps_ready:
            result = self._set_status(task_name, "queued")
            refreshed = self._get_task_from_repo(task_name)
            if isinstance(refreshed, dict):
                self._enqueue_repo_task_if_ready(refreshed, overwrite=True)
            return result

        self._sync_blocked_state(task_id=task_name, blocked_reason=blocked_reason)
        result = self._set_status(task_name, STATUS_BLOCKED)
        return {
            **result,
            "message": "task still blocked by dependencies",
        }

    def cancel_task(self, task_name: str) -> Dict[str, Any]:
        result = self._set_status(task_name, "cancelled")
        self.scheduler_queue.cancel(task_name)
        self.worker_pool.release_by_task(task_name)
        return result

    def set_task_priority(self, task_name: str, priority: int) -> Dict[str, Any]:
        repo = self.task_repo
        update_task_field_fn = getattr(repo, "update_task_field", None)

        if not callable(update_task_field_fn):
            return {
                "ok": False,
                "scheduler_build": SCHEDULER_BUILD,
                "error": "task_repo.update_task_field not available",
                "task_name": task_name,
                "priority": priority,
            }

        ok = bool(update_task_field_fn(task_name, "priority", int(priority)))
        if not ok:
            return {
                "ok": False,
                "scheduler_build": SCHEDULER_BUILD,
                "error": "task not found or priority update failed",
                "task_name": task_name,
                "priority": priority,
            }

        task = self._get_task_from_repo(task_name)
        if isinstance(task, dict):
            task["priority"] = int(priority)
            self._save_task_snapshot_safe(task)
            self.scheduler_queue.update_priority(task_name, int(priority))

        return {
            "ok": True,
            "scheduler_build": SCHEDULER_BUILD,
            "task_name": task_name,
            "priority": int(priority),
            "message": "priority updated",
        }

    def _set_status(self, task_name: str, status: str) -> Dict[str, Any]:
        repo = self.task_repo
        set_task_status_fn = getattr(repo, "set_task_status", None)

        if not callable(set_task_status_fn):
            task = self._get_task_from_repo(task_name)
            if not isinstance(task, dict):
                return {
                    "ok": False,
                    "scheduler_build": SCHEDULER_BUILD,
                    "error": "task_repo.set_task_status not available and task not found",
                    "task_name": task_name,
                    "status": status,
                }

            task["status"] = status
            task["history"] = self._append_history(task.get("history"), status)
            self._persist_task_payload(task_id=task_name, task=task)
            return {
                "ok": True,
                "scheduler_build": SCHEDULER_BUILD,
                "task_name": task_name,
                "status": status,
                "message": "task status updated",
            }

        ok = bool(set_task_status_fn(task_name, status))
        if not ok:
            return {
                "ok": False,
                "scheduler_build": SCHEDULER_BUILD,
                "error": "task not found or status update failed",
                "task_name": task_name,
                "status": status,
            }

        task = self._get_task_from_repo(task_name)
        if isinstance(task, dict):
            task["status"] = status
            task["history"] = self._append_history(task.get("history"), status)
            self._save_task_snapshot_safe(task)
            self._persist_task_payload(task_id=task_name, task=task)

        return {
            "ok": True,
            "scheduler_build": SCHEDULER_BUILD,
            "task_name": task_name,
            "status": status,
            "message": "task status updated",
        }

    # ------------------------------------------------------------
    # Queue / dispatcher / worker sync
    # ------------------------------------------------------------

    def rebuild_ready_queue(self) -> List[str]:
        tasks = self._list_repo_tasks()
        if not isinstance(tasks, list):
            return []

        synced_ids: List[str] = []

        for task in tasks:
            if not isinstance(task, dict):
                continue

            task = self._hydrate_task_from_workspace(task)
            task_id = self._extract_task_id(task)
            if not task_id:
                continue

            status = str(task.get("status") or "").strip().lower()

            if status in TERMINAL_STATUSES:
                self.worker_pool.release_by_task(task_id)
                continue

            if self._enqueue_repo_task_if_ready(task):
                synced_ids.append(task_id)

        return synced_ids

    def _enqueue_repo_task_if_ready(self, task: Dict[str, Any], overwrite: bool = False) -> bool:
        task = self._hydrate_task_from_workspace(task)

        task_id = self._extract_task_id(task)
        if not task_id:
            return False

        if self.worker_pool.get_running_task(task_id) is not None:
            return False

        status = str(task.get("status") or "").strip().lower()
        if status in TERMINAL_STATUSES:
            return False

        if self._queue_contains_task(task_id) and not overwrite:
            return False

        deps_ready, blocked_reason = self._task_dependencies_satisfied(task)

        if not deps_ready:
            self._sync_blocked_state(task_id=task_id, blocked_reason=blocked_reason)
            return False

        self._sync_unblocked_state(task_id=task_id)

        refreshed_task = self._get_task_from_repo(task_id)
        if isinstance(refreshed_task, dict):
            task = refreshed_task

        status = str(task.get("status") or "").strip().lower()
        if status not in READY_STATUSES:
            return False

        scheduled_task = self._repo_task_to_scheduled_task(task)
        return self.scheduler_queue.enqueue(scheduled_task, overwrite=overwrite)

    def _repo_task_to_scheduled_task(self, task: Dict[str, Any]) -> ScheduledTask:
        task = self._hydrate_task_from_workspace(task)

        task_id = self._extract_task_id(task) or f"task_{int(time.time() * 1000)}"

        created_at_raw = task.get("created_at", time.time())
        try:
            created_at = float(created_at_raw)
        except Exception:
            created_at = time.time()

        current_step_index = task.get("current_step_index")
        try:
            current_step_index = int(current_step_index) if current_step_index is not None else None
        except Exception:
            current_step_index = None

        full_payload = copy.deepcopy(task)
        full_payload["current_step_index"] = current_step_index

        return ScheduledTask(
            task_id=task_id,
            title=str(task.get("title") or task.get("goal") or task_id),
            priority=int(task.get("priority", 0)),
            created_at=created_at,
            status=str(task.get("status") or STATUS_QUEUED),
            retry_count=int(task.get("retry_count", 0)),
            max_retries=int(task.get("max_retries", 0)),
            payload=full_payload,
            metadata={
                "repo_status": task.get("status"),
                "task_name": task.get("task_name"),
                "blocked_reason": task.get("blocked_reason"),
                "scheduler_build": task.get("scheduler_build", SCHEDULER_BUILD),
                "goal": task.get("goal"),
                "steps_total": task.get("steps_total"),
                "current_step_index": current_step_index,
                "depends_on": copy.deepcopy(task.get("depends_on", [])),
            },
            last_error=task.get("last_error"),
            result=task.get("final_answer"),
            started_at=None,
            finished_at=None,
        )

    def _extract_task_id(self, task: Dict[str, Any]) -> str:
        return str(
            task.get("task_id")
            or task.get("task_name")
            or task.get("id")
            or ""
        ).strip()

    def _queue_contains_task(self, task_id: str) -> bool:
        contains_fn = getattr(self.scheduler_queue, "contains", None)
        if callable(contains_fn):
            try:
                return bool(contains_fn(task_id))
            except Exception:
                pass

        try:
            queued_rows = self.dispatcher.list_queued()
            if isinstance(queued_rows, list):
                for row in queued_rows:
                    if not isinstance(row, dict):
                        continue
                    row_task_id = str(row.get("task_id") or "").strip()
                    if row_task_id == task_id:
                        return True
        except Exception:
            pass

        try:
            running_rows = self.dispatcher.list_running()
            if isinstance(running_rows, list):
                for row in running_rows:
                    if not isinstance(row, dict):
                        continue
                    row_task_id = str(row.get("task_id") or "").strip()
                    if row_task_id == task_id:
                        return True
        except Exception:
            pass

        return False

    # ------------------------------------------------------------
    # DAG helpers
    # ------------------------------------------------------------

    def _task_dependencies_satisfied(self, task: Dict[str, Any]) -> Tuple[bool, str]:
        task = self._hydrate_task_from_workspace(task)
        depends_on = task.get("depends_on", [])

        if depends_on is None:
            return True, ""

        if not isinstance(depends_on, list):
            return False, "invalid depends_on"

        normalized_deps = self._normalize_depends_on(depends_on)
        if isinstance(normalized_deps, dict):
            normalized_deps = normalized_deps.get("depends_on", [])
        if not isinstance(normalized_deps, list):
            normalized_deps = []

        task_id = self._extract_task_id(task)
        if task_id and task_id in normalized_deps:
            return False, f"self dependency: {task_id}"

        if not normalized_deps:
            return True, ""

        for dep_id in normalized_deps:
            dep_task = self._get_task_from_repo(dep_id)
            if not isinstance(dep_task, dict):
                return False, f"dependency not found: {dep_id}"

            dep_status = str(dep_task.get("status") or "").strip().lower()
            if dep_status not in {"finished", "done", "success", "completed"}:
                return False, f"waiting dependency: {dep_id}"

        return True, ""

    def _unblock_tasks_if_dependencies_done(self) -> None:
        tasks = self._list_repo_tasks()
        if not isinstance(tasks, list):
            return

        for task in tasks:
            if not isinstance(task, dict):
                continue

            task = self._hydrate_task_from_workspace(task)

            task_id = self._extract_task_id(task)
            if not task_id:
                continue

            status = str(task.get("status") or "").strip().lower()
            if status != STATUS_BLOCKED:
                continue

            deps_ready, blocked_reason = self._task_dependencies_satisfied(task)

            if deps_ready:
                task["status"] = "queued"
                task["blocked_reason"] = ""
                task["history"] = self._append_history(task.get("history"), "queued")
                task["scheduler_build"] = SCHEDULER_BUILD
                self._persist_task_payload(task_id=task_id, task=task)
                self._enqueue_repo_task_if_ready(task, overwrite=True)

                trace = self._load_trace_for_task(task)
                self._trace_status(
                    trace=trace,
                    task=task,
                    status="queued",
                    tick=getattr(self, "current_tick", 0),
                    final_answer="",
                    extra={
                        "action": "unblocked_by_dependencies",
                    },
                )
                self._save_trace_for_task(task=task, trace=trace)
            else:
                self._sync_blocked_state(task_id=task_id, blocked_reason=blocked_reason)

    def _normalize_depends_on(
        self,
        raw_depends_on: Any,
        self_task_id: Optional[str] = None,
    ) -> Any:
        if self_task_id is None:
            return self._normalize_depends_on_simple(raw_depends_on)

        return self._normalize_depends_on_resolved(
            raw_depends_on=raw_depends_on,
            self_task_id=self_task_id,
        )

    def _normalize_depends_on_simple(self, raw_depends_on: Any) -> List[str]:
        if raw_depends_on is None:
            return []

        if isinstance(raw_depends_on, str):
            text = raw_depends_on.strip()
            return [text] if text else []

        if not isinstance(raw_depends_on, list):
            return []

        normalized: List[str] = []
        seen = set()

        for dep in raw_depends_on:
            dep_text = str(dep or "").strip()
            if not dep_text:
                continue
            if dep_text in seen:
                continue
            seen.add(dep_text)
            normalized.append(dep_text)

        return normalized

    def _normalize_depends_on_resolved(
        self,
        raw_depends_on: Any,
        self_task_id: str,
    ) -> Dict[str, Any]:
        if raw_depends_on is None:
            return {"ok": True, "depends_on": []}

        if isinstance(raw_depends_on, str):
            raw_depends_on = [raw_depends_on]

        if not isinstance(raw_depends_on, list):
            return {"ok": False, "error": "depends_on must be a list"}

        normalized: List[str] = []
        seen = set()

        for dep in raw_depends_on:
            dep_text = str(dep or "").strip()
            if not dep_text:
                continue

            resolved_task_id = self._resolve_dependency_reference(dep_text)

            if not resolved_task_id:
                return {
                    "ok": False,
                    "error": f"failed to create task: depends_on task not found: {dep_text}",
                }

            if resolved_task_id == self_task_id:
                return {
                    "ok": False,
                    "error": f"failed to create task: self dependency not allowed: {dep_text}",
                }

            if resolved_task_id in seen:
                continue

            seen.add(resolved_task_id)
            normalized.append(resolved_task_id)

        return {
            "ok": True,
            "depends_on": normalized,
        }

    def _resolve_dependency_reference(self, ref: str) -> Optional[str]:
        ref_text = str(ref or "").strip()
        if not ref_text:
            return None

        tasks = self._list_repo_tasks()
        if not tasks:
            return None

        exact_id_matches: List[str] = []
        for task in tasks:
            task_id = self._extract_task_id(task)
            task_name = str(task.get("task_name") or "").strip()

            if ref_text == task_id or ref_text == task_name:
                if task_id:
                    exact_id_matches.append(task_id)

        exact_id_matches = list(dict.fromkeys(exact_id_matches))
        if len(exact_id_matches) == 1:
            return exact_id_matches[0]
        if len(exact_id_matches) > 1:
            return None

        alias_matches: List[str] = []
        for task in tasks:
            task_id = self._extract_task_id(task)
            if not task_id:
                continue

            title = str(task.get("title") or "").strip()
            goal = str(task.get("goal") or "").strip()

            if ref_text == title or ref_text == goal:
                alias_matches.append(task_id)

        alias_matches = list(dict.fromkeys(alias_matches))
        if len(alias_matches) == 1:
            return alias_matches[0]
        if len(alias_matches) > 1:
            return None

        return None

    def _force_repo_task_state(
        self,
        task_id: str,
        desired_status: str,
        blocked_reason: str,
        depends_on: List[str],
        full_task: Dict[str, Any],
    ) -> None:
        task = self._get_task_from_repo(task_id)
        if not isinstance(task, dict):
            task = copy.deepcopy(full_task)
        else:
            merged = copy.deepcopy(task)
            merged.update(copy.deepcopy(full_task))
            task = merged

        task["status"] = desired_status
        task["depends_on"] = copy.deepcopy(depends_on)
        task["blocked_reason"] = blocked_reason or ""
        task["scheduler_build"] = SCHEDULER_BUILD
        task["history"] = [desired_status]

        self._persist_task_payload(task_id=task_id, task=task)

        set_status_fn = getattr(self.task_repo, "set_task_status", None)
        if callable(set_status_fn):
            try:
                set_status_fn(task_id, desired_status)
            except Exception:
                pass

        update_task_field_fn = getattr(self.task_repo, "update_task_field", None)
        if callable(update_task_field_fn):
            try:
                update_task_field_fn(task_id, "depends_on", copy.deepcopy(depends_on))
                update_task_field_fn(task_id, "blocked_reason", blocked_reason or "")
                update_task_field_fn(task_id, "scheduler_build", SCHEDULER_BUILD)
                update_task_field_fn(task_id, "history", [desired_status])
            except Exception:
                pass


    def _ensure_task_paths(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task, dict):
            return task

        task_id = self._extract_task_id(task) or str(task.get("task_name") or "unknown_task").strip() or "unknown_task"
        task["task_name"] = str(task.get("task_name") or task_id).strip() or task_id

        task_dir = str(task.get("task_dir") or "").strip()
        if not task_dir:
            task_dir = os.path.join(self.tasks_root, task_id)
        task["task_dir"] = task_dir

        task["workspace_root"] = str(task.get("workspace_root") or self.workspace_root)
        task["workspace_dir"] = str(task.get("workspace_dir") or self.tasks_root)
        task["shared_dir"] = str(task.get("shared_dir") or self.shared_dir)

        task["plan_file"] = str(task.get("plan_file") or os.path.join(task_dir, "plan.json"))
        task["runtime_state_file"] = str(task.get("runtime_state_file") or os.path.join(task_dir, "runtime_state.json"))
        task["trace_file"] = str(task.get("trace_file") or os.path.join(task_dir, "trace.json"))
        task["result_file"] = str(task.get("result_file") or os.path.join(task_dir, "result.json"))
        task["execution_log_file"] = str(task.get("execution_log_file") or os.path.join(task_dir, "execution_log.json"))
        task["snapshot_file"] = str(task.get("snapshot_file") or os.path.join(task_dir, "task_snapshot.json"))
        return task

    def _detect_artifact_scope(self, full_path: str) -> str:
        path = os.path.abspath(str(full_path or "").strip()) if str(full_path or "").strip() else ""
        if not path:
            return "task"

        shared_root = os.path.abspath(self.shared_dir)
        try:
            if os.path.commonpath([path, shared_root]) == shared_root:
                return "shared"
        except Exception:
            pass

        return "task"

    def _to_logical_path(self, full_path: str) -> str:
        path = os.path.abspath(str(full_path or "").strip()) if str(full_path or "").strip() else ""
        if not path:
            return ""

        shared_root = os.path.abspath(self.shared_dir)
        tasks_root = os.path.abspath(self.tasks_root)

        try:
            if os.path.commonpath([path, shared_root]) == shared_root:
                rel = os.path.relpath(path, shared_root).replace("\\", "/")
                return f"workspace/shared/{rel}" if rel != "." else "workspace/shared"
        except Exception:
            pass

        try:
            if os.path.commonpath([path, tasks_root]) == tasks_root:
                rel = os.path.relpath(path, tasks_root).replace("\\", "/")
                return f"workspace/tasks/{rel}" if rel != "." else "workspace/tasks"
        except Exception:
            pass

        return path.replace("\\", "/")

    def _make_artifact_entry(self, full_path: str) -> Dict[str, Any]:
        normalized_full_path = os.path.abspath(str(full_path or "").strip()) if str(full_path or "").strip() else ""
        exists = bool(normalized_full_path and os.path.exists(normalized_full_path))
        logical_path = self._to_logical_path(normalized_full_path)
        scope = self._detect_artifact_scope(normalized_full_path)

        return {
            "path": normalized_full_path,
            "full_path": normalized_full_path,
            "logical_path": logical_path,
            "exists": exists,
            "name": os.path.basename(normalized_full_path) if normalized_full_path else "",
            "scope": scope,
        }

    def _extract_result_artifact_paths(self, task: Dict[str, Any]) -> List[str]:
        candidates: List[str] = []

        for key in ("result_file", "execution_log_file", "plan_file", "runtime_state_file", "trace_file", "task_dir"):
            value = str(task.get(key) or "").strip()
            if value:
                candidates.append(value)

        results = task.get("results", [])
        if not isinstance(results, list):
            results = []

        for item in results:
            if not isinstance(item, dict):
                continue

            step_payloads = [item]
            nested = item.get("result")
            if isinstance(nested, dict):
                step_payloads.append(nested)

            for payload in step_payloads:
                if not isinstance(payload, dict):
                    continue
                for key in ("full_path", "path", "output_path", "file_path", "result_path"):
                    value = str(payload.get(key) or "").strip()
                    if value:
                        candidates.append(value)

        deduped: List[str] = []
        seen = set()
        for raw_path in candidates:
            path = str(raw_path or "").strip()
            if not path:
                continue
            normalized = path
            if not os.path.isabs(normalized):
                normalized = self._resolve_step_path(
                    normalized,
                    task_dir=str(task.get("task_dir") or self.tasks_root),
                    shared_dir=self.shared_dir,
                )
            normalized = os.path.abspath(normalized)
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)

        return deduped

    def _normalize_task_schema(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task, dict):
            return task

        normalized = copy.deepcopy(task)
        normalized = self._ensure_task_paths(normalized)

        defaults = {
            "task_id": self._extract_task_id(normalized),
            "task_name": self._extract_task_id(normalized) or str(normalized.get("task_name") or "").strip(),
            "goal": str(normalized.get("goal") or normalized.get("title") or ""),
            "title": str(normalized.get("title") or normalized.get("goal") or ""),
            "status": str(normalized.get("status") or STATUS_CREATED).strip().lower() or STATUS_CREATED,
            "priority": int(normalized.get("priority", 0) or 0),
            "current_step_index": int(normalized.get("current_step_index", 0) or 0),
            "steps": copy.deepcopy(normalized.get("steps", [])) if isinstance(normalized.get("steps"), list) else [],
            "results": copy.deepcopy(normalized.get("results", [])) if isinstance(normalized.get("results"), list) else [],
            "step_results": copy.deepcopy(normalized.get("step_results", [])) if isinstance(normalized.get("step_results"), list) else [],
            "execution_log": copy.deepcopy(normalized.get("execution_log", [])) if isinstance(normalized.get("execution_log"), list) else [],
            "depends_on": copy.deepcopy(normalized.get("depends_on", [])) if isinstance(normalized.get("depends_on"), list) else [],
            "history": copy.deepcopy(normalized.get("history", [])) if isinstance(normalized.get("history"), list) else [],
            "final_answer": str(normalized.get("final_answer") or ""),
            "last_error": str(normalized.get("last_error") or ""),
            "failure_message": str(normalized.get("failure_message") or ""),
            "blocked_reason": str(normalized.get("blocked_reason") or ""),
            "state_detail": str(normalized.get("state_detail") or ""),
            "retry_count": int(normalized.get("retry_count", 0) or 0),
            "replan_count": int(normalized.get("replan_count", 0) or 0),
            "replan_decision": str(normalized.get("replan_decision") or ""),
            "replan_summary": str(normalized.get("replan_summary") or ""),
            "replan_failed_step_type": str(normalized.get("replan_failed_step_type") or ""),
            "replan_repairable": normalized.get("replan_repairable", None),
            "completion_mode": str(normalized.get("completion_mode") or ""),
            "verification_required": normalized.get("verification_required", None),
            "verification_passed": normalized.get("verification_passed", None),
            "result_path": str(normalized.get("result_path") or ""),
            "result_logical_path": str(normalized.get("result_logical_path") or ""),
            "result_exists": bool(normalized.get("result_exists", False)),
            "openable": bool(normalized.get("openable", False)),
            "open_targets": copy.deepcopy(normalized.get("open_targets", [])) if isinstance(normalized.get("open_targets"), list) else [],
            "artifacts": copy.deepcopy(normalized.get("artifacts", [])) if isinstance(normalized.get("artifacts"), list) else [],
            "updated_at": int(normalized.get("updated_at", 0) or 0),
        }

        normalized.update(defaults)
        normalized["steps_total"] = len(normalized["steps"])

        if normalized["last_step_result"] is None if "last_step_result" in normalized else True:
            normalized["last_step_result"] = None
        else:
            normalized["last_step_result"] = copy.deepcopy(normalized.get("last_step_result"))

        normalized = self._normalize_public_status_fields(normalized)

        if not normalized["history"]:
            normalized["history"] = [normalized["status"]]

        return normalized

    def _backfill_replan_decision_fields(self, task: Dict[str, Any], replan_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not isinstance(task, dict):
            return task

        decision = str(task.get("replan_decision") or "").strip()
        summary = str(task.get("replan_summary") or "").strip()
        failed_step_type = str(task.get("replan_failed_step_type") or "").strip()
        repairable = task.get("replan_repairable", None)

        source = replan_result if isinstance(replan_result, dict) else {}
        if not decision:
            decision = str(source.get("decision") or "").strip()
        if not summary:
            summary = str(source.get("summary") or "").strip()
        if not failed_step_type:
            failed_step_type = str(source.get("failed_step_type") or "").strip()
        if repairable is None and "repairable" in source:
            repairable = source.get("repairable")

        if not failed_step_type:
            failed_step_type = self._get_failed_step_type(task)

        if not decision and (summary or failed_step_type):
            decision = "accepted" if bool(task.get("replanned")) else "skipped"

        if not summary and decision == "skipped" and failed_step_type:
            summary = f"step type not repairable: {failed_step_type}"

        if repairable is None and failed_step_type:
            repairable = failed_step_type in {"verify", "read_file", "run_python", "command", "write_file", "llm", "llm_generate"}

        task["replan_decision"] = decision
        task["replan_summary"] = summary
        task["replan_failed_step_type"] = failed_step_type
        task["replan_repairable"] = repairable
        return task

    def _normalize_verify_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        normalized = copy.deepcopy(step if isinstance(step, dict) else {})
        if not isinstance(normalized, dict):
            return {}

        path = str(normalized.get("path") or "").strip()
        contains = normalized.get("contains", None)
        equals = normalized.get("equals", None)
        exists = normalized.get("exists", None)

        if path and "," in path and ("contains=" in path or "equals=" in path or "exists=" in path):
            parts = [p.strip() for p in path.split(",") if p.strip()]
            if parts:
                first = parts[0]
                if not first.startswith("contains=") and not first.startswith("equals=") and not first.startswith("exists="):
                    path = first
                    for item in parts[1:]:
                        if item.startswith("contains=") and contains is None:
                            contains = item.split("=", 1)[1]
                        elif item.startswith("equals=") and equals is None:
                            equals = item.split("=", 1)[1]
                        elif item.startswith("exists=") and exists is None:
                            raw = item.split("=", 1)[1].strip().lower()
                            exists = raw in {"1", "true", "yes", "y"}

        normalized["path"] = path
        normalized["scope"] = self._normalize_step_scope(normalized.get("scope", None))
        if contains is not None:
            normalized["contains"] = contains
        if equals is not None:
            normalized["equals"] = equals
        if exists is not None:
            normalized["exists"] = exists
        return normalized

    def _verify_step_failure_repairable(self, task: Dict[str, Any]) -> bool:
        failed_step_type = self._get_failed_step_type(task)
        if failed_step_type != "verify":
            return failed_step_type in {"read_file", "run_python", "command", "write_file", "llm", "llm_generate"}

        error_text = str(task.get("last_error") or task.get("failure_message") or "").strip().lower()

        not_repairable_signals = [
            "file not found",
            "path is empty",
            "requires path",
            "requires contains",
            "requires equals",
            "requires exists",
            "invalid verify",
        ]
        for signal in not_repairable_signals:
            if signal in error_text:
                return False

        repairable_signals = [
            "contains failed",
            "equals failed",
            "verify failed",
        ]
        for signal in repairable_signals:
            if signal in error_text:
                return True

        return False

    def _infer_completion_fields(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task, dict):
            return task

        steps = task.get("steps", [])
        if not isinstance(steps, list):
            steps = []

        has_verify_step = False
        for step in steps:
            if isinstance(step, dict) and str(step.get("type") or "").strip().lower() == "verify":
                has_verify_step = True
                break

        status = str(task.get("status") or "").strip().lower()
        completion_mode = str(task.get("completion_mode") or "").strip().lower()
        verification_required = task.get("verification_required", None)
        verification_passed = task.get("verification_passed", None)

        if not completion_mode:
            completion_mode = "verified" if has_verify_step else "execution_only"

        if verification_required is None:
            verification_required = bool(has_verify_step)

        if verification_passed is None:
            if not bool(verification_required):
                verification_passed = None
            elif status in {"finished", "done", "success", "completed"}:
                verification_passed = True
            elif status in {"failed", "error"}:
                verification_passed = False
            else:
                verification_passed = None

        task["completion_mode"] = completion_mode
        task["verification_required"] = verification_required
        task["verification_passed"] = verification_passed
        return task

    def _clear_stale_replan_fields(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task, dict):
            return task

        status = str(task.get("status") or "").strip().lower()
        if status not in {"finished", "done", "success", "completed"}:
            return task

        # If the task finished and was not actually replanned, stale replan decision
        # fields should not leak into public outputs.
        if not bool(task.get("replanned", False)):
            task["replan_decision"] = ""
            task["replan_summary"] = ""
            task["replan_failed_step_type"] = ""
            task["replan_repairable"] = None

        return task

    def _build_public_task_record(self, task: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_task_schema(task)
        normalized = self._backfill_replan_decision_fields(normalized)
        normalized = self._infer_completion_fields(normalized)
        normalized = self._clear_stale_replan_fields(normalized)

        result_path = str(normalized.get("result_path") or "")
        result_logical_path = str(normalized.get("result_logical_path") or "")
        if result_path and not result_logical_path:
            result_logical_path = self._to_logical_path(result_path)

        open_targets = copy.deepcopy(normalized.get("open_targets", [])) if isinstance(normalized.get("open_targets"), list) else []
        artifacts = copy.deepcopy(normalized.get("artifacts", [])) if isinstance(normalized.get("artifacts"), list) else []
        if open_targets and not artifacts:
            artifacts = copy.deepcopy(open_targets)

        record = {
            "task_id": self._extract_task_id(normalized),
            "goal": str(normalized.get("goal") or ""),
            "status": str(normalized.get("status") or STATUS_CREATED),
            "current_step_index": int(normalized.get("current_step_index", 0) or 0),
            "steps_total": int(normalized.get("steps_total", len(normalized.get("steps", []))) or 0),
            "current_step": copy.deepcopy(normalized.get("current_step")) if isinstance(normalized.get("current_step"), dict) else None,
            "final_answer": str(normalized.get("final_answer") or ""),
            "last_error": str(normalized.get("last_error") or ""),
            "blocked_reason": str(normalized.get("blocked_reason") or ""),
            "state_detail": str(normalized.get("state_detail") or ""),
            "result_path": result_path,
            "result_logical_path": result_logical_path,
            "result_exists": bool(normalized.get("result_exists")),
            "openable": bool(normalized.get("openable")),
            "task_dir": str(normalized.get("task_dir") or ""),
            "task_dir_logical_path": self._to_logical_path(str(normalized.get("task_dir") or "")),
            "plan_file": str(normalized.get("plan_file") or ""),
            "plan_file_logical_path": self._to_logical_path(str(normalized.get("plan_file") or "")),
            "runtime_state_file": str(normalized.get("runtime_state_file") or ""),
            "runtime_state_file_logical_path": self._to_logical_path(str(normalized.get("runtime_state_file") or "")),
            "trace_file": str(normalized.get("trace_file") or ""),
            "trace_file_logical_path": self._to_logical_path(str(normalized.get("trace_file") or "")),
            "execution_log_file": str(normalized.get("execution_log_file") or ""),
            "execution_log_file_logical_path": self._to_logical_path(str(normalized.get("execution_log_file") or "")),
            "updated_at": int(normalized.get("updated_at", 0) or 0),
            "replan_count": int(normalized.get("replan_count", 0) or 0),
            "replanned": bool(normalized.get("replanned", False)),
            "replan_reason": str(normalized.get("replan_reason") or ""),
            "replan_decision": str(normalized.get("replan_decision") or ""),
            "replan_summary": str(normalized.get("replan_summary") or ""),
            "replan_failed_step_type": str(normalized.get("replan_failed_step_type") or ""),
            "replan_repairable": normalized.get("replan_repairable", None),
            "completion_mode": str(normalized.get("completion_mode") or ""),
            "verification_required": normalized.get("verification_required", None),
            "verification_passed": normalized.get("verification_passed", None),
            "history": copy.deepcopy(normalized.get("history", [])) if isinstance(normalized.get("history"), list) else [],
            "open_targets": open_targets,
            "artifacts": artifacts,
        }
        return record

    def _refresh_task_public_fields(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task, dict):
            return task

        task = self._normalize_task_schema(task)

        steps = task.get("steps", [])
        current_step_index = int(task.get("current_step_index", 0) or 0)
        current_step = copy.deepcopy(task.get("current_step")) if isinstance(task.get("current_step"), dict) else None

        if not isinstance(task.get("results"), list):
            task["results"] = []
        if not isinstance(task.get("step_results"), list):
            task["step_results"] = copy.deepcopy(task.get("results", []))
        if task.get("last_step_result") is None and task.get("step_results"):
            try:
                task["last_step_result"] = copy.deepcopy(task["step_results"][-1])
            except Exception:
                pass
        if not isinstance(task.get("execution_log"), list):
            task["execution_log"] = []

        if task["status"] in {"finished", "done", "success", "completed"} and not str(task.get("final_answer") or "").strip():
            task["final_answer"] = self._build_simple_final_answer(task.get("results", []))

        artifact_paths = self._extract_result_artifact_paths(task)
        artifact_entries = [self._make_artifact_entry(path) for path in artifact_paths]

        preferred_result_path = ""
        for entry in artifact_entries:
            path = str(entry.get("path") or "").strip()
            if not path:
                continue
            if path.endswith("result.json") and entry.get("exists"):
                preferred_result_path = path
                break
        if not preferred_result_path:
            for entry in artifact_entries:
                if bool(entry.get("exists")) and os.path.isfile(str(entry.get("path") or "")):
                    preferred_result_path = str(entry.get("path") or "")
                    break
        if not preferred_result_path and artifact_entries:
            preferred_result_path = str(artifact_entries[0].get("path") or "")

        result_exists = bool(preferred_result_path and os.path.exists(preferred_result_path))
        if not result_exists:
            result_exists = bool(
                str(task.get("final_answer") or "").strip()
                or task.get("results")
                or task.get("execution_log")
            )

        openable = bool(
            result_exists
            or any(bool(entry.get("exists")) for entry in artifact_entries)
            or os.path.exists(str(task.get("task_dir") or ""))
        )

        try:
            updated_at = int(time.time())
        except Exception:
            updated_at = 0

        task["result_path"] = preferred_result_path
        task["result_logical_path"] = self._to_logical_path(preferred_result_path)
        task["result_exists"] = result_exists
        task["openable"] = openable
        task["open_targets"] = artifact_entries
        task["artifacts"] = copy.deepcopy(artifact_entries)
        task["updated_at"] = updated_at

        task = self._infer_completion_fields(task)
        task = self._clear_stale_replan_fields(task)
        task["public_snapshot"] = self._build_public_task_record(task)

        return task

    # ------------------------------------------------------------
    # hydration
    # ------------------------------------------------------------

    def _hydrate_task_from_workspace(self, task: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(task, dict):
            return task

        hydrated = copy.deepcopy(task)

        task_id = self._extract_task_id(hydrated)
        if not task_id:
            return hydrated

        hydrated = self._ensure_task_paths(hydrated)

        task_dir = str(hydrated.get("task_dir") or "").strip()
        plan_file = str(hydrated.get("plan_file") or "").strip()
        runtime_state_file = str(hydrated.get("runtime_state_file") or "").strip()
        trace_file = str(hydrated.get("trace_file") or "").strip()

        if os.path.exists(plan_file):
            plan_data = self._safe_read_json(plan_file)
            if isinstance(plan_data, dict):
                hydrated["planner_result"] = copy.deepcopy(plan_data)
                plan_steps = plan_data.get("steps", [])
                if isinstance(plan_steps, list):
                    hydrated["steps"] = copy.deepcopy(plan_steps)
                    hydrated["steps_total"] = len(plan_steps)

        if "steps" not in hydrated or not isinstance(hydrated.get("steps"), list):
            hydrated["steps"] = []

        if hydrated.get("steps_total") in (None, ""):
            hydrated["steps_total"] = len(hydrated.get("steps", []))

        if hydrated.get("current_step_index") is None:
            hydrated["current_step_index"] = 0

        if os.path.exists(runtime_state_file):
            runtime_data = self._safe_read_json(runtime_state_file)
            if isinstance(runtime_data, dict):
                for key in (
                    "status",
                    "priority",
                    "retry_count",
                    "max_retries",
                    "retry_delay",
                    "next_retry_tick",
                    "timeout_ticks",
                    "wait_until_tick",
                    "created_tick",
                    "last_run_tick",
                    "last_failure_tick",
                    "finished_tick",
                    "depends_on",
                    "blocked_reason",
                    "failure_type",
                    "failure_message",
                    "last_error",
                    "final_answer",
                    "cancel_requested",
                    "cancel_reason",
                    "current_step_index",
                    "steps",
                    "steps_total",
                    "results",
                    "step_results",
                    "last_step_result",
                    "replan_count",
                    "replanned",
                    "replan_reason",
                    "replan_decision",
                    "replan_summary",
                    "replan_failed_step_type",
                    "replan_repairable",
                    "completion_mode",
                    "verification_required",
                    "verification_passed",
                    "max_replans",
                    "planner_result",
                    "history",
                    "execution_log",
                    "result_file",
                    "execution_log_file",
                    "snapshot_file",
                    "plan_file",
                    "log_file",
                    "runtime_state_file",
                    "trace_file",
                    "workspace_root",
                    "workspace_dir",
                    "shared_dir",
                    "task_dir",
                    "goal",
                    "title",
                ):
                    if key in runtime_data:
                        hydrated[key] = copy.deepcopy(runtime_data.get(key))

        if not isinstance(hydrated.get("results"), list):
            hydrated["results"] = []
        if not isinstance(hydrated.get("step_results"), list):
            hydrated["step_results"] = copy.deepcopy(hydrated.get("results", []))
        if hydrated.get("last_step_result") is None and hydrated.get("step_results"):
            try:
                hydrated["last_step_result"] = copy.deepcopy(hydrated["step_results"][-1])
            except Exception:
                pass

        if not isinstance(hydrated.get("history"), list):
            current_status = str(hydrated.get("status") or STATUS_CREATED)
            hydrated["history"] = [current_status]

        hydrated = self._refresh_task_public_fields(hydrated)
        return hydrated

    def _safe_read_json(self, path: str) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    # ------------------------------------------------------------
    # repo/runtime sync
    # ------------------------------------------------------------

    def _sync_runtime_back_to_repo(
        self,
        task: Dict[str, Any],
        runner_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        task_id = str(
            task.get("task_id")
            or task.get("task_name")
            or task.get("id")
            or ""
        ).strip()
        if not task_id:
            return

        repo_task = self._get_task_from_repo(task_id)
        base_task = copy.deepcopy(repo_task if isinstance(repo_task, dict) else task)
        base_task = self._hydrate_task_from_workspace(base_task)

        runtime_state = None
        if self.task_runtime is not None and hasattr(self.task_runtime, "load_runtime_state"):
            try:
                runtime_state = self.task_runtime.load_runtime_state(base_task)
            except Exception:
                runtime_state = None

        merged = copy.deepcopy(base_task)

        if isinstance(runtime_state, dict):
            for key in (
                "status",
                "priority",
                "retry_count",
                "max_retries",
                "retry_delay",
                "next_retry_tick",
                "timeout_ticks",
                "wait_until_tick",
                "created_tick",
                "last_run_tick",
                "last_failure_tick",
                "finished_tick",
                "depends_on",
                "blocked_reason",
                "failure_type",
                "failure_message",
                "last_error",
                "final_answer",
                "cancel_requested",
                "cancel_reason",
                "current_step_index",
                "steps",
                "steps_total",
                "results",
                "step_results",
                "last_step_result",
                "replan_count",
                "replanned",
                "replan_reason",
                "replan_decision",
                "replan_summary",
                "replan_failed_step_type",
                "replan_repairable",
                "completion_mode",
                "verification_required",
                "verification_passed",
                "max_replans",
                "planner_result",
                "history",
                "execution_log",
                "result_file",
                "execution_log_file",
                "plan_file",
                "log_file",
                "runtime_state_file",
                "trace_file",
                "workspace_root",
                "workspace_dir",
                "shared_dir",
                "task_dir",
                "scheduler_build",
            ):
                if key in runtime_state:
                    merged[key] = copy.deepcopy(runtime_state.get(key))

        if isinstance(runner_result, dict):
            for key in (
                "status",
                "final_answer",
                "execution_log",
                "results",
                "step_results",
                "last_step_result",
                "current_step_index",
                "steps_total",
                "last_run_tick",
                "last_failure_tick",
                "finished_tick",
                "blocked_reason",
                "replan_decision",
                "replan_summary",
                "replan_failed_step_type",
                "replan_repairable",
                "completion_mode",
                "verification_required",
                "verification_passed",
            ):
                if key in runner_result:
                    merged[key] = copy.deepcopy(runner_result.get(key))

        if isinstance(runner_result, dict):
            replan_result = runner_result.get("replan_result")
            if isinstance(replan_result, dict) and bool(replan_result.get("replanned")):
                raw_replan_result = replan_result.get("raw_replan_result", {})
                if isinstance(raw_replan_result, dict):
                    plan = raw_replan_result.get("plan", {})
                else:
                    plan = {}

                new_steps = plan.get("steps", []) if isinstance(plan, dict) else []

                if isinstance(new_steps, list) and new_steps:
                    merged["steps"] = copy.deepcopy(new_steps)
                    merged["steps_total"] = len(new_steps)
                    merged["current_step_index"] = 0
                else:
                    merged["current_step_index"] = 0

                merged["replanned"] = True
                merged["replan_count"] = int(
                    replan_result.get("replan_count", merged.get("replan_count", 0)) or 0
                )
                merged["planner_result"] = copy.deepcopy(plan) if isinstance(plan, dict) else {}
                merged["replan_reason"] = str(
                    runner_result.get("replan_reason")
                    or merged.get("last_error")
                    or merged.get("failure_message")
                    or ""
                )

                status_from_runner = str(runner_result.get("status") or "").strip().lower()
                if status_from_runner:
                    merged["status"] = status_from_runner

        if not isinstance(merged.get("results"), list):
            merged["results"] = []
        if not isinstance(merged.get("step_results"), list):
            merged["step_results"] = copy.deepcopy(merged.get("results", []))

        if merged.get("last_step_result") is None and merged.get("step_results"):
            try:
                merged["last_step_result"] = copy.deepcopy(merged["step_results"][-1])
            except Exception:
                pass

        steps = merged.get("steps", [])
        if isinstance(steps, list):
            merged["steps_total"] = int(merged.get("steps_total", len(steps)) or len(steps))
        else:
            merged["steps_total"] = int(merged.get("steps_total", 0) or 0)

        if merged.get("current_step_index") is None:
            merged["current_step_index"] = 0

        merged["task_name"] = merged.get("task_name") or task_id
        merged["task_dir"] = merged.get("task_dir") or os.path.join(self.tasks_root, task_id)
        merged["plan_file"] = merged.get("plan_file") or os.path.join(merged["task_dir"], "plan.json")
        merged["runtime_state_file"] = merged.get("runtime_state_file") or os.path.join(
            merged["task_dir"], "runtime_state.json"
        )
        merged["trace_file"] = merged.get("trace_file") or os.path.join(merged["task_dir"], "trace.json")
        merged["workspace_root"] = merged.get("workspace_root") or self.workspace_root
        merged["workspace_dir"] = merged.get("workspace_dir") or self.tasks_root
        merged["shared_dir"] = merged.get("shared_dir") or self.shared_dir

        merged["scheduler_build"] = SCHEDULER_BUILD

        inferred_replan_result = None
        if isinstance(runner_result, dict):
            maybe_replan = runner_result.get("replan_result")
            if isinstance(maybe_replan, dict):
                inferred_replan_result = maybe_replan

        merged = self._backfill_replan_decision_fields(merged, replan_result=inferred_replan_result)
        merged = self._infer_completion_fields(merged)
        merged = self._clear_stale_replan_fields(merged)
        merged = self._refresh_task_public_fields(merged)
        self._persist_task_payload(task_id=task_id, task=merged)

    def _extract_effective_status_and_answer(
        self,
        original_task: Optional[Dict[str, Any]],
        refreshed_task: Optional[Dict[str, Any]],
        runner_result: Optional[Dict[str, Any]],
    ) -> Tuple[str, Any]:
        candidates: List[Dict[str, Any]] = []

        if isinstance(runner_result, dict):
            candidates.append(runner_result)
        if isinstance(refreshed_task, dict):
            candidates.append(refreshed_task)
        if isinstance(original_task, dict):
            candidates.append(original_task)

        status = ""
        final_answer: Any = ""

        for source in candidates:
            source_status = str(source.get("status") or "").strip().lower()
            if source_status:
                status = source_status
                break

        for source in candidates:
            if "final_answer" in source:
                value = source.get("final_answer")
                if value not in (None, ""):
                    final_answer = value
                    break

        return status, final_answer

    # ------------------------------------------------------------
    # repo state sync helpers
    # ------------------------------------------------------------

    def _mark_repo_task_finished(self, task_id: str, result: Any = None) -> None:
        task = self._get_task_from_repo(task_id)
        if not isinstance(task, dict):
            return

        task["status"] = "finished"
        task["blocked_reason"] = ""
        task["last_error"] = ""
        task["failure_message"] = ""
        task["finished_tick"] = getattr(self, "current_tick", 0)
        task["scheduler_build"] = SCHEDULER_BUILD
        if result is not None:
            task["final_answer"] = result
        task["history"] = self._append_history(task.get("history"), "finished")
        self._persist_task_payload(task_id=task_id, task=task)
        self.worker_pool.release_by_task(task_id)
        self._unblock_tasks_if_dependencies_done()

    def _mark_repo_task_failed(self, task_id: str, error: str = "") -> None:
        task = self._get_task_from_repo(task_id)
        if not isinstance(task, dict):
            return

        task["status"] = "failed"
        task["last_error"] = str(error or task.get("last_error") or "task failed")
        task["failure_message"] = task["last_error"]
        task["last_failure_tick"] = getattr(self, "current_tick", 0)
        task["scheduler_build"] = SCHEDULER_BUILD
        task["history"] = self._append_history(task.get("history"), "failed")
        self._persist_task_payload(task_id=task_id, task=task)
        self.worker_pool.release_by_task(task_id)

    def _mark_repo_task_queued(self, task_id: str, error: str = "") -> None:
        task = self._get_task_from_repo(task_id)
        if not isinstance(task, dict):
            return

        current_status = str(task.get("status") or "").strip().lower()
        if current_status in TERMINAL_STATUSES:
            return

        task["status"] = "queued"
        task["blocked_reason"] = ""
        task["scheduler_build"] = SCHEDULER_BUILD
        if error:
            task["last_error"] = str(error)
        else:
            task["last_error"] = ""
            task["failure_message"] = ""
        task["history"] = self._append_history(task.get("history"), "queued")
        self._persist_task_payload(task_id=task_id, task=task)

    def _sync_blocked_state(self, task_id: str, blocked_reason: str) -> None:
        task = self._get_task_from_repo(task_id)
        if not isinstance(task, dict):
            return

        current_status = str(task.get("status") or "").strip().lower()
        if current_status in TERMINAL_STATUSES:
            return

        changed = False

        if current_status != STATUS_BLOCKED:
            task["status"] = STATUS_BLOCKED
            task["history"] = self._append_history(task.get("history"), STATUS_BLOCKED)
            changed = True

        if str(task.get("blocked_reason") or "") != str(blocked_reason or ""):
            task["blocked_reason"] = str(blocked_reason or "")
            changed = True

        task["scheduler_build"] = SCHEDULER_BUILD
        changed = True

        if changed:
            self._persist_task_payload(task_id=task_id, task=task)

        trace = self._load_trace_for_task(task)
        self._trace_status(
            trace=trace,
            task=task,
            status=STATUS_BLOCKED,
            tick=getattr(self, "current_tick", 0),
            final_answer="",
            extra={
                "action": "sync_blocked_state",
                "blocked_reason": str(blocked_reason or ""),
            },
        )
        self._save_trace_for_task(task=task, trace=trace)

        self.worker_pool.release_by_task(task_id)

    def _sync_unblocked_state(self, task_id: str) -> None:
        task = self._get_task_from_repo(task_id)
        if not isinstance(task, dict):
            return

        status = str(task.get("status") or "").strip().lower()
        if status in TERMINAL_STATUSES:
            return

        if status == STATUS_BLOCKED:
            task["status"] = "queued"
            task["history"] = self._append_history(task.get("history"), "queued")

        task["blocked_reason"] = ""
        if str(task.get("status") or "").strip().lower() in {"queued", "ready", "retry", STATUS_QUEUED}:
            task["last_error"] = ""
            task["failure_message"] = ""
        task["scheduler_build"] = SCHEDULER_BUILD
        self._persist_task_payload(task_id=task_id, task=task)

    def _persist_task_payload(self, task_id: str, task: Dict[str, Any]) -> None:
        task = self._refresh_task_public_fields(copy.deepcopy(task))

        replace_task_fn = getattr(self.task_repo, "replace_task", None)
        upsert_task_fn = getattr(self.task_repo, "upsert_task", None)

        persisted = False

        try:
            if callable(replace_task_fn):
                replace_task_fn(task_id, copy.deepcopy(task))
                persisted = True
            elif callable(upsert_task_fn):
                upsert_task_fn(copy.deepcopy(task))
                persisted = True
        except Exception:
            persisted = False

        if not persisted:
            create_task_fn = getattr(self.task_repo, "create_task", None)
            add_task_fn = getattr(self.task_repo, "add_task", None)

            try:
                if callable(create_task_fn):
                    create_task_fn(copy.deepcopy(task))
                elif callable(add_task_fn):
                    add_task_fn(copy.deepcopy(task))
            except Exception:
                pass

        self._save_task_snapshot_safe(task)

    def _save_task_snapshot_safe(self, task: Dict[str, Any]) -> None:
        task = self._backfill_replan_decision_fields(copy.deepcopy(task))
        task = self._infer_completion_fields(task)
        task = self._clear_stale_replan_fields(task)
        task = self._refresh_task_public_fields(task)
        try:
            self.task_workspace.save_task_snapshot(task)
        except Exception:
            pass

        snapshot_file = str(task.get("snapshot_file") or "").strip()
        if snapshot_file:
            try:
                os.makedirs(os.path.dirname(snapshot_file), exist_ok=True)
                with open(snapshot_file, "w", encoding="utf-8") as f:
                    json.dump(task.get("public_snapshot", {}), f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        result_file = str(task.get("result_file") or "").strip()
        if result_file:
            try:
                os.makedirs(os.path.dirname(result_file), exist_ok=True)
                public_record = self._build_public_task_record(task)
                result_payload = {
                    **public_record,
                    "results": copy.deepcopy(task.get("results", [])),
                    "step_results": copy.deepcopy(task.get("step_results", [])),
                    "last_step_result": copy.deepcopy(task.get("last_step_result")),
                    "execution_log": copy.deepcopy(task.get("execution_log", [])),
                }
                with open(result_file, "w", encoding="utf-8") as f:
                    json.dump(result_payload, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        execution_log_file = str(task.get("execution_log_file") or "").strip()
        if execution_log_file:
            try:
                os.makedirs(os.path.dirname(execution_log_file), exist_ok=True)
                with open(execution_log_file, "w", encoding="utf-8") as f:
                    json.dump(task.get("execution_log", []), f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    def _get_task_from_repo(self, task_id: str) -> Optional[Dict[str, Any]]:
        if not task_id:
            return None

        repo = self.task_repo

        for method_name in ("get_task", "get", "load_task", "find_task"):
            method = getattr(repo, method_name, None)
            if callable(method):
                try:
                    value = method(task_id)
                    if isinstance(value, dict):
                        return self._hydrate_task_from_workspace(value)
                except Exception:
                    pass

        tasks = self._list_repo_tasks()
        for task in tasks:
            if not isinstance(task, dict):
                continue
            candidate = self._extract_task_id(task)
            if candidate == task_id:
                return self._hydrate_task_from_workspace(task)

        return None

    def _list_repo_tasks(self) -> List[Dict[str, Any]]:
        repo = self.task_repo
        list_tasks_fn = getattr(repo, "list_tasks", None)
        if callable(list_tasks_fn):
            try:
                loaded = list_tasks_fn()
                if isinstance(loaded, list):
                    return [
                        self._hydrate_task_from_workspace(x)
                        for x in loaded
                        if isinstance(x, dict)
                    ]
            except Exception:
                return []
        return []

    def _append_history(self, history: Any, status: str) -> List[str]:
        if isinstance(history, list):
            new_history = [str(x) for x in history]
        else:
            new_history = []

        if not new_history or new_history[-1] != status:
            new_history.append(status)

        return new_history

    # ------------------------------------------------------------
    # Planner
    # ------------------------------------------------------------

    def _plan_goal(self, goal: str) -> Dict[str, Any]:
        clean_goal = str(goal or "").strip()

        external_plan = self._plan_goal_via_agent_planners(clean_goal)
        if isinstance(external_plan, dict):
            steps = external_plan.get("steps", [])
            if isinstance(steps, list) and steps:
                return external_plan

        command_step = self._try_plan_command(clean_goal)
        if isinstance(command_step, dict):
            return {
                "planner_mode": "deterministic_v6_task_os_fallback",
                "intent": "command",
                "final_answer": "已規劃 1 個步驟",
                "steps": [command_step],
            }

        write_step = self._try_plan_write_file(clean_goal)
        if isinstance(write_step, dict):
            return {
                "planner_mode": "deterministic_v6_task_os_fallback",
                "intent": "write_file",
                "final_answer": "已規劃 1 個步驟",
                "steps": [write_step],
            }

        read_step = self._try_plan_read_file(clean_goal)
        if isinstance(read_step, dict):
            return {
                "planner_mode": "deterministic_v6_task_os_fallback",
                "intent": "read_file",
                "final_answer": "已規劃 1 個步驟",
                "steps": [read_step],
            }

        if self._looks_like_hello_world_python(clean_goal):
            return {
                "planner_mode": "deterministic_v6_task_os_fallback",
                "intent": "hello_world_python_multi_step",
                "final_answer": "已規劃 3 個步驟",
                "steps": [
                    {
                        "type": "write_file",
                        "path": "shared/hello.py",
                        "content": "print('hello')\n",
                    },
                    {
                        "type": "run_python",
                        "path": "shared/hello.py",
                    },
                    {
                        "type": "verify",
                        "contains": "hello",
                    },
                ],
            }

        return {
            "planner_mode": "deterministic_v6_task_os_fallback",
            "intent": "unresolved",
            "final_answer": "目前 task planner 還無法把這個 goal 轉成可執行 steps。",
            "steps": [],
        }

    def _plan_goal_via_agent_planners(self, goal: str) -> Optional[Dict[str, Any]]:
        agent_loop = getattr(self, "agent_loop", None)
        if agent_loop is None:
            return None

        planners: List[Any] = []
        llm_planner = getattr(agent_loop, "llm_planner", None)
        deterministic_planner = getattr(agent_loop, "planner", None)

        if llm_planner is not None:
            planners.append(llm_planner)
        if deterministic_planner is not None:
            planners.append(deterministic_planner)

        context = {
            "user_input": goal,
            "workspace": self.workspace_dir,
        }
        route = {
            "mode": "task",
            "task": True,
        }

        for planner in planners:
            plan = self._call_planner_like(planner, context=context, user_input=goal, route=route)
            normalized = self._normalize_external_plan(plan)
            if normalized is not None:
                return normalized

        return None

    def _call_planner_like(
        self,
        planner: Any,
        context: Dict[str, Any],
        user_input: str,
        route: Dict[str, Any],
    ) -> Any:
        if planner is None:
            return None

        for method_name in ("plan", "run", "__call__"):
            method = getattr(planner, method_name, None)
            if not callable(method):
                continue

            candidate_calls = [
                {"context": context, "user_input": user_input, "route": route},
                {"context": context, "user_input": user_input},
                {"context": context},
                {"user_input": user_input, "route": route},
                {"user_input": user_input},
            ]

            for kwargs in candidate_calls:
                try:
                    return method(**kwargs)
                except TypeError:
                    continue
                except Exception:
                    return None

            try:
                return method(user_input)
            except Exception:
                return None

        return None

    def _normalize_external_plan(self, plan: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(plan, dict):
            return None

        steps = []
        if isinstance(plan.get("steps"), list):
            steps = copy.deepcopy(plan.get("steps", []))
        elif isinstance(plan.get("plan"), dict) and isinstance(plan["plan"].get("steps"), list):
            steps = copy.deepcopy(plan["plan"].get("steps", []))

        if not isinstance(steps, list) or not steps:
            return None

        normalized_steps: List[Dict[str, Any]] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            step_type = str(step.get("type") or "").strip()
            if not step_type:
                continue
            normalized_steps.append(copy.deepcopy(step))

        if not normalized_steps:
            return None

        return {
            "planner_mode": str(plan.get("planner_mode") or "external_task_planner"),
            "intent": str(plan.get("intent") or normalized_steps[0].get("type") or "task"),
            "final_answer": str(plan.get("final_answer") or f"已規劃 {len(normalized_steps)} 個步驟"),
            "steps": normalized_steps,
            "meta": copy.deepcopy(plan.get("meta", {})) if isinstance(plan.get("meta"), dict) else {},
        }

    def _parse_goal_overrides(self, goal: str) -> Dict[str, Any]:
        text = str(goal or "").strip()
        segments = [seg.strip() for seg in text.split("::") if seg.strip()]

        clean_goal = segments[0] if segments else text
        depends_on: List[str] = []
        steps: List[Dict[str, Any]] = []

        for seg in segments[1:]:
            lower = seg.lower()

            if lower.startswith("depends_on="):
                dep_text = seg.split("=", 1)[1].strip()
                raw_deps = [x.strip() for x in dep_text.split(",") if x.strip()]
                seen = set()
                for dep in raw_deps:
                    if dep not in seen:
                        seen.add(dep)
                        depends_on.append(dep)
                continue

            if lower.startswith("step="):
                step_value = seg.split("=", 1)[1].strip()
                parsed_step = self._parse_inline_step(step_value)
                if isinstance(parsed_step, dict):
                    steps.append(parsed_step)
                continue

        return {
            "clean_goal": clean_goal,
            "depends_on": depends_on,
            "steps": steps if steps else None,
        }

    def _parse_inline_step(self, text: str) -> Optional[Dict[str, Any]]:
        value = str(text or "").strip()
        if not value:
            return None

        lower = value.lower()

        if lower == "noop":
            return {"type": "noop", "message": "noop ok"}

        if lower.startswith("command:"):
            command = value.split(":", 1)[1].strip()
            if command:
                return {"type": "command", "command": command}
            return None

        if lower.startswith("run_python:"):
            path = value.split(":", 1)[1].strip()
            if path:
                return {"type": "run_python", "path": path}
            return None

        if lower.startswith("verify:"):
            payload = value.split(":", 1)[1].strip()
            if not payload:
                return None

            if payload.startswith("contains="):
                keyword = payload.split("=", 1)[1].strip()
                if keyword:
                    return {"type": "verify", "contains": keyword}
                return None

            if payload.startswith("equals="):
                expected = payload.split("=", 1)[1]
                return {"type": "verify", "equals": expected}

            if payload.startswith("path="):
                path = payload.split("=", 1)[1].strip()
                if path:
                    return {"type": "verify", "path": path}
                return None

            return {"type": "verify", "contains": payload}

        if lower.startswith("read_file:"):
            path = value.split(":", 1)[1].strip()
            if path:
                return {"type": "read_file", "path": path}
            return None

        if lower.startswith("ensure_file:"):
            path = value.split(":", 1)[1].strip()
            if path:
                return {"type": "ensure_file", "path": path}
            return None

        if lower.startswith("write_file:"):
            payload = value.split(":", 1)[1]
            if "|" in payload:
                path, content = payload.split("|", 1)
            else:
                path, content = payload, ""
            path = path.strip()
            if not path:
                return None
            return {
                "type": "write_file",
                "path": path,
                "content": content,
            }

        return None

    def _looks_like_hello_world_python(self, text: str) -> bool:
        lowered = str(text or "").lower()
        candidates = [
            "hello world python",
            "hello world 的 python",
            "寫一個 hello world python",
            "建立 hello world python",
            "做一個 hello world python",
            "python hello world",
            "建立一個 hello.py 印出 hello world",
            "hello.py 印出 hello world",
        ]
        return any(item in lowered for item in candidates)

    def _try_plan_command(self, text: str) -> Optional[Dict[str, Any]]:
        stripped = str(text or "").strip()
        lowered = stripped.lower()

        patterns = [
            r"^cmd\s*:\s*(.+)$",
            r"^run\s*:\s*(.+)$",
            r"^run\s+(.+)$",
            r"^command\s*:\s*(.+)$",
            r"^command\s+(.+)$",
            r"^execute\s+(.+)$",
            r"^shell\s+(.+)$",
            r"^bash\s+(.+)$",
            r"^執行\s+(.+)$",
        ]

        for pattern in patterns:
            m = re.match(pattern, stripped, flags=re.IGNORECASE)
            if m:
                command = m.group(1).strip()
                if command:
                    return {"type": "command", "command": command}

        if lowered.startswith("python "):
            return {"type": "command", "command": stripped}
        if lowered.startswith("py "):
            return {"type": "command", "command": stripped}
        if lowered.startswith("cmd /c "):
            return {"type": "command", "command": stripped}
        if lowered.startswith("powershell "):
            return {"type": "command", "command": stripped}

        return None

    def _try_plan_write_file(self, text: str) -> Optional[Dict[str, Any]]:
        stripped = str(text or "").strip()
        lowered = stripped.lower()

        if not any(k in stripped for k in ["寫", "建立", "新增"]) and not any(
            k in lowered for k in ["write", "create", "make"]
        ):
            return None

        path = self._extract_file_path(stripped)
        if not path:
            return None

        content, has_explicit_content = self._extract_write_content(stripped)
        if has_explicit_content:
            return {
                "type": "write_file",
                "path": path,
                "content": content,
            }

        return {
            "type": "ensure_file",
            "path": path,
        }

    def _extract_write_content(self, text: str) -> Tuple[str, bool]:
        stripped = str(text or "").strip()

        patterns = [
            r"內容是\s*(.+)$",
            r"內容為\s*(.+)$",
            r"內容:\s*(.+)$",
            r"內容：\s*(.+)$",
            r"寫入\s*(.+)$",
            r"放入\s*(.+)$",
            r"content is\s+(.+)$",
            r"content:\s*(.+)$",
            r"with content\s+(.+)$",
        ]

        for pattern in patterns:
            m = re.search(pattern, stripped, flags=re.IGNORECASE)
            if m:
                value = m.group(1).strip()
                if value:
                    return self._strip_quotes(value), True

        return "", False

    def _strip_quotes(self, text: str) -> str:
        value = str(text or "").strip()
        if len(value) >= 2:
            if (value[0] == value[-1]) and value[0] in {"'", '"', "「", "」", "“", "”"}:
                return value[1:-1]
        return value

    def _try_plan_read_file(self, text: str) -> Optional[Dict[str, Any]]:
        stripped = str(text or "").strip()

        m = re.search(r"([A-Za-z0-9_\-./\\]+\.(py|json|txt|md))", stripped, flags=re.IGNORECASE)
        if not m:
            return None

        path = m.group(1).strip()
        lowered = stripped.lower()
        if any(x in lowered for x in ["read", "讀", "看", "open", "檢查", "查看"]):
            return {"type": "read_file", "path": path}

        return None

    def _extract_file_path(self, text: str) -> Optional[str]:
        m = re.search(r"([A-Za-z0-9_\-./\\]+?\.(?:py|txt|md|json|yaml|yml|csv|log))", text, flags=re.IGNORECASE)
        return m.group(1).strip() if m else None