from __future__ import annotations

import copy
import os
import re
import time
from typing import Any, Dict, List, Optional

from core.runtime.task_scheduler import TaskScheduler as RuntimeTaskScheduler
from core.tasks.task_workspace import TaskWorkspace


class Scheduler(RuntimeTaskScheduler):
    """
    Tasks-layer Scheduler facade

    目的：
    1. 相容 services/system_boot.py 目前的 import：
       from core.tasks.scheduler import Scheduler
    2. 補齊 app.py / system_boot.py 目前會用到的介面
    3. 建立任務時先做 deterministic planning，避免 steps 為空直接 finished
    4. 真正 runtime tick 邏輯仍交給 core.runtime.task_scheduler.TaskScheduler
    5. 每次 runner 跑完後，把 runtime state 同步回 tasks.json / task.json
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
        super().__init__(
            task_repo=task_repo,
            task_manager=task_manager,
            workspace_dir=workspace_dir,
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

        self.task_repo = task_repo
        self.task_manager = task_manager
        self.workspace_dir = workspace_dir or "workspace"
        self.task_runtime = task_runtime
        self.task_runner = task_runner
        self.task_workspace = TaskWorkspace(os.path.join(self.workspace_dir, "tasks"))

    # ------------------------------------------------------------
    # 舊介面相容
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
        rebuild_ready_queue_fn = getattr(self, "rebuild_ready_queue", None)
        if callable(rebuild_ready_queue_fn):
            return rebuild_ready_queue_fn()
        return []

    # ------------------------------------------------------------
    # 關鍵：覆蓋 runtime scheduler 的 run_one_step
    # 在 runner 跑完後，把 runtime state 回寫到 repo / snapshot
    # ------------------------------------------------------------

    def run_one_step(
        self,
        task: Dict[str, Any],
        current_tick: Optional[int] = None,
    ) -> Dict[str, Any]:
        result = super().run_one_step(task=task, current_tick=current_tick)
        self._sync_runtime_back_to_repo(task=task, runner_result=result)
        return result

    # ------------------------------------------------------------
    # 查詢 API
    # ------------------------------------------------------------

    def get_queue_rows(self) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = []

        repo = self.task_repo
        list_tasks_fn = getattr(repo, "list_tasks", None)

        if callable(list_tasks_fn):
            try:
                tasks = list_tasks_fn()
            except Exception as e:
                return {
                    "ok": False,
                    "error": f"task_repo.list_tasks failed: {e}",
                }

            if isinstance(tasks, list):
                for task in tasks:
                    if not isinstance(task, dict):
                        continue
                    rows.append(
                        {
                            "task_id": task.get("task_id") or task.get("task_name") or task.get("id"),
                            "status": task.get("status"),
                            "priority": task.get("priority"),
                            "current_step_index": task.get("current_step_index"),
                        }
                    )

        return {
            "ok": True,
            "tick": getattr(self, "current_tick", 0),
            "count": len(rows),
            "rows": rows,
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

        ready_queue = []
        list_queue_fn = getattr(self, "list_queue", None)
        if callable(list_queue_fn):
            try:
                loaded_queue = list_queue_fn()
                if isinstance(loaded_queue, list):
                    ready_queue = loaded_queue
            except Exception:
                ready_queue = []

        return {
            "ok": True,
            "tick": getattr(self, "current_tick", 0),
            "ready_queue": ready_queue,
            "ready_queue_size": len(ready_queue),
            "workspace_dir": self.workspace_dir,
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
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if not isinstance(goal, str) or not goal.strip():
            return {
                "ok": False,
                "error": "goal is empty",
            }

        repo = self.task_repo
        create_task_fn = getattr(repo, "create_task", None)
        add_task_fn = getattr(repo, "add_task", None)

        planner_result = self._plan_goal(goal.strip())
        steps = planner_result.get("steps", [])
        if not isinstance(steps, list):
            steps = []

        task_name = f"task_{int(time.time() * 1000)}"
        task = {
            "task_id": task_name,
            "task_name": task_name,
            "title": goal.strip(),
            "goal": goal.strip(),
            "status": "queued",
            "priority": int(priority),
            "current_step_index": 0,
            "steps": steps,
            "steps_total": len(steps),
            "results": [],
            "execution_log": [],
            "final_answer": "",
            "retry_count": 0,
            "max_retries": int(max_retries),
            "retry_delay": int(retry_delay),
            "timeout_ticks": int(timeout_ticks),
            "created_at": int(time.time()),
            "created_tick": getattr(self, "current_tick", 0),
            "last_run_tick": None,
            "last_failure_tick": None,
            "finished_tick": None,
            "depends_on": [],
            "blocked_reason": "",
            "failure_type": None,
            "failure_message": None,
            "last_error": None,
            "cancel_requested": False,
            "cancel_reason": "",
            "planner_result": planner_result,
            "replan_count": 0,
            "replanned": False,
            "replan_reason": "",
            "max_replans": 1,
            "history": ["queued"],
        }

        try:
            task = self.task_workspace.create_workspace(task)
            self.task_workspace.save_plan(task, planner_result)
            self.task_workspace.save_task_snapshot(task)
        except Exception as e:
            return {
                "ok": False,
                "error": f"task workspace init failed: {e}",
            }

        created = False

        if callable(create_task_fn):
            created = bool(create_task_fn(task))
        elif callable(add_task_fn):
            created = bool(add_task_fn(task))
        else:
            return {
                "ok": False,
                "error": "task repository has no create_task/add_task",
            }

        if not created:
            return {
                "ok": False,
                "error": "failed to create task",
                "task": task,
            }

        return {
            "ok": True,
            "message": "task created",
            "task_name": task_name,
            "task": task,
            "planner_result": planner_result,
        }

    def pause_task(self, task_name: str) -> Dict[str, Any]:
        return self._set_status(task_name, "paused")

    def resume_task(self, task_name: str) -> Dict[str, Any]:
        return self._set_status(task_name, "queued")

    def cancel_task(self, task_name: str) -> Dict[str, Any]:
        return self._set_status(task_name, "cancelled")

    def set_task_priority(self, task_name: str, priority: int) -> Dict[str, Any]:
        repo = self.task_repo
        update_task_field_fn = getattr(repo, "update_task_field", None)

        if not callable(update_task_field_fn):
            return {
                "ok": False,
                "error": "task_repo.update_task_field not available",
                "task_name": task_name,
                "priority": priority,
            }

        ok = bool(update_task_field_fn(task_name, "priority", int(priority)))
        if not ok:
            return {
                "ok": False,
                "error": "task not found or priority update failed",
                "task_name": task_name,
                "priority": priority,
            }

        task = self._get_task_from_repo(task_name)
        if isinstance(task, dict):
            task["priority"] = int(priority)
            self._save_task_snapshot_safe(task)

        return {
            "ok": True,
            "task_name": task_name,
            "priority": int(priority),
            "message": "priority updated",
        }

    def _set_status(self, task_name: str, status: str) -> Dict[str, Any]:
        repo = self.task_repo
        set_task_status_fn = getattr(repo, "set_task_status", None)

        if not callable(set_task_status_fn):
            return {
                "ok": False,
                "error": "task_repo.set_task_status not available",
                "task_name": task_name,
                "status": status,
            }

        ok = bool(set_task_status_fn(task_name, status))
        if not ok:
            return {
                "ok": False,
                "error": "task not found or status update failed",
                "task_name": task_name,
                "status": status,
            }

        task = self._get_task_from_repo(task_name)
        if isinstance(task, dict):
            task["status"] = status
            history = task.get("history", [])
            if isinstance(history, list):
                history.append(status)
            else:
                history = [status]
            task["history"] = history
            self._save_task_snapshot_safe(task)

        return {
            "ok": True,
            "task_name": task_name,
            "status": status,
            "message": "task status updated",
        }

    # ------------------------------------------------------------
    # Planner
    # ------------------------------------------------------------

    def _plan_goal(self, goal: str) -> Dict[str, Any]:
        text = goal.strip()
        lowered = text.lower()

        if lowered.startswith("cmd:"):
            command = text[4:].strip()
            return self._build_plan(
                intent="command",
                steps=[
                    {
                        "type": "command",
                        "command": command,
                    }
                ],
            )

        if self._looks_like_hello_world_python(text):
            return self._build_plan(
                intent="python_hello_world",
                steps=[
                    {
                        "type": "write_file",
                        "path": "hello.py",
                        "content": 'print("hello world")\n',
                    },
                    {
                        "type": "command",
                        "command": "python hello.py",
                    },
                ],
            )

        write_file_step = self._try_plan_write_file(text)
        if write_file_step is not None:
            return self._build_plan(
                intent="write_file",
                steps=[write_file_step],
            )

        read_file_step = self._try_plan_read_file(text)
        if read_file_step is not None:
            return self._build_plan(
                intent="read_file",
                steps=[read_file_step],
            )

        command_step = self._try_plan_command(text)
        if command_step is not None:
            return self._build_plan(
                intent="command",
                steps=[command_step],
            )

        return {
            "planner_mode": "deterministic_v1",
            "intent": "unresolved",
            "final_answer": "目前規則式 planner 還無法把這個 goal 轉成可執行 steps。",
            "steps": [],
        }

    def _build_plan(self, intent: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "planner_mode": "deterministic_v1",
            "intent": intent,
            "final_answer": f"已規劃 {len(steps)} 個步驟",
            "steps": steps,
        }

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
        lowered = text.lower().strip()

        command_prefixes = [
            "run ",
            "execute ",
            "cmd ",
            "cmd /c ",
            "powershell ",
            "執行 ",
            "跑 ",
            "命令 ",
            "指令 ",
        ]

        for prefix in command_prefixes:
            if lowered.startswith(prefix):
                command = text[len(prefix):].strip()
                if command:
                    return {
                        "type": "command",
                        "command": command,
                    }

        return None

    def _try_plan_read_file(self, text: str) -> Optional[Dict[str, Any]]:
        lowered = text.lower()

        path_match = re.search(r"([A-Za-z0-9_\-./\\]+\.(py|txt|md|json|yaml|yml|csv))", text)
        if not path_match:
            return None

        if any(keyword in lowered for keyword in ["讀取", "讀檔", "read ", "open ", "查看", "看一下", "show "]):
            return {
                "type": "read_file",
                "path": path_match.group(1),
            }

        return None

    def _try_plan_write_file(self, text: str) -> Optional[Dict[str, Any]]:
        path_match = re.search(r"([A-Za-z0-9_\-./\\]+\.(py|txt|md|json|yaml|yml|csv))", text)
        if not path_match:
            return None

        path = path_match.group(1)

        content_match = re.search(r"(?:內容是|內容為|內容:|內容：)(.+)$", text)
        if content_match:
            content = content_match.group(1).strip()
            return {
                "type": "write_file",
                "path": path,
                "content": self._normalize_inline_content(content),
            }

        content_match = re.search(r"(?:content is|content:)(.+)$", text, flags=re.IGNORECASE)
        if content_match:
            content = content_match.group(1).strip()
            return {
                "type": "write_file",
                "path": path,
                "content": self._normalize_inline_content(content),
            }

        lowered = text.lower()
        if any(keyword in lowered for keyword in ["建立", "新增", "create", "write"]):
            default_content = self._default_file_content(path, text)
            return {
                "type": "write_file",
                "path": path,
                "content": default_content,
            }

        return None

    def _default_file_content(self, path: str, goal: str) -> str:
        lowered_path = path.lower()

        if lowered_path.endswith(".py"):
            if "hello" in goal.lower():
                return 'print("hello world")\n'
            return "# generated by ZERO\n"

        if lowered_path.endswith(".md"):
            return "# generated by ZERO\n"

        if lowered_path.endswith(".json"):
            return "{}\n"

        return ""

    def _normalize_inline_content(self, content: str) -> str:
        content = content.strip()

        if (
            (content.startswith('"') and content.endswith('"'))
            or (content.startswith("'") and content.endswith("'"))
        ):
            content = content[1:-1]

        content = content.replace("\\n", "\n")
        if not content.endswith("\n"):
            content += "\n"
        return content

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
            ):
                if key in runtime_state:
                    merged[key] = copy.deepcopy(runtime_state.get(key))

        if isinstance(runner_result, dict):
            if "status" in runner_result and runner_result.get("status") is not None:
                merged["status"] = runner_result.get("status")
            if "final_answer" in runner_result and runner_result.get("final_answer"):
                merged["final_answer"] = runner_result.get("final_answer")

        replace_task_fn = getattr(self.task_repo, "replace_task", None)
        upsert_task_fn = getattr(self.task_repo, "upsert_task", None)

        try:
            if callable(replace_task_fn):
                replace_task_fn(task_id, merged)
            elif callable(upsert_task_fn):
                upsert_task_fn(merged)
        except Exception:
            pass

        self._save_task_snapshot_safe(merged)

    # ------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------

    def _get_task_from_repo(self, task_name: str) -> Optional[Dict[str, Any]]:
        repo = self.task_repo
        get_task_fn = getattr(repo, "get_task", None)
        if callable(get_task_fn):
            try:
                task = get_task_fn(task_name)
                if isinstance(task, dict):
                    return task
            except Exception:
                return None
        return None

    def _save_task_snapshot_safe(self, task: Dict[str, Any]) -> None:
        try:
            self.task_workspace.save_task_snapshot(task)
        except Exception:
            pass