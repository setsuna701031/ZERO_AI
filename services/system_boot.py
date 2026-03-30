from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Optional

from core.agent.agent_loop import AgentLoop
from core.tasks.scheduler import Scheduler


try:
    from core.router import Router  # type: ignore
except Exception:
    try:
        from core.routing.router import Router  # type: ignore
    except Exception:
        Router = None  # type: ignore


try:
    from core.planner import Planner  # type: ignore
except Exception:
    try:
        from core.planning.planner import Planner  # type: ignore
    except Exception:
        Planner = None  # type: ignore


try:
    from core.verifier import Verifier  # type: ignore
except Exception:
    try:
        from core.verify.verifier import Verifier  # type: ignore
    except Exception:
        Verifier = None  # type: ignore


try:
    from core.safety_guard import SafetyGuard  # type: ignore
except Exception:
    try:
        from core.safety.safety_guard import SafetyGuard  # type: ignore
    except Exception:
        SafetyGuard = None  # type: ignore


try:
    from core.tool_registry import ToolRegistry  # type: ignore
except Exception:
    try:
        from core.tools.tool_registry import ToolRegistry  # type: ignore
    except Exception:
        ToolRegistry = None  # type: ignore


try:
    from core.step_executor import StepExecutor  # type: ignore
except Exception:
    try:
        from core.execution.step_executor import StepExecutor  # type: ignore
    except Exception:
        try:
            from core.tasks.step_executor import StepExecutor  # type: ignore
        except Exception:
            StepExecutor = None  # type: ignore


class SafePlannerAdapter:
    def __init__(self, planner: Any = None, step_executor: Any = None) -> None:
        self.planner = planner
        self.step_executor = step_executor

    def plan(
        self,
        context: Optional[Dict[str, Any]] = None,
        user_input: str = "",
        route: Any = None,
    ) -> Dict[str, Any]:
        context = context or {}
        user_input = user_input or str(context.get("user_input", "")).strip()

        if self.planner is None:
            return self._fallback_plan(context=context, user_input=user_input)

        planner_fn = self._pick_callable(
            self.planner,
            [
                "plan",
                "run",
                "create_plan",
                "build_plan",
                "build",
                "make_plan",
                "generate_plan",
                "generate",
                "handle",
                "__call__",
            ],
        )

        if planner_fn is None:
            return self._fallback_plan(context=context, user_input=user_input)

        candidate_calls = [
            {"context": context, "user_input": user_input, "route": route},
            {"context": context, "user_input": user_input},
            {"context": context},
            {"user_input": user_input, "route": route},
            {"user_input": user_input},
            {"input_text": user_input},
            {"message": user_input},
            {"prompt": user_input},
            {"task": context},
            {"payload": context},
        ]

        for kwargs in candidate_calls:
            try:
                result = planner_fn(**kwargs)
                normalized = self._normalize_result(
                    result=result,
                    context=context,
                    user_input=user_input,
                )
                if self._is_usable_plan(normalized):
                    return normalized
            except TypeError:
                continue
            except Exception:
                break

        for arg in (
            context,
            user_input,
            {"context": context, "user_input": user_input, "route": route},
        ):
            try:
                result = planner_fn(arg)
                normalized = self._normalize_result(
                    result=result,
                    context=context,
                    user_input=user_input,
                )
                if self._is_usable_plan(normalized):
                    return normalized
            except TypeError:
                continue
            except Exception:
                break

        return self._fallback_plan(context=context, user_input=user_input)

    def _is_usable_plan(self, normalized: Dict[str, Any]) -> bool:
        steps = normalized.get("steps", [])
        return isinstance(steps, list) and len(steps) > 0

    def _normalize_result(
        self,
        result: Any,
        context: Dict[str, Any],
        user_input: str,
    ) -> Dict[str, Any]:
        if isinstance(result, dict):
            if any(
                k in result
                for k in (
                    "steps",
                    "plan",
                    "actions",
                    "tasks",
                    "final_answer",
                    "answer",
                    "response",
                    "message",
                    "summary",
                )
            ):
                normalized = copy.deepcopy(result)

                if "steps" not in normalized:
                    for alt_key in ("plan", "actions", "tasks"):
                        value = normalized.get(alt_key)
                        if isinstance(value, list):
                            normalized["steps"] = value
                            break

                if not isinstance(normalized.get("steps"), list):
                    normalized["steps"] = []

                normalized.setdefault("final_answer", self._summarize_user_input(user_input))
                return normalized

            return {
                "final_answer": self._summarize_user_input(user_input),
                "steps": [
                    {
                        "type": "respond",
                        "message": self._summarize_user_input(user_input),
                    }
                ],
                "raw_planner_result": result,
            }

        if isinstance(result, list):
            return {
                "steps": result,
                "final_answer": self._summarize_user_input(user_input),
            }

        if isinstance(result, str):
            text = result.strip() or self._summarize_user_input(user_input)
            return {
                "final_answer": text,
                "steps": [
                    {
                        "type": "respond",
                        "message": text,
                    }
                ],
            }

        return self._fallback_plan(context=context, user_input=user_input)

    def _fallback_plan(
        self,
        context: Dict[str, Any],
        user_input: str,
    ) -> Dict[str, Any]:
        text = (user_input or "").strip()
        answer = self._summarize_user_input(text)
        return {
            "planner_mode": "fallback",
            "intent": "respond",
            "final_answer": answer,
            "steps": [
                {
                    "type": "respond",
                    "message": answer,
                }
            ],
            "context_summary": context.get("summary", ""),
        }

    def _summarize_user_input(self, user_input: str) -> str:
        text = (user_input or "").strip()
        if not text:
            return "已收到。"
        return f"已收到：{text}"

    def _pick_callable(self, obj: Any, names: List[str]):
        for name in names:
            fn = getattr(obj, name, None)
            if callable(fn):
                return fn
        return None


class ZeroSystem:
    def __init__(self, workspace_dir: str = "workspace") -> None:
        self.workspace_dir = workspace_dir
        os.makedirs(self.workspace_dir, exist_ok=True)

        self.data_dir = os.path.join(self.workspace_dir, "data")
        os.makedirs(self.data_dir, exist_ok=True)

        self.tasks_path = os.path.join(self.data_dir, "tasks.json")
        self.scheduler_state_path = os.path.join(self.data_dir, "scheduler_state.json")
        self.runtime_events_path = os.path.join(self.data_dir, "runtime_events.jsonl")
        self.memory_store_path = os.path.join(self.data_dir, "memory_store.json")

        self.runtime_store = JsonRuntimeStore(self.runtime_events_path)
        self.memory_store = JsonMemoryStore(self.memory_store_path)

        self.tool_registry = self._build_tool_registry()
        self.step_executor = self._build_step_executor(self.tool_registry)
        self.scheduler = self._build_scheduler()
        self._ensure_scheduler_bindings()

        self.router = self._build_router()
        self.raw_planner = self._build_raw_planner()
        self.planner = SafePlannerAdapter(
            self.raw_planner,
            step_executor=getattr(self.scheduler, "step_executor", None),
        )
        self.verifier = self._build_verifier()
        self.safety_guard = self._build_safety_guard()

        self.agent_loop = AgentLoop(
            router=self.router,
            planner=self.planner,
            step_executor=getattr(self.scheduler, "step_executor", None),
            verifier=self.verifier,
            safety_guard=self.safety_guard,
            memory_store=self.memory_store,
            runtime_store=self.runtime_store,
            debug=False,
        )

        self._ensure_files()

    def _build_tool_registry(self) -> Optional[Any]:
        if ToolRegistry is None:
            return None

        candidate_kwargs = [
            {"memory_store": self.memory_store, "runtime_store": self.runtime_store, "workspace_dir": self.workspace_dir},
            {"memory_store": self.memory_store, "workspace_dir": self.workspace_dir},
            {"runtime_store": self.runtime_store, "workspace_dir": self.workspace_dir},
            {"workspace_dir": self.workspace_dir},
            {"workspace_root": self.workspace_dir},
            {"memory_store": self.memory_store},
            {"runtime_store": self.runtime_store},
            {},
        ]

        for kwargs in candidate_kwargs:
            try:
                return ToolRegistry(**kwargs)
            except TypeError:
                continue
            except Exception:
                return None

        try:
            return ToolRegistry()
        except Exception:
            return None

    def _build_step_executor(self, tool_registry: Optional[Any]) -> Optional[Any]:
        if StepExecutor is None:
            return None

        candidate_kwargs = [
            {
                "tool_registry": tool_registry,
                "memory_store": self.memory_store,
                "runtime_store": self.runtime_store,
                "workspace_dir": self.workspace_dir,
            },
            {
                "tool_registry": tool_registry,
                "runtime_store": self.runtime_store,
                "workspace_dir": self.workspace_dir,
            },
            {
                "tool_registry": tool_registry,
                "workspace_dir": self.workspace_dir,
            },
            {
                "tool_registry": tool_registry,
            },
            {
                "workspace_dir": self.workspace_dir,
            },
            {
                "workspace_root": self.workspace_dir,
            },
            {},
        ]

        for kwargs in candidate_kwargs:
            try:
                return StepExecutor(**kwargs)
            except TypeError:
                continue
            except Exception:
                return None

        try:
            return StepExecutor()
        except Exception:
            return None

    def _build_scheduler(self) -> Any:
        candidate_kwargs = [
            {
                "workspace_dir": self.workspace_dir,
                "runtime_store": self.runtime_store,
                "queue": [],
                "debug": False,
                "step_executor": self.step_executor,
                "tool_registry": self.tool_registry,
            },
            {
                "workspace_dir": self.workspace_dir,
                "runtime_store": self.runtime_store,
                "queue": [],
                "debug": False,
                "step_executor": self.step_executor,
            },
            {
                "workspace_dir": self.workspace_dir,
                "runtime_store": self.runtime_store,
                "queue": [],
                "debug": False,
                "tool_registry": self.tool_registry,
            },
            {
                "workspace_dir": self.workspace_dir,
                "runtime_store": self.runtime_store,
                "queue": [],
                "debug": False,
            },
        ]

        last_error: Optional[Exception] = None

        for kwargs in candidate_kwargs:
            try:
                return Scheduler(**kwargs)
            except TypeError:
                continue
            except Exception as exc:
                last_error = exc
                break

        if last_error is not None:
            raise last_error

        return Scheduler(
            workspace_dir=self.workspace_dir,
            runtime_store=self.runtime_store,
            queue=[],
            debug=False,
        )

    def _ensure_scheduler_bindings(self) -> None:
        scheduler_step_executor = getattr(self.scheduler, "step_executor", None)

        if scheduler_step_executor is None and self.step_executor is not None:
            try:
                setattr(self.scheduler, "step_executor", self.step_executor)
                scheduler_step_executor = self.step_executor
            except Exception:
                scheduler_step_executor = getattr(self.scheduler, "step_executor", None)

        if getattr(self.scheduler, "tool_registry", None) is None and self.tool_registry is not None:
            try:
                setattr(self.scheduler, "tool_registry", self.tool_registry)
            except Exception:
                pass

        if scheduler_step_executor is not None:
            if getattr(scheduler_step_executor, "tool_registry", None) is None and self.tool_registry is not None:
                try:
                    setattr(scheduler_step_executor, "tool_registry", self.tool_registry)
                except Exception:
                    pass

            if getattr(scheduler_step_executor, "runtime_store", None) is None:
                try:
                    setattr(scheduler_step_executor, "runtime_store", self.runtime_store)
                except Exception:
                    pass

            if getattr(scheduler_step_executor, "memory_store", None) is None:
                try:
                    setattr(scheduler_step_executor, "memory_store", self.memory_store)
                except Exception:
                    pass

            if getattr(scheduler_step_executor, "workspace_dir", None) in (None, ""):
                try:
                    setattr(scheduler_step_executor, "workspace_dir", self.workspace_dir)
                except Exception:
                    pass

    def _build_router(self) -> Optional[Any]:
        if Router is None:
            return None

        candidate_kwargs = [
            {"memory_store": self.memory_store, "runtime_store": self.runtime_store},
            {"memory_store": self.memory_store},
            {"runtime_store": self.runtime_store},
            {},
        ]

        for kwargs in candidate_kwargs:
            try:
                return Router(**kwargs)
            except TypeError:
                continue
            except Exception:
                return None

        try:
            return Router()
        except Exception:
            return None

    def _build_raw_planner(self) -> Optional[Any]:
        if Planner is None:
            return None

        step_executor = getattr(self.scheduler, "step_executor", None)

        candidate_kwargs = [
            {
                "memory_store": self.memory_store,
                "runtime_store": self.runtime_store,
                "step_executor": step_executor,
                "workspace_dir": self.workspace_dir,
            },
            {
                "memory_store": self.memory_store,
                "step_executor": step_executor,
                "workspace_dir": self.workspace_dir,
            },
            {
                "runtime_store": self.runtime_store,
                "step_executor": step_executor,
                "workspace_dir": self.workspace_dir,
            },
            {
                "step_executor": step_executor,
                "workspace_dir": self.workspace_dir,
            },
            {
                "step_executor": step_executor,
                "workspace_root": self.workspace_dir,
            },
            {
                "step_executor": step_executor,
            },
            {
                "memory_store": self.memory_store,
                "runtime_store": self.runtime_store,
                "workspace_dir": self.workspace_dir,
            },
            {
                "workspace_dir": self.workspace_dir,
            },
            {
                "workspace_root": self.workspace_dir,
            },
            {
                "memory_store": self.memory_store,
            },
            {
                "runtime_store": self.runtime_store,
            },
            {},
        ]

        for kwargs in candidate_kwargs:
            try:
                planner = Planner(**kwargs)
                return planner
            except TypeError:
                continue
            except Exception:
                return None

        try:
            return Planner()
        except Exception:
            return None

    def _build_verifier(self) -> Optional[Any]:
        if Verifier is None:
            return None

        candidate_kwargs = [
            {"memory_store": self.memory_store, "runtime_store": self.runtime_store},
            {"memory_store": self.memory_store},
            {"runtime_store": self.runtime_store},
            {},
        ]

        for kwargs in candidate_kwargs:
            try:
                return Verifier(**kwargs)
            except TypeError:
                continue
            except Exception:
                return None

        try:
            return Verifier()
        except Exception:
            return None

    def _build_safety_guard(self) -> Optional[Any]:
        if SafetyGuard is None:
            return None

        candidate_kwargs = [
            {"memory_store": self.memory_store, "runtime_store": self.runtime_store},
            {"memory_store": self.memory_store},
            {"runtime_store": self.runtime_store},
            {},
        ]

        for kwargs in candidate_kwargs:
            try:
                return SafetyGuard(**kwargs)
            except TypeError:
                continue
            except Exception:
                return None

        try:
            return SafetyGuard()
        except Exception:
            return None

    def _ensure_files(self) -> None:
        if not os.path.exists(self.tasks_path):
            self._write_json(self.tasks_path, {"tasks": []})

        if not os.path.exists(self.scheduler_state_path):
            self._write_json(
                self.scheduler_state_path,
                {
                    "tick": 0,
                    "current_task_name": None,
                    "queued_count": 0,
                    "paused_count": 0,
                    "waiting_count": 0,
                    "retrying_count": 0,
                    "blocked_count": 0,
                    "has_work": False,
                },
            )

    def _read_json(self, path: str, default: Any) -> Any:
        if not os.path.exists(path):
            return copy.deepcopy(default)

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return copy.deepcopy(default)

    def _write_json(self, path: str, data: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_tasks(self) -> List[Dict[str, Any]]:
        payload = self._read_json(self.tasks_path, {"tasks": []})
        tasks = payload.get("tasks", [])
        return tasks if isinstance(tasks, list) else []

    def _save_tasks(self, tasks: List[Dict[str, Any]]) -> None:
        self._write_json(self.tasks_path, {"tasks": tasks})

    def _load_scheduler_state(self) -> Dict[str, Any]:
        return self._read_json(
            self.scheduler_state_path,
            {
                "tick": 0,
                "current_task_name": None,
                "queued_count": 0,
                "paused_count": 0,
                "waiting_count": 0,
                "retrying_count": 0,
                "blocked_count": 0,
                "has_work": False,
            },
        )

    def _save_scheduler_state(self, state: Dict[str, Any]) -> None:
        self._write_json(self.scheduler_state_path, state)

    def _make_task_workspace(self, task_name: str) -> str:
        task_workspace = os.path.join(self.workspace_dir, "tasks", task_name)
        os.makedirs(task_workspace, exist_ok=True)
        return task_workspace

    def _plan_task(self, goal: str, task_name: str) -> Dict[str, Any]:
        goal = str(goal or "").strip()
        task_workspace = self._make_task_workspace(task_name)

        context = {
            "user_input": goal,
            "goal": goal,
            "task_name": task_name,
            "workspace": task_workspace,
        }

        planner_result: Dict[str, Any]
        try:
            planner_result = self.planner.plan(
                context=context,
                user_input=goal,
                route=None,
            )
        except Exception:
            planner_result = {
                "final_answer": f"已收到：{goal}",
                "steps": [
                    {
                        "type": "respond",
                        "message": f"已收到：{goal}",
                    }
                ],
            }

        steps = planner_result.get("steps", [])
        if not isinstance(steps, list):
            steps = []

        if not steps and self.raw_planner is not None:
            build_plan_fn = getattr(self.raw_planner, "build_plan", None)
            if callable(build_plan_fn):
                try:
                    legacy_steps = build_plan_fn(goal=goal, task_dir=task_workspace)
                    if isinstance(legacy_steps, list):
                        steps = legacy_steps
                        planner_result = {
                            "planner_mode": "legacy_build_plan",
                            "steps": legacy_steps,
                            "final_answer": planner_result.get("final_answer") or f"已收到：{goal}",
                        }
                except Exception:
                    pass

        return {
            "planner_result": planner_result,
            "steps": steps,
            "task_workspace": task_workspace,
        }

    def _normalize_submit_steps(self, steps: Any) -> List[Dict[str, Any]]:
        if not isinstance(steps, list):
            return []

        normalized_steps: List[Dict[str, Any]] = []
        for step in steps:
            if isinstance(step, dict):
                normalized_steps.append(copy.deepcopy(step))
            else:
                normalized_steps.append(
                    {
                        "type": "respond",
                        "message": str(step),
                    }
                )
        return normalized_steps

    def _task_has_executable_steps(self, task: Dict[str, Any]) -> bool:
        steps = task.get("steps")
        return isinstance(steps, list) and len(steps) > 0

    def _scheduler_result_is_success(self, scheduler_result: Dict[str, Any]) -> bool:
        if not isinstance(scheduler_result, dict):
            return False
        if not scheduler_result.get("ok"):
            return False
        execution_log = scheduler_result.get("execution_log", [])
        return not self._execution_log_has_error(execution_log)

    def _execution_log_has_error(self, execution_log: Any) -> bool:
        if not isinstance(execution_log, list):
            return False

        for item in execution_log:
            if not isinstance(item, dict):
                continue
            if item.get("ok") is False:
                return True
            result = item.get("result")
            if isinstance(result, dict):
                if result.get("success") is False:
                    return True
                if result.get("ok") is False:
                    return True
                if result.get("error"):
                    return True
        return False

    def health(self) -> Dict[str, Any]:
        tasks = self._load_tasks()
        scheduler_state = self._load_scheduler_state()

        scheduler_step_executor = getattr(self.scheduler, "step_executor", None)
        scheduler_tool_registry = getattr(self.scheduler, "tool_registry", None)
        step_executor_tool_registry = getattr(scheduler_step_executor, "tool_registry", None) if scheduler_step_executor else None

        return {
            "ok": True,
            "system": "ZERO Task OS",
            "workspace_dir": self.workspace_dir,
            "task_count": len(tasks),
            "scheduler_state": scheduler_state,
            "agent_loop": self.agent_loop is not None,
            "router": self.router is not None,
            "planner": self.planner is not None,
            "raw_planner": self.raw_planner is not None,
            "verifier": self.verifier is not None,
            "safety_guard": self.safety_guard is not None,
            "memory_store": self.memory_store is not None,
            "runtime_store": self.runtime_store is not None,
            "tool_registry": self.tool_registry is not None,
            "step_executor": scheduler_step_executor is not None,
            "scheduler_tool_registry": scheduler_tool_registry is not None,
            "step_executor_tool_registry": step_executor_tool_registry is not None,
        }

    def submit_task(
        self,
        goal: str,
        priority: int = 0,
        max_retries: int = 0,
        retry_delay: int = 0,
        timeout_ticks: int = 0,
        depends_on: Optional[List[str]] = None,
        simulate: str = "",
        required_ticks: int = 1,
        steps: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        tasks = self._load_tasks()

        task_name = self._next_task_name(tasks)
        task_workspace = self._make_task_workspace(task_name)

        provided_steps = self._normalize_submit_steps(steps)
        planner_result: Dict[str, Any] = {}

        if provided_steps:
            final_steps = provided_steps
            planner_result = {
                "planner_mode": "external_steps",
                "steps": final_steps,
                "final_answer": f"已建立任務：{goal}",
            }
        else:
            planned = self._plan_task(goal=goal, task_name=task_name)
            planner_result = planned.get("planner_result", {})
            final_steps = self._normalize_submit_steps(planned.get("steps", []))
            task_workspace = planned.get("task_workspace", task_workspace)

        task = {
            "id": task_name,
            "task_name": task_name,
            "title": goal,
            "goal": goal,
            "status": "queued",
            "priority": int(priority),
            "retry_count": 0,
            "max_retries": int(max_retries),
            "retry_delay": int(retry_delay),
            "timeout_ticks": int(timeout_ticks),
            "depends_on": depends_on or [],
            "simulate": simulate or "",
            "required_ticks": max(1, int(required_ticks or 1)),
            "progress_ticks": 0,
            "history": "queued",
            "workspace": task_workspace,
            "steps": final_steps,
            "current_step_index": 0,
            "step_results": [],
            "execution_log": [],
            "final_result": None,
            "final_answer": planner_result.get("final_answer"),
            "planner_result": planner_result,
        }

        tasks.append(task)
        self._save_tasks(tasks)
        self._refresh_scheduler_state(tasks, current_task_name=None)

        return {
            "ok": True,
            "task_name": task_name,
            "task": task,
        }

    def get_queue_rows(self) -> Dict[str, Any]:
        tasks = self._load_tasks()
        scheduler_state = self._load_scheduler_state()

        rows: List[Dict[str, Any]] = []
        for task in tasks:
            rows.append(
                {
                    "task_name": task.get("task_name", task.get("id", "")),
                    "status": task.get("status", ""),
                    "priority": task.get("priority", 0),
                    "retry_count": task.get("retry_count", 0),
                    "max_retries": task.get("max_retries", 0),
                    "timeout_ticks": task.get("timeout_ticks", 0),
                    "history": task.get("history", ""),
                    "step_count": len(task.get("steps", [])) if isinstance(task.get("steps"), list) else 0,
                    "current_step_index": task.get("current_step_index", 0),
                }
            )

        return {
            "ok": True,
            "rows": rows,
            "scheduler_state": scheduler_state,
        }

    def get_queue_snapshot(self) -> Dict[str, Any]:
        tasks = self._load_tasks()
        scheduler_state = self._load_scheduler_state()

        return {
            "ok": True,
            "tasks": tasks,
            "scheduler_state": scheduler_state,
        }

    def get_task(self, task_name: str) -> Dict[str, Any]:
        tasks = self._load_tasks()
        for task in tasks:
            if task.get("task_name") == task_name or task.get("id") == task_name:
                return {
                    "ok": True,
                    "task": task,
                }

        return {
            "ok": False,
            "error": f"找不到任務: {task_name}",
        }

    def pause_task(self, task_name: str) -> Dict[str, Any]:
        return self._update_task_status(task_name, "paused", history_label="paused")

    def resume_task(self, task_name: str) -> Dict[str, Any]:
        return self._update_task_status(task_name, "queued", history_label="resumed -> queued")

    def cancel_task(self, task_name: str) -> Dict[str, Any]:
        return self._update_task_status(task_name, "cancelled", history_label="cancelled")

    def set_task_priority(self, task_name: str, priority: int) -> Dict[str, Any]:
        tasks = self._load_tasks()
        target = None

        for task in tasks:
            if task.get("task_name") == task_name or task.get("id") == task_name:
                task["priority"] = int(priority)
                history = str(task.get("history", "")).strip()
                task["history"] = f"{history} -> priority={priority}".strip(" ->")
                target = task
                break

        if target is None:
            return {
                "ok": False,
                "error": f"找不到任務: {task_name}",
            }

        self._save_tasks(tasks)
        self._refresh_scheduler_state(tasks, current_task_name=None)

        return {
            "ok": True,
            "task": target,
        }

    def tick(self) -> Dict[str, Any]:
        tasks = self._load_tasks()

        queued_tasks = [
            t for t in tasks
            if t.get("status") in ("queued", "retrying", "waiting")
        ]
        queued_tasks.sort(
            key=lambda x: (
                -int(x.get("priority", 0)),
                str(x.get("task_name", "")),
            )
        )

        if not queued_tasks:
            self._refresh_scheduler_state(tasks, current_task_name=None)
            state = self._load_scheduler_state()
            state["tick"] = int(state.get("tick", 0)) + 1
            state["has_work"] = False
            self._save_scheduler_state(state)
            return {
                "ok": True,
                "tick": state["tick"],
                "message": "no queued task",
            }

        selected = queued_tasks[0]
        task_name = selected.get("task_name") or selected.get("id")

        target_index = None
        for idx, task in enumerate(tasks):
            if task.get("task_name") == task_name or task.get("id") == task_name:
                target_index = idx
                break

        if target_index is None:
            state = self._load_scheduler_state()
            state["tick"] = int(state.get("tick", 0)) + 1
            self._save_scheduler_state(state)
            return {
                "ok": False,
                "tick": state["tick"],
                "error": f"找不到任務實體: {task_name}",
            }

        task = tasks[target_index]
        task["status"] = "running"
        task["history"] = self._append_history(task.get("history", ""), "running")

        self._refresh_scheduler_state(tasks, current_task_name=task_name)
        state = self._load_scheduler_state()
        state["tick"] = int(state.get("tick", 0)) + 1
        self._save_scheduler_state(state)

        if self._task_has_executable_steps(task):
            scheduler_result = self.scheduler.run_task(copy.deepcopy(task))

            task["progress_ticks"] = int(task.get("progress_ticks", 0)) + 1
            task["execution_log"] = scheduler_result.get("execution_log", [])
            task["step_results"] = scheduler_result.get("execution_log", [])
            task["final_result"] = scheduler_result

            if self._scheduler_result_is_success(scheduler_result):
                task["status"] = "finished"
                task["current_step_index"] = len(task.get("steps", []))
                task["final_answer"] = (
                    scheduler_result.get("final_answer")
                    or task.get("final_answer")
                    or task.get("goal")
                )
                task["history"] = self._append_history(task.get("history", ""), "finished")
                result_payload = {
                    "ok": True,
                    "tick": state["tick"],
                    "task_name": task_name,
                    "status": "finished",
                    "message": f"{task_name} finished",
                    "final_answer": task.get("final_answer"),
                    "execution_log": task["execution_log"],
                }
            else:
                task["status"] = "failed"
                failed_step_index = 0
                execution_log = scheduler_result.get("execution_log", [])
                if isinstance(execution_log, list) and execution_log:
                    failed_step_index = len(execution_log) - 1
                task["current_step_index"] = failed_step_index
                task["final_answer"] = (
                    scheduler_result.get("final_answer")
                    or scheduler_result.get("error")
                    or task.get("final_answer")
                )
                task["history"] = self._append_history(task.get("history", ""), "failed")
                result_payload = {
                    "ok": False,
                    "tick": state["tick"],
                    "task_name": task_name,
                    "status": "failed",
                    "message": scheduler_result.get("final_answer")
                    or scheduler_result.get("error")
                    or f"{task_name} failed",
                    "final_answer": task.get("final_answer"),
                    "execution_log": task["execution_log"],
                }

            tasks[target_index] = task
            self._save_tasks(tasks)
            self._refresh_scheduler_state(tasks, current_task_name=None)
            return result_payload

        simulate = str(task.get("simulate", "")).strip().lower()
        required_ticks = max(1, int(task.get("required_ticks", 1)))
        progress_ticks = int(task.get("progress_ticks", 0)) + 1
        task["progress_ticks"] = progress_ticks

        result_payload: Dict[str, Any] = {
            "ok": True,
            "tick": state["tick"],
            "task_name": task_name,
            "status": "running",
        }

        if simulate == "block":
            task["status"] = "blocked"
            task["history"] = self._append_history(task.get("history", ""), "blocked")
            result_payload["status"] = "blocked"
            result_payload["message"] = f"{task_name} blocked"
        elif simulate == "wait":
            if progress_ticks < required_ticks:
                task["status"] = "waiting"
                task["history"] = self._append_history(task.get("history", ""), "waiting")
                result_payload["status"] = "waiting"
                result_payload["message"] = f"{task_name} waiting ({progress_ticks}/{required_ticks})"
            else:
                task["status"] = "finished"
                task["history"] = self._append_history(task.get("history", ""), "finished")
                result_payload["status"] = "finished"
                result_payload["message"] = f"{task_name} finished"
        elif simulate == "fail":
            retry_count = int(task.get("retry_count", 0))
            max_retries = int(task.get("max_retries", 0))
            if retry_count < max_retries:
                task["retry_count"] = retry_count + 1
                task["status"] = "retrying"
                task["history"] = self._append_history(task.get("history", ""), "retrying")
                result_payload["status"] = "retrying"
                result_payload["message"] = f"{task_name} retrying ({task['retry_count']}/{max_retries})"
            else:
                task["status"] = "failed"
                task["history"] = self._append_history(task.get("history", ""), "failed")
                result_payload["status"] = "failed"
                result_payload["message"] = f"{task_name} failed"
        else:
            if progress_ticks >= required_ticks:
                task["status"] = "finished"
                task["history"] = self._append_history(task.get("history", ""), "finished")
                result_payload["status"] = "finished"
                result_payload["message"] = f"{task_name} finished"
            else:
                task["status"] = "waiting"
                task["history"] = self._append_history(task.get("history", ""), "waiting")
                result_payload["status"] = "waiting"
                result_payload["message"] = f"{task_name} waiting ({progress_ticks}/{required_ticks})"

        tasks[target_index] = task
        self._save_tasks(tasks)
        self._refresh_scheduler_state(tasks, current_task_name=None)
        return result_payload

    def run(self, count: int) -> Dict[str, Any]:
        count = max(1, int(count))
        results: List[Dict[str, Any]] = []

        for _ in range(count):
            results.append(self.tick())

        return {
            "ok": True,
            "count": count,
            "results": results,
            "scheduler_state": self._load_scheduler_state(),
        }

    def get_scheduler_state(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "scheduler_state": self._load_scheduler_state(),
        }

    def reset_scheduler_state(self) -> Dict[str, Any]:
        tasks = self._load_tasks()
        self._save_scheduler_state(
            {
                "tick": 0,
                "current_task_name": None,
                "queued_count": len([t for t in tasks if t.get("status") == "queued"]),
                "paused_count": len([t for t in tasks if t.get("status") == "paused"]),
                "waiting_count": len([t for t in tasks if t.get("status") == "waiting"]),
                "retrying_count": len([t for t in tasks if t.get("status") == "retrying"]),
                "blocked_count": len([t for t in tasks if t.get("status") == "blocked"]),
                "has_work": any(t.get("status") in ("queued", "waiting", "retrying") for t in tasks),
            }
        )
        return {
            "ok": True,
            "scheduler_state": self._load_scheduler_state(),
        }

    def _next_task_name(self, tasks: List[Dict[str, Any]]) -> str:
        max_id = 0
        for task in tasks:
            name = str(task.get("task_name", ""))
            if name.startswith("task_"):
                try:
                    max_id = max(max_id, int(name.split("_", 1)[1]))
                except Exception:
                    pass
        return f"task_{max_id + 1:04d}"

    def _append_history(self, history: str, item: str) -> str:
        history = str(history or "").strip()
        item = str(item or "").strip()
        if not history:
            return item
        if not item:
            return history
        return f"{history} -> {item}"

    def _update_task_status(self, task_name: str, status: str, history_label: str) -> Dict[str, Any]:
        tasks = self._load_tasks()
        target = None

        for task in tasks:
            if task.get("task_name") == task_name or task.get("id") == task_name:
                task["status"] = status
                task["history"] = self._append_history(task.get("history", ""), history_label)
                target = task
                break

        if target is None:
            return {
                "ok": False,
                "error": f"找不到任務: {task_name}",
            }

        self._save_tasks(tasks)
        self._refresh_scheduler_state(tasks, current_task_name=None)

        return {
            "ok": True,
            "task": target,
        }

    def _refresh_scheduler_state(
        self,
        tasks: List[Dict[str, Any]],
        current_task_name: Optional[str],
    ) -> None:
        state = self._load_scheduler_state()
        state["current_task_name"] = current_task_name
        state["queued_count"] = len([t for t in tasks if t.get("status") == "queued"])
        state["paused_count"] = len([t for t in tasks if t.get("status") == "paused"])
        state["waiting_count"] = len([t for t in tasks if t.get("status") == "waiting"])
        state["retrying_count"] = len([t for t in tasks if t.get("status") == "retrying"])
        state["blocked_count"] = len([t for t in tasks if t.get("status") == "blocked"])
        state["has_work"] = any(
            t.get("status") in ("queued", "waiting", "retrying")
            for t in tasks
        )
        self._save_scheduler_state(state)


class JsonRuntimeStore:
    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def append_event(self, task_id: Optional[str] = None, event: str = "", payload: Optional[Dict[str, Any]] = None) -> None:
        record = {
            "task_id": task_id,
            "event": event,
            "payload": payload or {},
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def log_event(self, task_id: Optional[str] = None, event: str = "", payload: Optional[Dict[str, Any]] = None) -> None:
        self.append_event(task_id=task_id, event=event, payload=payload)

    def record_event(self, task_id: Optional[str] = None, event: str = "", payload: Optional[Dict[str, Any]] = None) -> None:
        self.append_event(task_id=task_id, event=event, payload=payload)

    def write_event(self, task_id: Optional[str] = None, event: str = "", payload: Optional[Dict[str, Any]] = None) -> None:
        self.append_event(task_id=task_id, event=event, payload=payload)


class JsonMemoryStore:
    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not os.path.exists(self.path):
            self._write({"items": []})

    def _read(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"items": []}

    def _write(self, data: Dict[str, Any]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        query = str(query or "").strip().lower()
        if not query:
            return self.list_recent(limit=limit)

        items = self._read().get("items", [])
        results: List[Dict[str, Any]] = []

        for item in items:
            text = str(
                item.get("text")
                or item.get("content")
                or item.get("summary")
                or ""
            ).lower()
            if query in text:
                results.append(item)

        return results[:limit]

    def list_recent(self, limit: int = 5) -> List[Dict[str, Any]]:
        items = self._read().get("items", [])
        return list(reversed(items))[:limit]

    def list(self, limit: int = 5) -> List[Dict[str, Any]]:
        return self.list_recent(limit=limit)


def boot_system(workspace_dir: str = "workspace") -> ZeroSystem:
    return ZeroSystem(workspace_dir=workspace_dir)