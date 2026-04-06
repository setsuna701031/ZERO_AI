from __future__ import annotations

import copy
import os
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from core.runtime.task_scheduler import TaskScheduler as RuntimeTaskScheduler
from core.tasks.task_repository import TaskRepository
from core.tasks.task_workspace import TaskWorkspace
from core.tasks.scheduler_core.task_dispatcher import TaskDispatcher
from core.tasks.scheduler_core.task_scheduler_queue import (
    STATUS_FAILED,
    STATUS_FINISHED,
    STATUS_QUEUED,
    ScheduledTask,
    TaskSchedulerQueue,
)
from core.tasks.scheduler_core.worker_pool import WorkerPool


SCHEDULER_BUILD = "DAG_ALIAS_FORCE_BLOCKED_V4"


class Scheduler(RuntimeTaskScheduler):
    """
    Tasks-layer Scheduler facade

    這版重點：
    1. Repository 是 source of truth
    2. depends_on 支援 task_id / task_name / title / goal 解析
    3. 建立任務後會強制校正 repo 狀態 blocked / queued
    4. tick() 會統一做 blocked -> queued 解鎖
    5. 內建最小 simple executor，可跑 noop / command / write_file / read_file
    6. 修正 _normalize_depends_on 與父類別方法簽名衝突問題
       - 父類可能會呼叫 self._normalize_depends_on(depends_on)
       - 本檔 submit_task 需要 richer 版本的 depends_on 解析
       - 現在同一個方法同時相容兩種呼叫方式
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

        self.task_workspace = TaskWorkspace(os.path.join(self.workspace_dir, "tasks"))
        self.workspace_root = os.path.abspath(self.workspace_dir)
        self.shared_dir = os.path.join(self.workspace_root, "shared")
        os.makedirs(self.shared_dir, exist_ok=True)

        self.scheduler_queue = TaskSchedulerQueue()
        self.worker_pool = WorkerPool(max_workers=max(1, int(max_worker_slots)))
        self.dispatcher = TaskDispatcher(
            queue=self.scheduler_queue,
            worker_pool=self.worker_pool,
        )

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
        if current_tick is not None:
            self.current_tick = int(current_tick)
        else:
            self.current_tick = int(getattr(self, "current_tick", 0)) + 1

        self._unblock_tasks_if_dependencies_done()
        synced = self.rebuild_ready_queue()
        dispatch_results = self.dispatcher.dispatch_until_full()
        executed_results: List[Dict[str, Any]] = []

        for dispatch_result in dispatch_results:
            if not dispatch_result.dispatched or dispatch_result.task is None:
                continue

            scheduled_task = dispatch_result.task
            task_id = str(scheduled_task.task_id)

            repo_task = self._get_task_from_repo(task_id)
            if not isinstance(repo_task, dict):
                self.dispatcher.fail_task(
                    task_id=task_id,
                    error="task missing from repository",
                    requeue_on_retry=False,
                )
                self._mark_repo_task_failed(task_id=task_id, error="task missing from repository")
                executed_results.append(
                    {
                        "ok": False,
                        "task_id": task_id,
                        "status": STATUS_FAILED,
                        "error": "task missing from repository",
                    }
                )
                continue

            try:
                runner_result = self.run_one_step(task=repo_task, current_tick=self.current_tick)
            except Exception as e:
                fail_result = self.dispatcher.fail_task(
                    task_id=task_id,
                    error=f"run_one_step exception: {e}",
                    requeue_on_retry=True,
                )

                final_status = str(fail_result.get("final_status") or STATUS_FAILED).strip().lower()
                if final_status == STATUS_QUEUED:
                    self._mark_repo_task_queued(task_id=task_id, error=f"run_one_step exception: {e}")
                else:
                    self._mark_repo_task_failed(task_id=task_id, error=f"run_one_step exception: {e}")

                executed_results.append(
                    {
                        "ok": False,
                        "task_id": task_id,
                        "status": fail_result.get("final_status", STATUS_FAILED),
                        "error": str(e),
                        "dispatcher": fail_result,
                    }
                )
                continue

            final_status = str(
                runner_result.get("status") or repo_task.get("status") or ""
            ).strip().lower()
            final_answer = runner_result.get("final_answer")

            if final_status in {"done", "finished", STATUS_FINISHED, "success", "completed"}:
                self.dispatcher.complete_task(task_id=task_id, result=final_answer)
                self._mark_repo_task_finished(task_id=task_id, result=final_answer)

            elif final_status in {"failed", STATUS_FAILED, "error"}:
                fail_result = self.dispatcher.fail_task(
                    task_id=task_id,
                    error=str(
                        runner_result.get("error")
                        or runner_result.get("final_answer")
                        or "task failed"
                    ),
                    requeue_on_retry=True,
                )
                fail_final_status = str(fail_result.get("final_status") or STATUS_FAILED).strip().lower()

                if fail_final_status == STATUS_QUEUED:
                    self._mark_repo_task_queued(
                        task_id=task_id,
                        error=str(
                            runner_result.get("error")
                            or runner_result.get("final_answer")
                            or "task failed"
                        ),
                    )
                else:
                    self._mark_repo_task_failed(
                        task_id=task_id,
                        error=str(
                            runner_result.get("error")
                            or runner_result.get("final_answer")
                            or "task failed"
                        ),
                    )

            elif final_status in {"queued", STATUS_QUEUED, "retry"}:
                self.worker_pool.release_by_task(task_id)
                self.scheduler_queue.requeue(task_id=task_id, priority=scheduled_task.priority)
                self._mark_repo_task_queued(
                    task_id=task_id,
                    error=str(runner_result.get("error") or ""),
                )

            else:
                runtime_task = self._get_task_from_repo(task_id)
                runtime_status = ""
                if isinstance(runtime_task, dict):
                    runtime_status = str(runtime_task.get("status") or "").strip().lower()

                if runtime_status in {"done", "finished", STATUS_FINISHED, "success", "completed"}:
                    self.dispatcher.complete_task(task_id=task_id, result=final_answer)
                    self._mark_repo_task_finished(task_id=task_id, result=final_answer)

                elif runtime_status in {"failed", STATUS_FAILED, "error"}:
                    fail_result = self.dispatcher.fail_task(
                        task_id=task_id,
                        error=str(runner_result.get("error") or "task failed"),
                        requeue_on_retry=True,
                    )
                    fail_final_status = str(fail_result.get("final_status") or STATUS_FAILED).strip().lower()

                    if fail_final_status == STATUS_QUEUED:
                        self._mark_repo_task_queued(
                            task_id=task_id,
                            error=str(runner_result.get("error") or "task failed"),
                        )
                    else:
                        self._mark_repo_task_failed(
                            task_id=task_id,
                            error=str(runner_result.get("error") or "task failed"),
                        )
                else:
                    self.worker_pool.release_by_task(task_id)
                    self.scheduler_queue.requeue(task_id=task_id, priority=scheduled_task.priority)
                    self._mark_repo_task_queued(
                        task_id=task_id,
                        error=str(runner_result.get("error") or ""),
                    )

            executed_results.append(
                {
                    "ok": bool(runner_result.get("ok", True)),
                    "task_id": task_id,
                    "worker_id": dispatch_result.worker_id,
                    "result": runner_result,
                }
            )

        snapshot = self.dispatcher.snapshot()
        queue_stats = snapshot.get("queue", {})
        worker_stats = snapshot.get("workers", {})

        return {
            "ok": True,
            "scheduler_build": SCHEDULER_BUILD,
            "tick": self.current_tick,
            "synced_task_ids": synced,
            "dispatched_count": len(dispatch_results),
            "executed_count": len(executed_results),
            "executed_results": executed_results,
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

    # ------------------------------------------------------------
    # runtime scheduler sync
    # ------------------------------------------------------------

    def run_one_step(
        self,
        task: Dict[str, Any],
        current_tick: Optional[int] = None,
    ) -> Dict[str, Any]:
        result = super().run_one_step(task=task, current_tick=current_tick)

        if isinstance(result, dict) and result.get("action") == "scheduler_no_runner":
            result = self._run_simple_task_tick(task=task, current_tick=current_tick)

        self._sync_runtime_back_to_repo(task=task, runner_result=result)
        return result

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

        task_id = self._extract_task_id(task)
        task_name = str(task.get("task_name") or task_id or "unknown_task")

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

        if current_step_index >= len(steps):
            task["status"] = "finished"
            task["final_answer"] = str(task.get("final_answer") or "task finished")
            task["finished_tick"] = self.current_tick
            task["last_run_tick"] = self.current_tick
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
                "current_step_index": current_step_index,
                "step_count": len(steps),
                "last_run_tick": self.current_tick,
                "finished_tick": self.current_tick,
            }

        step = steps[current_step_index]
        if not isinstance(step, dict):
            task["status"] = "failed"
            task["last_error"] = "invalid step type"
            task["failure_message"] = "invalid step type"
            task["last_failure_tick"] = self.current_tick
            task["last_run_tick"] = self.current_tick
            return {
                "ok": False,
                "action": "simple_invalid_step",
                "tick": self.current_tick,
                "task_id": task_id,
                "task_name": task_name,
                "status": "failed",
                "message": "invalid step type",
                "error": "invalid step type",
                "execution_log": execution_log,
                "results": results,
                "current_step_index": current_step_index,
                "step_count": len(steps),
                "last_run_tick": self.current_tick,
                "last_failure_tick": self.current_tick,
            }

        try:
            step_result = self._execute_simple_step(task=task, step=step)
        except Exception as e:
            execution_log.append(
                {
                    "tick": self.current_tick,
                    "step_index": current_step_index,
                    "step": copy.deepcopy(step),
                    "ok": False,
                    "error": str(e),
                }
            )
            task["execution_log"] = execution_log
            task["status"] = "failed"
            task["last_error"] = str(e)
            task["failure_message"] = str(e)
            task["last_failure_tick"] = self.current_tick
            task["last_run_tick"] = self.current_tick

            return {
                "ok": False,
                "action": "simple_step_failed",
                "tick": self.current_tick,
                "task_id": task_id,
                "task_name": task_name,
                "status": "failed",
                "message": "step execution failed",
                "error": str(e),
                "execution_log": execution_log,
                "results": results,
                "current_step_index": current_step_index,
                "step_count": len(steps),
                "last_run_tick": self.current_tick,
                "last_failure_tick": self.current_tick,
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
        results.append(copy.deepcopy(step_result))

        task["execution_log"] = execution_log
        task["results"] = results
        task["current_step_index"] = current_step_index + 1
        task["last_run_tick"] = self.current_tick

        if task["current_step_index"] >= len(steps):
            final_answer = self._build_simple_final_answer(results)
            task["status"] = "finished"
            task["final_answer"] = final_answer
            task["finished_tick"] = self.current_tick

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
                "current_step_index": task["current_step_index"],
                "step_count": len(steps),
                "last_run_tick": self.current_tick,
                "finished_tick": self.current_tick,
            }

        task["status"] = "queued"
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
            "current_step_index": task["current_step_index"],
            "step_count": len(steps),
            "last_run_tick": self.current_tick,
        }

    def _execute_simple_step(
        self,
        task: Dict[str, Any],
        step: Dict[str, Any],
    ) -> Dict[str, Any]:
        step_type = str(step.get("type") or "").strip().lower()
        task_dir = self._resolve_task_dir(task)
        shared_dir = self.shared_dir

        if step_type == "noop":
            return {
                "type": "noop",
                "message": str(step.get("message") or "noop ok"),
            }

        if step_type == "write_file":
            raw_path = str(step.get("path") or "").strip()
            if not raw_path:
                raise ValueError("write_file step missing path")

            content = step.get("content", "")
            if content is None:
                content = ""
            content = str(content)

            full_path = self._resolve_step_path(raw_path, task_dir=task_dir, shared_dir=shared_dir)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

            return {
                "type": "write_file",
                "path": raw_path,
                "full_path": full_path,
                "bytes": len(content.encode("utf-8")),
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

        if step_type == "read_file":
            raw_path = str(step.get("path") or "").strip()
            if not raw_path:
                raise ValueError("read_file step missing path")

            full_path = self._resolve_step_path(raw_path, task_dir=task_dir, shared_dir=shared_dir)
            if not os.path.exists(full_path):
                raise FileNotFoundError(f"file not found: {full_path}")

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            return {
                "type": "read_file",
                "path": raw_path,
                "full_path": full_path,
                "content": content,
            }

        raise ValueError(f"unsupported step type: {step_type}")

    def _resolve_task_dir(self, task: Dict[str, Any]) -> str:
        task_dir = str(task.get("task_dir") or "").strip()
        if task_dir:
            os.makedirs(task_dir, exist_ok=True)
            return task_dir

        fallback_dir = os.path.join(
            self.workspace_root,
            "tasks",
            str(task.get("task_name") or "unknown_task"),
        )
        os.makedirs(fallback_dir, exist_ok=True)
        return fallback_dir

    def _resolve_step_path(self, raw_path: str, task_dir: str, shared_dir: str) -> str:
        normalized = raw_path.replace("\\", "/").strip()

        if os.path.isabs(normalized):
            return os.path.abspath(normalized)

        if normalized.startswith("shared/"):
            relative_part = normalized[len("shared/"):].strip("/")
            return os.path.abspath(os.path.join(shared_dir, relative_part))

        return os.path.abspath(os.path.join(task_dir, normalized))

    def _build_simple_final_answer(self, results: List[Dict[str, Any]]) -> str:
        if not results:
            return "task finished"

        last = results[-1]
        if isinstance(last, dict) and last.get("type") == "command":
            stdout = str(last.get("stdout") or "").strip()
            if stdout:
                return stdout

        if isinstance(last, dict) and last.get("type") == "read_file":
            return str(last.get("content") or "").strip() or "task finished"

        if isinstance(last, dict) and last.get("type") == "noop":
            return str(last.get("message") or "task finished")

        return "task finished"

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
        repo_tasks: List[Dict[str, Any]] = []

        repo = self.task_repo
        list_tasks_fn = getattr(repo, "list_tasks", None)

        if callable(list_tasks_fn):
            try:
                loaded = list_tasks_fn()
                if isinstance(loaded, list):
                    repo_tasks = loaded
            except Exception:
                repo_tasks = []

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

        raw_depends_on = depends_on if depends_on is not None else kwargs.get("depends_on", None)
        if raw_depends_on is None:
            raw_depends_on = parsed.get("depends_on", [])

        resolve_result = self._normalize_depends_on(raw_depends_on=raw_depends_on, self_task_id=task_name)
        if not isinstance(resolve_result, dict) or not resolve_result.get("ok"):
            return {
                "ok": False,
                "scheduler_build": SCHEDULER_BUILD,
                "error": resolve_result.get("error", "depends_on normalization failed") if isinstance(resolve_result, dict) else "depends_on normalization failed",
                "depends_on_input": raw_depends_on,
            }

        normalized_depends_on = resolve_result["depends_on"]
        initial_status, initial_blocked_reason = self._decide_initial_status(normalized_depends_on)

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
            "blocked_reason": initial_blocked_reason,
            "failure_type": None,
            "failure_message": None,
            "last_error": None,
            "cancel_requested": False,
            "cancel_reason": "",
            "planner_result": copy.deepcopy(planner_result),
            "replan_count": 0,
            "replanned": False,
            "replan_reason": "",
            "max_replans": 1,
            "history": [initial_status],
            "workspace_root": self.workspace_root,
            "shared_dir": self.shared_dir,
            "scheduler_build": SCHEDULER_BUILD,
        }

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
            blocked_reason=initial_blocked_reason,
            depends_on=normalized_depends_on,
            full_task=task,
        )

        refreshed = self._get_task_from_repo(task_name)
        if isinstance(refreshed, dict):
            task = refreshed

        if str(task.get("status") or "").strip().lower() == "queued":
            self._enqueue_repo_task_if_ready(task, overwrite=True)

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
        return self.submit_task(
            goal=goal,
            priority=priority,
            max_retries=max_retries,
            retry_delay=retry_delay,
            timeout_ticks=timeout_ticks,
            depends_on=depends_on,
            **kwargs,
        )

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

        deps_ready, blocked_reason = self._task_dependencies_satisfied(task)
        if deps_ready:
            result = self._set_status(task_name, "queued")
            refreshed = self._get_task_from_repo(task_name)
            if isinstance(refreshed, dict):
                self._enqueue_repo_task_if_ready(refreshed, overwrite=True)
            return result

        self._sync_blocked_state(task_id=task_name, blocked_reason=blocked_reason)
        result = self._set_status(task_name, "blocked")
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
            if self._enqueue_repo_task_if_ready(task):
                task_id = self._extract_task_id(task)
                if task_id:
                    synced_ids.append(task_id)

        return synced_ids

    def _enqueue_repo_task_if_ready(self, task: Dict[str, Any], overwrite: bool = False) -> bool:
        task_id = self._extract_task_id(task)
        if not task_id:
            return False

        if self.worker_pool.get_running_task(task_id) is not None:
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
        ready_statuses = {
            "queued",
            "ready",
            "retry",
            STATUS_QUEUED,
        }

        if status not in ready_statuses:
            return False

        scheduled_task = self._repo_task_to_scheduled_task(task)
        return self.scheduler_queue.enqueue(scheduled_task, overwrite=overwrite)

    def _repo_task_to_scheduled_task(self, task: Dict[str, Any]) -> ScheduledTask:
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

        return ScheduledTask(
            task_id=task_id,
            title=str(task.get("title") or task.get("goal") or task_id),
            priority=int(task.get("priority", 0)),
            created_at=created_at,
            status=str(task.get("status") or STATUS_QUEUED),
            retry_count=int(task.get("retry_count", 0)),
            max_retries=int(task.get("max_retries", 0)),
            payload={
                "goal": task.get("goal"),
                "steps_total": task.get("steps_total"),
                "current_step_index": current_step_index,
                "depends_on": copy.deepcopy(task.get("depends_on", [])),
            },
            metadata={
                "repo_status": task.get("status"),
                "task_name": task.get("task_name"),
                "blocked_reason": task.get("blocked_reason"),
                "scheduler_build": task.get("scheduler_build", SCHEDULER_BUILD),
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

    def _decide_initial_status(self, depends_on: List[str]) -> Tuple[str, str]:
        if not depends_on:
            return "queued", ""

        for dep_id in depends_on:
            dep_task = self._get_task_from_repo(dep_id)
            if not isinstance(dep_task, dict):
                return "blocked", f"dependency not found: {dep_id}"

            dep_status = str(dep_task.get("status") or "").strip().lower()
            if dep_status not in {"finished", "done", "success", "completed"}:
                return "blocked", f"waiting dependency: {dep_id}"

        return "queued", ""

    def _task_dependencies_satisfied(self, task: Dict[str, Any]) -> Tuple[bool, str]:
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

            task_id = self._extract_task_id(task)
            if not task_id:
                continue

            status = str(task.get("status") or "").strip().lower()
            if status != "blocked":
                continue

            deps_ready, blocked_reason = self._task_dependencies_satisfied(task)

            if deps_ready:
                task["status"] = "queued"
                task["blocked_reason"] = ""
                task["history"] = self._append_history(task.get("history"), "queued")
                task["scheduler_build"] = SCHEDULER_BUILD
                self._persist_task_payload(task_id=task_id, task=task)
                self.scheduler_queue.cancel(task_id)
                self._enqueue_repo_task_if_ready(task, overwrite=True)
            else:
                self._sync_blocked_state(task_id=task_id, blocked_reason=blocked_reason)

    def _normalize_depends_on(
        self,
        raw_depends_on: Any,
        self_task_id: Optional[str] = None,
    ) -> Any:
        """
        相容兩種呼叫模式：

        1. 父類 / 舊邏輯：
           self._normalize_depends_on(depends_on)
           -> 回傳 List[str]

        2. 本檔 submit_task：
           self._normalize_depends_on(raw_depends_on, self_task_id=task_name)
           -> 回傳 {"ok": bool, "depends_on": [...]} / {"ok": False, "error": ...}
        """
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

        if desired_status == "blocked":
            self.scheduler_queue.cancel(task_id)

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
                "max_replans",
                "planner_result",
                "history",
                "execution_log",
                "result_file",
                "execution_log_file",
                "plan_file",
                "log_file",
                "runtime_state_file",
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
                "current_step_index",
                "last_run_tick",
                "last_failure_tick",
                "finished_tick",
            ):
                if key in runner_result:
                    merged[key] = copy.deepcopy(runner_result.get(key))

        merged["scheduler_build"] = SCHEDULER_BUILD
        self._persist_task_payload(task_id=task_id, task=merged)

    # ------------------------------------------------------------
    # repo state sync helpers
    # ------------------------------------------------------------

    def _mark_repo_task_finished(self, task_id: str, result: Any = None) -> None:
        task = self._get_task_from_repo(task_id)
        if not isinstance(task, dict):
            return

        task["status"] = "finished"
        task["blocked_reason"] = ""
        task["finished_tick"] = getattr(self, "current_tick", 0)
        task["scheduler_build"] = SCHEDULER_BUILD
        if result is not None:
            task["final_answer"] = result
        task["history"] = self._append_history(task.get("history"), "finished")
        self._persist_task_payload(task_id=task_id, task=task)

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

    def _mark_repo_task_queued(self, task_id: str, error: str = "") -> None:
        task = self._get_task_from_repo(task_id)
        if not isinstance(task, dict):
            return

        task["status"] = "queued"
        task["blocked_reason"] = ""
        task["scheduler_build"] = SCHEDULER_BUILD
        if error:
            task["last_error"] = str(error)
        task["history"] = self._append_history(task.get("history"), "queued")
        self._persist_task_payload(task_id=task_id, task=task)

    def _sync_blocked_state(self, task_id: str, blocked_reason: str) -> None:
        task = self._get_task_from_repo(task_id)
        if not isinstance(task, dict):
            return

        changed = False

        if str(task.get("status") or "").strip().lower() != "blocked":
            task["status"] = "blocked"
            task["history"] = self._append_history(task.get("history"), "blocked")
            changed = True

        if str(task.get("blocked_reason") or "") != str(blocked_reason or ""):
            task["blocked_reason"] = str(blocked_reason or "")
            changed = True

        task["scheduler_build"] = SCHEDULER_BUILD
        changed = True

        if changed:
            self._persist_task_payload(task_id=task_id, task=task)

    def _sync_unblocked_state(self, task_id: str) -> None:
        task = self._get_task_from_repo(task_id)
        if not isinstance(task, dict):
            return

        status = str(task.get("status") or "").strip().lower()
        if status == "blocked":
            task["status"] = "queued"
            task["history"] = self._append_history(task.get("history"), "queued")

        task["blocked_reason"] = ""
        task["scheduler_build"] = SCHEDULER_BUILD
        self._persist_task_payload(task_id=task_id, task=task)

    def _persist_task_payload(self, task_id: str, task: Dict[str, Any]) -> None:
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
        try:
            self.task_workspace.save_task_snapshot(task)
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
                        return copy.deepcopy(value)
                except Exception:
                    pass

        tasks = self._list_repo_tasks()
        for task in tasks:
            if not isinstance(task, dict):
                continue
            candidate = self._extract_task_id(task)
            if candidate == task_id:
                return copy.deepcopy(task)

        return None

    def _list_repo_tasks(self) -> List[Dict[str, Any]]:
        repo = self.task_repo
        list_tasks_fn = getattr(repo, "list_tasks", None)
        if callable(list_tasks_fn):
            try:
                loaded = list_tasks_fn()
                if isinstance(loaded, list):
                    return [copy.deepcopy(x) for x in loaded if isinstance(x, dict)]
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

        command_step = self._try_plan_command(clean_goal)
        if isinstance(command_step, dict):
            return {
                "planner_mode": "deterministic_v3_shared_workspace",
                "intent": "command",
                "final_answer": "已規劃 1 個步驟",
                "steps": [command_step],
            }

        read_step = self._try_plan_read_file(clean_goal)
        if isinstance(read_step, dict):
            return {
                "planner_mode": "deterministic_v3_shared_workspace",
                "intent": "read_file",
                "final_answer": "已規劃 1 個步驟",
                "steps": [read_step],
            }

        if self._looks_like_hello_world_python(clean_goal):
            return {
                "planner_mode": "deterministic_v3_shared_workspace",
                "intent": "write_file",
                "final_answer": "已規劃 1 個步驟",
                "steps": [
                    {
                        "type": "write_file",
                        "path": "hello.py",
                        "content": 'print("hello world")\n',
                    }
                ],
            }

        return {
            "planner_mode": "deterministic_v3_shared_workspace",
            "intent": "unresolved",
            "final_answer": "目前規則式 planner 還無法把這個 goal 轉成可執行 steps。",
            "steps": [],
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

        if lower.startswith("read_file:"):
            path = value.split(":", 1)[1].strip()
            if path:
                return {"type": "read_file", "path": path}
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
        lowered = text.lower()
        candidates = [
            "hello world python",
            "hello world 的 python",
            "寫一個 hello world python",
            "建立 hello world python",
            "做一個 hello world python",
            "python hello world",
        ]
        return any(item in lowered for item in candidates)

    def _try_plan_command(self, text: str) -> Optional[Dict[str, Any]]:
        stripped = text.strip()
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

    def _try_plan_read_file(self, text: str) -> Optional[Dict[str, Any]]:
        stripped = text.strip()

        m = re.search(r"([A-Za-z0-9_\-./\\]+\.(py|json|txt|md))", stripped, flags=re.IGNORECASE)
        if not m:
            return None

        path = m.group(1).strip()
        lowered = stripped.lower()
        if any(x in lowered for x in ["read", "讀", "看", "open", "檢查", "內容"]):
            return {"type": "read_file", "path": path}

        return None