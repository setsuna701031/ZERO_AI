from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List

from core.tasks.task_paths import TaskPathManager
from core.tasks.task_repository import TaskRepository
from core.runtime.task_runtime import TaskRuntime
from core.runtime.task_runner import TaskRunner
from core.runtime.step_executor import StepExecutor
from core.tasks.scheduler import Scheduler
from core.planning.task_replanner import TaskReplanner


class ZeroSystem:
    def __init__(self, workspace: str = "workspace"):
        self.workspace = os.path.abspath(workspace)

        # ---------------------------------------------------------
        # Path manager
        # ---------------------------------------------------------
        self.path_manager = TaskPathManager(workspace_root=self.workspace)
        self.path_manager.ensure_workspace()

        workspace_paths = self.path_manager.get_workspace_paths()

        self.tasks_db_path = workspace_paths["tasks_index_file"]
        self.runtime_dir = workspace_paths["runtime_root"]
        self.logs_dir = workspace_paths["logs_root"]
        self.tasks_dir = workspace_paths["tasks_root"]
        self.scheduler_state_file = workspace_paths["scheduler_state_file"]
        self.memory_root = workspace_paths["memory_root"]
        self.knowledge_root = workspace_paths["knowledge_root"]
        self.cache_root = workspace_paths["cache_root"]

        # ---------------------------------------------------------
        # Ensure tasks.json exists
        # ---------------------------------------------------------
        if not os.path.exists(self.tasks_db_path):
            with open(self.tasks_db_path, "w", encoding="utf-8") as f:
                json.dump({"tasks": []}, f, ensure_ascii=False, indent=2)

        # ---------------------------------------------------------
        # Core components
        # ---------------------------------------------------------
        self.task_repository = TaskRepository(self.tasks_db_path)
        self.task_runtime = TaskRuntime(self.workspace)

        self.step_executor = StepExecutor(
            workspace_root=self.workspace,
            debug=False,
        )

        self.replanner = TaskReplanner(
            workspace_dir=self.workspace,
        )

        self.task_runner = TaskRunner(
            step_executor=self.step_executor,
            replanner=self.replanner,
            task_runtime=self.task_runtime,
            debug=False,
        )

        self.scheduler = Scheduler(
            task_repo=self.task_repository,
            workspace_dir=self.workspace,
            task_runtime=self.task_runtime,
            task_runner=self.task_runner,
        )

        self.tick_count = 0

    # ============================================================
    # Main loop
    # ============================================================

    def tick(self) -> Dict[str, Any]:
        self.tick_count += 1

        sched_result = self.scheduler.tick()

        if not sched_result:
            return {
                "ok": True,
                "status": "idle",
                "message": "no task scheduled",
            }

        task_name = sched_result.get("task_name")
        status = sched_result.get("status")
        message = sched_result.get("message")
        step_result = sched_result.get("step_result")

        if step_result and task_name:
            runtime = self.task_runtime.load_runtime(task_name)
            if runtime:
                compact_step_result = {
                    "step": step_result.get("step"),
                    "command": step_result.get("command"),
                    "result": step_result.get("result"),
                    "returncode": step_result.get("returncode"),
                    "status": step_result.get("status"),
                    "ok": step_result.get("ok"),
                    "error": step_result.get("error"),
                }

                runtime["last_step_result"] = copy.deepcopy(compact_step_result)

                if status == "finished":
                    result_obj = compact_step_result.get("result")
                    if isinstance(result_obj, dict) and "stdout" in result_obj:
                        runtime["final_answer"] = str(result_obj["stdout"]).strip()

                self.task_runtime.save_runtime(task_name, runtime)

        return {
            "ok": True,
            "task_name": task_name,
            "status": status,
            "message": message,
        }

    def run_until_idle(self, max_ticks: int = 50) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []

        for _ in range(max_ticks):
            r = self.tick()
            results.append(r)

            if r.get("status") == "idle":
                break

        return results

    # ============================================================
    # System info
    # ============================================================

    def health(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "system": "ZERO",
            "workspace": self.workspace,
            "tasks_db_path": self.tasks_db_path,
            "tasks_dir": self.tasks_dir,
            "runtime_dir": self.runtime_dir,
            "logs_dir": self.logs_dir,
            "scheduler_state_file": self.scheduler_state_file,
            "memory_root": self.memory_root,
            "knowledge_root": self.knowledge_root,
            "cache_root": self.cache_root,
            "step_executor_type": type(self.step_executor).__name__,
            "replanner_type": type(self.replanner).__name__,
            "task_runner_type": type(self.task_runner).__name__,
            "scheduler_type": type(self.scheduler).__name__,
            "task_repository_type": type(self.task_repository).__name__,
            "task_runtime_type": type(self.task_runtime).__name__,
        }

    # ============================================================
    # Queue / task queries
    # ============================================================

    def get_queue_rows(self) -> Any:
        fn = getattr(self.scheduler, "get_queue_rows", None)
        if callable(fn):
            return fn()
        return {
            "ok": False,
            "error": "scheduler.get_queue_rows not available",
        }

    def get_queue_snapshot(self) -> Any:
        fn = getattr(self.scheduler, "get_queue_snapshot", None)
        if callable(fn):
            return fn()
        return {
            "ok": False,
            "error": "scheduler.get_queue_snapshot not available",
        }

    def submit_task(self, **kwargs) -> Any:
        fn = getattr(self.scheduler, "submit_task", None)
        if callable(fn):
            return fn(**kwargs)
        return {
            "ok": False,
            "error": "scheduler.submit_task not available",
        }

    def get_task(self, task_name: str) -> Dict[str, Any]:
        task = self.task_repository.get_task(task_name)
        if task is None:
            return {
                "ok": False,
                "error": "task not found",
                "task_name": task_name,
            }
        return {
            "ok": True,
            "task": copy.deepcopy(task),
        }

    # ============================================================
    # Task control
    # ============================================================

    def pause_task(self, task_name: str) -> Any:
        fn = getattr(self.scheduler, "pause_task", None)
        if callable(fn):
            return fn(task_name)
        return {
            "ok": False,
            "error": "scheduler.pause_task not available",
            "task_name": task_name,
        }

    def resume_task(self, task_name: str) -> Any:
        fn = getattr(self.scheduler, "resume_task", None)
        if callable(fn):
            return fn(task_name)
        return {
            "ok": False,
            "error": "scheduler.resume_task not available",
            "task_name": task_name,
        }

    def cancel_task(self, task_name: str) -> Any:
        fn = getattr(self.scheduler, "cancel_task", None)
        if callable(fn):
            return fn(task_name)
        return {
            "ok": False,
            "error": "scheduler.cancel_task not available",
            "task_name": task_name,
        }

    def set_task_priority(self, task_name: str, priority: int) -> Any:
        fn = getattr(self.scheduler, "set_task_priority", None)
        if callable(fn):
            return fn(task_name, priority)
        return {
            "ok": False,
            "error": "scheduler.set_task_priority not available",
            "task_name": task_name,
            "priority": priority,
        }


def boot_system(workspace_dir: str = "workspace") -> ZeroSystem:
    return ZeroSystem(workspace=workspace_dir)