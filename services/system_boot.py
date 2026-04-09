from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List

from core.planning.task_replanner import TaskReplanner
from core.runtime.step_executor import StepExecutor
from core.runtime.task_runner import TaskRunner
from core.runtime.task_runtime import TaskRuntime
from core.tasks.scheduler import Scheduler
from core.tasks.task_paths import TaskPathManager
from core.tasks.task_repository import TaskRepository


class ZeroSystem:
    """
    ZERO System Boot

    角色：
    - 統一初始化 ZERO Task OS 核心元件
    - 提供 tick / run_until_idle / health
    - 對外暴露 queue / task control 的穩定入口
    """

    def __init__(self, workspace: str = "workspace") -> None:
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

        self.task_runtime = TaskRuntime(
            workspace_root=self.workspace,
            debug=False,
        )

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
            step_executor=self.step_executor,
            debug=False,
        )

        self.tick_count = 0

    # ============================================================
    # Main loop
    # ============================================================

    def tick(self) -> Dict[str, Any]:
        self.tick_count += 1
        sched_result = self.scheduler.tick(current_tick=self.tick_count)

        if not isinstance(sched_result, dict):
            return {
                "ok": False,
                "status": "failed",
                "message": "scheduler returned invalid result",
                "tick": self.tick_count,
                "raw_result": sched_result,
            }

        action = str(sched_result.get("action", "") or "").strip().lower()
        status = str(sched_result.get("status", "") or "").strip().lower()

        if action == "scheduler_idle":
            return {
                "ok": True,
                "status": "idle",
                "message": sched_result.get("message", "no task scheduled"),
                "tick": self.tick_count,
                "ready_queue": copy.deepcopy(sched_result.get("ready_queue", [])),
            }

        return {
            "ok": bool(sched_result.get("ok", False)),
            "task_name": sched_result.get("task_name"),
            "task_id": sched_result.get("task_id"),
            "status": status,
            "action": sched_result.get("action"),
            "message": sched_result.get("message", ""),
            "error": sched_result.get("error"),
            "tick": self.tick_count,
            "final_answer": sched_result.get("final_answer", ""),
            "current_step_index": sched_result.get("current_step_index"),
            "step_count": sched_result.get("step_count"),
            "raw_result": copy.deepcopy(sched_result),
        }

    def run_until_idle(self, max_ticks: int = 50) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []

        for _ in range(max_ticks):
            r = self.tick()
            results.append(copy.deepcopy(r))

            if str(r.get("status", "") or "").strip().lower() == "idle":
                break

        return results

    # ============================================================
    # System info
    # ============================================================

    def health(self) -> Dict[str, Any]:
        scheduler_status = self.scheduler.status() if hasattr(self.scheduler, "status") else {}

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
            "tick_count": self.tick_count,
            "scheduler_status": copy.deepcopy(scheduler_status),
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
        if hasattr(self.scheduler, "list_queue"):
            return {
                "ok": True,
                "queue": self.scheduler.list_queue(),
            }
        return {
            "ok": False,
            "error": "scheduler.get_queue_snapshot not available",
        }

    def create_task(self, **kwargs: Any) -> Dict[str, Any]:
        """
        純建立 task，不提交既有任務，不自動跑 scheduler。
        這裡只允許走 scheduler.create_task。
        """
        fn = getattr(self.scheduler, "create_task", None)
        if not callable(fn):
            return {
                "ok": False,
                "error": "scheduler.create_task not available",
            }

        try:
            result = fn(**kwargs)
            if not isinstance(result, dict):
                return {
                    "ok": False,
                    "error": "scheduler.create_task returned invalid result",
                    "raw_result": result,
                }
            return result
        except Exception as e:
            return {
                "ok": False,
                "error": f"create_task exception: {e}",
            }

    def submit_task(self, task_id: str) -> Any:
        """
        對外 submit API：提交既有 task_id。
        不建立新 task，不接受 goal。
        """
        fn = getattr(self.scheduler, "submit_existing_task", None)
        if callable(fn):
            try:
                return fn(task_id)
            except Exception as e:
                return {
                    "ok": False,
                    "error": f"submit_task exception: {e}",
                    "task_id": task_id,
                }

        return {
            "ok": False,
            "error": "scheduler.submit_existing_task not available",
            "task_id": task_id,
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

    def list_tasks(self) -> Dict[str, Any]:
        tasks = self.task_repository.list_tasks()
        if not isinstance(tasks, list):
            tasks = []
        return {
            "ok": True,
            "tasks": copy.deepcopy(tasks),
            "count": len(tasks),
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

    # ============================================================
    # low level helpers
    # ============================================================

    def scheduler_boot(self) -> Dict[str, Any]:
        if hasattr(self.scheduler, "boot"):
            return self.scheduler.boot()
        return {
            "ok": False,
            "error": "scheduler.boot not available",
        }

    def scheduler_status(self) -> Dict[str, Any]:
        if hasattr(self.scheduler, "status"):
            return self.scheduler.status()
        return {
            "ok": False,
            "error": "scheduler.status not available",
        }


def boot_system(workspace_dir: str = "workspace") -> ZeroSystem:
    return ZeroSystem(workspace=workspace_dir)