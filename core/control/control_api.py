# core/control/control_api.py
"""
ZERO Control API

Purpose:
- Provide a small, stable platform-facing control layer.
- Keep external callers away from app.py / scheduler internals.
- Do not hard-code domain-specific logic into AgentLoop, Scheduler, or Planner.

This file is intentionally conservative:
- It boots the existing ZERO system through services.system_boot.boot_system().
- It exposes submit(), inject_world(), get_world(), get_status(), list_tasks(), get_task().
- It avoids directly rewriting core agent/scheduler behavior.
"""

from __future__ import annotations

import copy
import traceback
from typing import Any, Dict, List, Optional

from services.system_boot import boot_system
from core.world.world_state import world_state


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _get_scheduler(system: Any) -> Any:
    scheduler = getattr(system, "scheduler", None)
    if scheduler is not None:
        return scheduler
    return system


def _get_agent_loop(system: Any) -> Any:
    for attr in ("agent_loop", "loop"):
        value = getattr(system, attr, None)
        if value is not None:
            return value

    if callable(getattr(system, "run", None)):
        return system

    return None


def _extract_task_id(task_or_result: Any) -> str:
    if not isinstance(task_or_result, dict):
        return ""

    for key in ("task_id", "task_name", "id", "name"):
        value = _safe_str(task_or_result.get(key))
        if value:
            return value

    task = task_or_result.get("task")
    if isinstance(task, dict):
        for key in ("task_id", "task_name", "id", "name"):
            value = _safe_str(task.get(key))
            if value:
                return value

    return ""


def _extract_status(task: Any) -> str:
    if not isinstance(task, dict):
        return "unknown"
    return _safe_str(task.get("status")) or "unknown"


def _extract_goal(task: Any) -> str:
    if not isinstance(task, dict):
        return ""
    for key in ("goal", "title", "prompt", "query", "input"):
        value = _safe_str(task.get(key))
        if value:
            return value
    return ""


class ZeroControlAPI:
    """
    Minimal platform-facing ZERO API.

    Example:
        from core.control.control_api import ZeroControlAPI

        zero = ZeroControlAPI()
        zero.submit("Create a task that writes hello to workspace/shared/hello.txt")
        zero.inject_world("demo_trigger", {"test": True})
        print(zero.get_status())
    """

    def __init__(self, system: Any = None, *, autostart: bool = True, debug: bool = False) -> None:
        self.debug = bool(debug)
        self.system = system
        if self.system is None and autostart:
            self.system = self.boot()

    def boot(self) -> Any:
        self.system = boot_system()
        return self.system

    def ensure_booted(self) -> Any:
        if self.system is None:
            return self.boot()
        return self.system

    def submit(self, goal: str, *, auto_submit: bool = True) -> Dict[str, Any]:
        """
        Submit a semantic goal through the existing scheduler path.

        This does NOT bypass scheduler/planner architecture.
        It tries scheduler.create_task(), then submit_existing_task() when available.
        """
        normalized_goal = _safe_str(goal)
        if not normalized_goal:
            return {
                "ok": False,
                "error": "goal is empty",
                "mode": "control_api_submit",
            }

        system = self.ensure_booted()
        scheduler = _get_scheduler(system)

        create_fn = getattr(scheduler, "create_task", None)
        if not callable(create_fn):
            return {
                "ok": False,
                "error": "scheduler.create_task is not available",
                "mode": "control_api_submit",
                "goal": normalized_goal,
            }

        try:
            create_result = create_fn(
                goal=normalized_goal,
                priority=0,
                max_retries=0,
                retry_delay=0,
                timeout_ticks=0,
            )
        except TypeError:
            try:
                create_result = create_fn(goal=normalized_goal)
            except Exception as e:
                return {
                    "ok": False,
                    "error": f"create_task failed: {e}",
                    "traceback": traceback.format_exc(),
                    "mode": "control_api_submit",
                    "goal": normalized_goal,
                }
        except Exception as e:
            return {
                "ok": False,
                "error": f"create_task failed: {e}",
                "traceback": traceback.format_exc(),
                "mode": "control_api_submit",
                "goal": normalized_goal,
            }

        if not isinstance(create_result, dict):
            create_result = {
                "ok": bool(create_result),
                "raw_result": create_result,
            }

        task_id = _extract_task_id(create_result)
        submit_result: Optional[Dict[str, Any]] = None

        if auto_submit and task_id:
            submit_fn = getattr(scheduler, "submit_existing_task", None)
            if callable(submit_fn):
                try:
                    raw_submit_result = submit_fn(task_id)
                    submit_result = raw_submit_result if isinstance(raw_submit_result, dict) else {
                        "ok": bool(raw_submit_result),
                        "task_id": task_id,
                    }
                except Exception as e:
                    submit_result = {
                        "ok": False,
                        "error": f"submit_existing_task failed: {e}",
                        "traceback": traceback.format_exc(),
                        "task_id": task_id,
                    }

        return {
            "ok": bool(create_result.get("ok", True)) and (submit_result is None or bool(submit_result.get("ok", False))),
            "mode": "control_api_submit",
            "goal": normalized_goal,
            "task_id": task_id,
            "create_result": create_result,
            "submit_result": submit_result,
        }

    def run_agent(self, user_input: str) -> Dict[str, Any]:
        """
        Run the existing AgentLoop entry when available.

        This is useful for platform callers that want the current app.py natural-language path
        without importing app.py.
        """
        text = _safe_str(user_input)
        if not text:
            return {
                "ok": False,
                "error": "user_input is empty",
                "mode": "control_api_agent_run",
            }

        system = self.ensure_booted()
        agent = _get_agent_loop(system)
        run_fn = getattr(agent, "run", None) if agent is not None else None

        if not callable(run_fn):
            return {
                "ok": False,
                "error": "AgentLoop.run is not available",
                "mode": "control_api_agent_run",
                "user_input": text,
            }

        try:
            result = run_fn(text)
            if isinstance(result, dict):
                payload = copy.deepcopy(result)
                payload.setdefault("mode", "control_api_agent_run")
                return payload
            return {
                "ok": True,
                "mode": "control_api_agent_run",
                "result": result,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"AgentLoop.run failed: {e}",
                "traceback": traceback.format_exc(),
                "mode": "control_api_agent_run",
                "user_input": text,
            }

    def inject_world(self, source: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inject external world/event data into ZERO world_state.

        This is the current platform bridge for sensors, file watchers, UI events,
        remote commands, and later camera / microphone adapters.
        """
        try:
            state = world_state.update(source, payload)
            return {
                "ok": True,
                "mode": "control_api_world_inject",
                "source": _safe_str(source),
                "state": state,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"world_state.update failed: {e}",
                "traceback": traceback.format_exc(),
                "mode": "control_api_world_inject",
                "source": _safe_str(source),
            }

    def get_world(self) -> Dict[str, Any]:
        try:
            return {
                "ok": True,
                "mode": "control_api_get_world",
                "world_state": world_state.get(reload=True),
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"world_state.get failed: {e}",
                "traceback": traceback.format_exc(),
                "mode": "control_api_get_world",
            }

    def list_tasks(self) -> Dict[str, Any]:
        system = self.ensure_booted()

        list_fn = getattr(system, "list_tasks", None)
        if callable(list_fn):
            try:
                result = list_fn()
                if isinstance(result, dict):
                    return {
                        "ok": bool(result.get("ok", True)),
                        "mode": "control_api_list_tasks",
                        "tasks": result.get("tasks", []),
                        "raw_result": result,
                    }
                if isinstance(result, list):
                    return {
                        "ok": True,
                        "mode": "control_api_list_tasks",
                        "tasks": result,
                    }
            except Exception as e:
                return {
                    "ok": False,
                    "error": f"system.list_tasks failed: {e}",
                    "traceback": traceback.format_exc(),
                    "mode": "control_api_list_tasks",
                }

        scheduler = _get_scheduler(system)
        repo = getattr(scheduler, "task_repo", None)
        repo_list_fn = getattr(repo, "list_tasks", None)

        if callable(repo_list_fn):
            try:
                tasks = repo_list_fn()
                return {
                    "ok": True,
                    "mode": "control_api_list_tasks",
                    "tasks": tasks if isinstance(tasks, list) else [],
                }
            except Exception as e:
                return {
                    "ok": False,
                    "error": f"task_repo.list_tasks failed: {e}",
                    "traceback": traceback.format_exc(),
                    "mode": "control_api_list_tasks",
                }

        return {
            "ok": False,
            "error": "task listing is not available",
            "mode": "control_api_list_tasks",
            "tasks": [],
        }

    def get_task(self, task_id: str) -> Dict[str, Any]:
        normalized_task_id = _safe_str(task_id)
        if not normalized_task_id:
            return {
                "ok": False,
                "error": "task_id is empty",
                "mode": "control_api_get_task",
            }

        system = self.ensure_booted()

        get_fn = getattr(system, "get_task", None)
        if callable(get_fn):
            try:
                result = get_fn(normalized_task_id)
                if isinstance(result, dict):
                    task = result.get("task") if isinstance(result.get("task"), dict) else result
                    return {
                        "ok": True,
                        "mode": "control_api_get_task",
                        "task_id": normalized_task_id,
                        "task": task,
                        "raw_result": result,
                    }
            except Exception:
                pass

        scheduler = _get_scheduler(system)

        helper = getattr(scheduler, "_get_task_from_repo", None)
        if callable(helper):
            try:
                task = helper(normalized_task_id)
                if isinstance(task, dict):
                    return {
                        "ok": True,
                        "mode": "control_api_get_task",
                        "task_id": normalized_task_id,
                        "task": task,
                    }
            except Exception:
                pass

        listed = self.list_tasks()
        for task in listed.get("tasks", []):
            if not isinstance(task, dict):
                continue
            if _extract_task_id(task) == normalized_task_id:
                return {
                    "ok": True,
                    "mode": "control_api_get_task",
                    "task_id": normalized_task_id,
                    "task": task,
                }

        return {
            "ok": False,
            "error": "task not found",
            "mode": "control_api_get_task",
            "task_id": normalized_task_id,
        }

    def get_status(self) -> Dict[str, Any]:
        system = self.ensure_booted()
        scheduler = _get_scheduler(system)
        agent = _get_agent_loop(system)

        tasks_payload = self.list_tasks()
        tasks = tasks_payload.get("tasks", [])
        if not isinstance(tasks, list):
            tasks = []

        status_counts: Dict[str, int] = {}
        compact_tasks: List[Dict[str, Any]] = []

        for task in tasks:
            if not isinstance(task, dict):
                continue
            status = _extract_status(task)
            status_counts[status] = status_counts.get(status, 0) + 1
            compact_tasks.append(
                {
                    "task_id": _extract_task_id(task),
                    "status": status,
                    "goal": _extract_goal(task),
                }
            )

        return {
            "ok": True,
            "mode": "control_api_status",
            "has_system": system is not None,
            "has_scheduler": scheduler is not None,
            "has_agent_loop": agent is not None,
            "task_count": len(compact_tasks),
            "status_counts": status_counts,
            "tasks": compact_tasks[-20:],
            "world_state": world_state.get(reload=True),
        }


def create_control_api(*, autostart: bool = True, debug: bool = False) -> ZeroControlAPI:
    return ZeroControlAPI(autostart=autostart, debug=debug)


# Short alias for later platform-facing usage.
Zero = ZeroControlAPI
