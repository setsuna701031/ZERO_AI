from __future__ import annotations

import importlib
import inspect
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CURRENT_FILE = Path(__file__).resolve()
SERVICES_DIR = CURRENT_FILE.parent
PROJECT_ROOT = SERVICES_DIR.parent
CORE_DIR = PROJECT_ROOT / "core"
TOOLS_DIR = PROJECT_ROOT / "tools"
CORE_TASKS_DIR = CORE_DIR / "tasks"

for path in [
    PROJECT_ROOT,
    CORE_DIR,
    TOOLS_DIR,
    SERVICES_DIR,
    CORE_TASKS_DIR,
]:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from core.task_manager import TaskManager
from core.task_runtime import TaskRuntime
from core.tasks.scheduler import TaskScheduler
from tools.command_tool import CommandTool
from tools.workspace_tool import WorkspaceTool


class SimpleToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, Any] = {}

    @property
    def tools(self) -> Dict[str, Any]:
        return self._tools

    def register(self, tool: Any) -> Dict[str, Any]:
        if tool is None:
            return {
                "ok": False,
                "error": "tool_is_none",
                "summary": "Cannot register tool: tool is None.",
            }

        tool_name = getattr(tool, "name", None)
        if not isinstance(tool_name, str) or tool_name.strip() == "":
            return {
                "ok": False,
                "error": "invalid_tool_name",
                "summary": "Cannot register tool: missing valid tool.name.",
            }

        self._tools[tool_name.strip()] = tool
        return {
            "ok": True,
            "tool_name": tool_name.strip(),
            "summary": f"Tool registered: {tool_name.strip()}",
        }

    def register_tool(self, tool: Any) -> None:
        tool_name = getattr(tool, "name", tool.__class__.__name__.lower())
        self._tools[tool_name] = tool

    def get_tool(self, name: str) -> Optional[Any]:
        return self._tools.get(str(name or "").strip())

    def has_tool(self, name: str) -> bool:
        return str(name or "").strip() in self._tools

    def list_tools(self) -> Dict[str, Any]:
        names = sorted(self._tools.keys())
        return {
            "ok": True,
            "count": len(names),
            "tools": names,
            "summary": f"Registered {len(names)} tool(s).",
        }

    def list_tool_names(self) -> List[str]:
        return sorted(self._tools.keys())


class SimpleRouter:
    def route(self, user_input: str) -> Dict[str, Any]:
        text = user_input.strip()

        if text.startswith("cmd:"):
            return {
                "mode": "tool",
                "tool_name": "command_tool",
                "tool_args": {
                    "command": text[4:].strip(),
                },
            }

        if text.startswith("ws:"):
            payload = text[3:].strip()
            return {
                "mode": "tool",
                "tool_name": "workspace_tool",
                "tool_args": {
                    "action": "read_file",
                    "path": payload,
                },
            }

        return {
            "mode": "task",
            "tool_name": None,
            "tool_args": {},
        }


class SimpleAgentLoop:
    def __init__(
        self,
        router: Any = None,
        llm_client: Any = None,
        tool_registry: Any = None,
        task_manager: Any = None,
        task_runtime: Any = None,
        scheduler: Any = None,
        **kwargs: Any,
    ) -> None:
        self.router = router or SimpleRouter()
        self.llm_client = llm_client
        self.tool_registry = tool_registry or SimpleToolRegistry()
        self.task_manager = task_manager
        self.task_runtime = task_runtime
        self.scheduler = scheduler
        self.extra_config = kwargs

    def run(self, user_input: str) -> Dict[str, Any]:
        if not isinstance(user_input, str) or not user_input.strip():
            return {
                "success": False,
                "mode": "system",
                "summary": "Empty user input.",
                "data": {},
                "error": "user_input cannot be empty.",
            }

        route_result = self._safe_route(user_input)

        if route_result.get("mode") == "tool":
            tool_name = route_result.get("tool_name")
            tool_args = route_result.get("tool_args", {})
            tool = self._get_tool(tool_name)

            if tool is None:
                return {
                    "success": False,
                    "mode": "tool",
                    "summary": f"Tool not found: {tool_name}",
                    "data": {},
                    "error": f"Tool '{tool_name}' is not registered.",
                }

            try:
                tool_result = self._run_tool(tool, tool_args)
                return {
                    "success": True,
                    "mode": "tool",
                    "summary": f"Executed tool: {tool_name}",
                    "data": {
                        "tool_name": tool_name,
                        "tool_result": tool_result,
                    },
                    "error": None,
                }
            except Exception as exc:
                return {
                    "success": False,
                    "mode": "tool",
                    "summary": f"Tool execution failed: {tool_name}",
                    "data": {
                        "tool_name": tool_name,
                    },
                    "error": str(exc),
                }

        if self.scheduler is None:
            return {
                "success": False,
                "mode": "scheduler",
                "summary": "Task scheduler is not available.",
                "data": {},
                "error": "scheduler is not configured.",
            }

        try:
            submit_result = self.scheduler.submit_task(user_input)
        except Exception as exc:
            return {
                "success": False,
                "mode": "scheduler",
                "summary": "Failed to submit task to scheduler.",
                "data": {},
                "error": str(exc),
            }

        return {
            "success": True,
            "mode": "scheduler",
            "summary": submit_result.get("summary", "Task submitted."),
            "data": {
                "submit_result": submit_result,
                "scheduler_state": self.scheduler.get_scheduler_state(),
            },
            "error": None,
        }

    def _safe_route(self, user_input: str) -> Dict[str, Any]:
        if self.router is None:
            return {"mode": "task", "tool_name": None, "tool_args": {}}

        for method_name in ("route", "run", "__call__"):
            method = getattr(self.router, method_name, None)
            if callable(method):
                result = method(user_input)
                if isinstance(result, dict):
                    return result

        return {"mode": "task", "tool_name": None, "tool_args": {}}

    def _get_tool(self, name: Optional[str]) -> Optional[Any]:
        if not name:
            return None

        if hasattr(self.tool_registry, "get_tool"):
            tool = self.tool_registry.get_tool(name)
            if tool is not None:
                return tool

        if hasattr(self.tool_registry, "tools"):
            tools = getattr(self.tool_registry, "tools")
            if isinstance(tools, dict):
                return tools.get(name)

        return None

    def _run_tool(self, tool: Any, tool_args: Dict[str, Any]) -> Any:
        execute_method = getattr(tool, "execute", None)
        if callable(execute_method):
            try:
                return execute_method(tool_args)
            except TypeError:
                pass

        run_method = getattr(tool, "run", None)
        if callable(run_method):
            return run_method(**tool_args)

        call_method = getattr(tool, "__call__", None)
        if callable(call_method):
            return call_method(**tool_args)

        raise RuntimeError(
            f"Tool '{getattr(tool, 'name', str(tool))}' has no callable execute/run method."
        )


class ZeroSystem:
    def __init__(self, boot: Dict[str, Any]) -> None:
        self._boot = boot
        self.agent = boot.get("agent")
        self.router = boot.get("router")
        self.llm_client = boot.get("llm_client")
        self.tool_registry = boot.get("tool_registry")
        self.workspace_tool = boot.get("workspace_tool")
        self.command_tool = boot.get("command_tool")
        self.task_manager = boot.get("task_manager")
        self.task_runtime = boot.get("task_runtime")
        self.scheduler = boot.get("scheduler")
        self.project_root = boot.get("project_root")
        self.workspace_root = boot.get("workspace_root")
        self.boot_info = boot.get("boot_info", {})
        self.started_at = time.time()

    def enqueue(
        self,
        goal: str,
        dependencies: Optional[List[str]] = None,
        max_retries: Optional[int] = None,
        retry_delay_ticks: Optional[int] = None,
    ) -> Dict[str, Any]:
        clean_goal = str(goal or "").strip()
        if not clean_goal:
            return {
                "success": False,
                "summary": "Goal cannot be empty.",
                "error": "empty_goal",
            }

        normalized_deps: List[str] = []
        if dependencies:
            seen = set()
            for dep in dependencies:
                dep_name = str(dep or "").strip()
                if not dep_name:
                    continue
                if dep_name in seen:
                    continue
                seen.add(dep_name)
                normalized_deps.append(dep_name)

        try:
            result = self.scheduler.submit_task(
                clean_goal,
                dependencies=normalized_deps,
                max_retries=max_retries,
                retry_delay_ticks=retry_delay_ticks,
            )
        except Exception as exc:
            return {
                "success": False,
                "summary": "Failed to enqueue task.",
                "error": str(exc),
            }

        task = result.get("task", {}) if isinstance(result, dict) else {}
        task_name = str(task.get("task_name", "")).strip()

        return {
            "success": True,
            "summary": result.get("summary", "Task queued."),
            "task": task,
            "id": task_name,
            "action": result.get("action"),
            "scheduler_state": self.scheduler.get_scheduler_state(),
            "error": None,
        }

    def queue_list(self) -> Dict[str, Any]:
        tasks = self._collect_tasks()
        return {
            "success": True,
            "count": len(tasks),
            "tasks": tasks,
            "scheduler_state": self.scheduler.get_scheduler_state(),
            "error": None,
        }

    def queue_get(self, qid: str) -> Dict[str, Any]:
        task_name = str(qid or "").strip()
        if not task_name:
            return {
                "success": False,
                "summary": "Task id is required.",
                "error": "empty_task_id",
            }

        task = self._get_task(task_name)
        if task is None:
            return {
                "success": False,
                "summary": f"Task not found: {task_name}",
                "error": "task_not_found",
            }

        return {
            "success": True,
            "task": task,
            "error": None,
        }

    def queue_pause(self, qid: str) -> Dict[str, Any]:
        task_name = str(qid or "").strip()
        if not task_name:
            return {
                "success": False,
                "summary": "Task id is required.",
                "error": "empty_task_id",
            }

        task = self._get_task(task_name)
        if task is None:
            return {
                "success": False,
                "summary": f"Task not found: {task_name}",
                "error": "task_not_found",
            }

        try:
            result = self.task_runtime.pause_task(task, reason="manual_pause")
        except Exception as exc:
            return {
                "success": False,
                "summary": f"Failed to pause task: {task_name}",
                "error": str(exc),
            }

        if task_name == self.scheduler._current_task_name:
            self.scheduler._current_task_name = None

        if task_name not in self.scheduler._paused_stack:
            self.scheduler._paused_stack.append(task_name)

        self.scheduler._set_task_status(task_name, "paused")

        return {
            "success": True,
            "summary": result.get("summary", f"Task paused: {task_name}"),
            "task": self._get_task(task_name),
            "runtime": result,
            "error": None,
        }

    def queue_resume(self, qid: str) -> Dict[str, Any]:
        task_name = str(qid or "").strip()
        if not task_name:
            return {
                "success": False,
                "summary": "Task id is required.",
                "error": "empty_task_id",
            }

        task = self._get_task(task_name)
        if task is None:
            return {
                "success": False,
                "summary": f"Task not found: {task_name}",
                "error": "task_not_found",
            }

        try:
            result = self.task_runtime.resume_task(task)
        except Exception as exc:
            return {
                "success": False,
                "summary": f"Failed to resume task: {task_name}",
                "error": str(exc),
            }

        self.scheduler._set_task_status(task_name, "queued")
        self.scheduler._push_pending(task_name)

        return {
            "success": True,
            "summary": result.get("summary", f"Task resumed: {task_name}"),
            "task": self._get_task(task_name),
            "runtime": result,
            "error": None,
        }

    def queue_cancel(self, qid: str) -> Dict[str, Any]:
        task_name = str(qid or "").strip()
        if not task_name:
            return {
                "success": False,
                "summary": "Task id is required.",
                "error": "empty_task_id",
            }

        task = self._get_task(task_name)
        if task is None:
            return {
                "success": False,
                "summary": f"Task not found: {task_name}",
                "error": "task_not_found",
            }

        task_dir = self._get_task_dir(task_name)
        self._append_task_log(task_dir, f"Task canceled: {task_name}")

        try:
            self._update_task_status(task_name, "canceled")
        except Exception as exc:
            return {
                "success": False,
                "summary": f"Failed to cancel task: {task_name}",
                "error": str(exc),
            }

        if self.scheduler._current_task_name == task_name:
            self.scheduler._current_task_name = None

        self.scheduler._paused_stack = [
            name for name in self.scheduler._paused_stack if name != task_name
        ]
        self.scheduler._pending_heap = [
            item for item in self.scheduler._pending_heap if item[2] != task_name
        ]

        import heapq
        heapq.heapify(self.scheduler._pending_heap)

        return {
            "success": True,
            "summary": f"Task canceled: {task_name}",
            "task": self._get_task(task_name),
            "scheduler_state": self.scheduler.get_scheduler_state(),
            "error": None,
        }

    def queue_reprioritize(self, qid: str, priority: int) -> Dict[str, Any]:
        task_name = str(qid or "").strip()
        if not task_name:
            return {
                "success": False,
                "summary": "Task id is required.",
                "error": "empty_task_id",
            }

        task = self._get_task(task_name)
        if task is None:
            return {
                "success": False,
                "summary": f"Task not found: {task_name}",
                "error": "task_not_found",
            }

        try:
            new_priority = int(priority)
        except Exception:
            return {
                "success": False,
                "summary": "Priority must be an integer.",
                "error": "invalid_priority",
            }

        task["priority"] = new_priority
        if task_name in self.scheduler._tasks:
            self.scheduler._tasks[task_name]["priority"] = new_priority

        self._rewrite_pending_heap()

        current_task = self.scheduler.get_current_task()
        if current_task is not None:
            current_name = str(current_task.get("task_name", "")).strip()
            current_priority = int(current_task.get("priority", 0))

            target_task = self._get_task(task_name)
            target_ready = bool(target_task) and self.scheduler._dependencies_satisfied(target_task)
            target_blocked = bool(target_task) and self.scheduler._dependency_block_reason(target_task)

            if (
                task_name != current_name
                and target_ready
                and not target_blocked
                and new_priority > current_priority
            ):
                self.scheduler._preempt_current_task(
                    reason=f"reprioritized_higher_priority:{task_name}"
                )
                self.scheduler._set_task_status(task_name, "queued")
                self.scheduler._push_pending(task_name)

        return {
            "success": True,
            "summary": f"Task reprioritized: {task_name} -> {new_priority}",
            "task": self._get_task(task_name),
            "scheduler_state": self.scheduler.get_scheduler_state(),
            "error": None,
        }

    def health(self) -> Dict[str, Any]:
        uptime_sec = round(time.time() - self.started_at, 3)
        return {
            "success": True,
            "status": "ok",
            "uptime_sec": uptime_sec,
            "boot_info": self.boot_info,
            "scheduler_state": self.scheduler.get_scheduler_state(),
            "task_count": len(self._collect_tasks()),
            "error": None,
        }

    def stop(self) -> Dict[str, Any]:
        return {
            "success": True,
            "summary": "ZERO system stopped.",
            "error": None,
        }

    def _collect_tasks(self) -> List[Dict[str, Any]]:
        tasks: List[Dict[str, Any]] = []

        if hasattr(self.scheduler, "_tasks"):
            raw_tasks = getattr(self.scheduler, "_tasks")
            if isinstance(raw_tasks, dict):
                for _, value in raw_tasks.items():
                    if isinstance(value, dict):
                        tasks.append(value)

        elif hasattr(self.task_manager, "_tasks"):
            raw_tasks = getattr(self.task_manager, "_tasks")
            if isinstance(raw_tasks, dict):
                for _, value in raw_tasks.items():
                    if isinstance(value, dict):
                        tasks.append(value)

        tasks.sort(key=lambda item: str(item.get("task_name", "")))
        return tasks

    def _get_task(self, task_name: str) -> Optional[Dict[str, Any]]:
        if hasattr(self.scheduler, "get_task") and callable(getattr(self.scheduler, "get_task")):
            try:
                task = self.scheduler.get_task(task_name)
                if isinstance(task, dict):
                    return task
            except Exception:
                pass

        if hasattr(self.task_manager, "get_task") and callable(getattr(self.task_manager, "get_task")):
            try:
                task = self.task_manager.get_task(task_name)
                if isinstance(task, dict):
                    return task
            except Exception:
                pass

        return None

    def _update_task_status(self, task_name: str, status: str) -> None:
        if hasattr(self.task_manager, "update_task_status") and callable(
            getattr(self.task_manager, "update_task_status")
        ):
            self.task_manager.update_task_status(task_name, status)

        if hasattr(self.scheduler, "_tasks") and task_name in self.scheduler._tasks:
            self.scheduler._tasks[task_name]["status"] = status

    def _rewrite_pending_heap(self) -> None:
        import heapq

        new_heap: List[Tuple[int, int, str]] = []
        sequence = 0

        for task_name, task in self.scheduler._tasks.items():
            if not isinstance(task, dict):
                continue

            status = str(task.get("status", "")).strip().lower()
            if status != "queued":
                continue

            priority = self._coerce_int(task.get("priority"), 0)
            new_heap.append((-priority, sequence, task_name))
            sequence += 1

        heapq.heapify(new_heap)
        self.scheduler._pending_heap = new_heap
        self.scheduler._sequence = sequence

    def _get_task_dir(self, task_name: str) -> Path:
        return Path(self.workspace_root) / task_name

    def _append_task_log(self, task_dir: Path, text: str) -> None:
        task_dir.mkdir(parents=True, exist_ok=True)
        log_file = task_dir / "log.txt"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(text + "\n")

    def _coerce_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default


def _import_first(candidates: List[Tuple[str, str]]) -> Optional[Any]:
    for module_name, attr_name in candidates:
        try:
            module = importlib.import_module(module_name)
            return getattr(module, attr_name)
        except Exception:
            continue
    return None


def _instantiate_best(cls: Any, **kwargs: Any) -> Any:
    if cls is None:
        return None

    try:
        signature = inspect.signature(cls)
        accepted_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in signature.parameters
        }
        return cls(**accepted_kwargs)
    except Exception:
        try:
            return cls()
        except Exception:
            return None


def _register_tool(registry: Any, tool: Any) -> None:
    if registry is None or tool is None:
        return

    tool_name = str(getattr(tool, "name", tool.__class__.__name__.lower())).strip()
    if not tool_name:
        tool_name = tool.__class__.__name__.lower()

    register_method = getattr(registry, "register", None)
    if callable(register_method):
        try:
            register_method(tool)
            return
        except TypeError:
            pass
        except Exception:
            pass

        try:
            register_method(tool_name, tool)
            return
        except TypeError:
            pass
        except Exception:
            pass

    register_tool_method = getattr(registry, "register_tool", None)
    if callable(register_tool_method):
        try:
            register_tool_method(tool)
            return
        except TypeError:
            pass
        except Exception:
            pass

        try:
            register_tool_method(tool_name, tool)
            return
        except TypeError:
            pass
        except Exception:
            pass

    tools_attr = getattr(registry, "tools", None)
    if isinstance(tools_attr, dict):
        tools_attr[tool_name] = tool
        return

    private_tools = getattr(registry, "_tools", None)
    if isinstance(private_tools, dict):
        private_tools[tool_name] = tool
        return

    raise RuntimeError(
        f"Tool registry does not support registering tool '{tool_name}'."
    )


def _extract_tool_names(registry: Any) -> List[str]:
    if registry is None:
        return []

    if hasattr(registry, "list_tool_names") and callable(getattr(registry, "list_tool_names")):
        try:
            result = registry.list_tool_names()
            if isinstance(result, list):
                return [str(x) for x in result]
        except Exception:
            pass

    if hasattr(registry, "list_tools") and callable(getattr(registry, "list_tools")):
        try:
            result = registry.list_tools()
            if isinstance(result, dict) and isinstance(result.get("tools"), list):
                return [str(x) for x in result["tools"]]
            if isinstance(result, list):
                return [str(x) for x in result]
        except Exception:
            pass

    if hasattr(registry, "tools"):
        tools = getattr(registry, "tools")
        if isinstance(tools, dict):
            return [str(x) for x in tools.keys()]

    if hasattr(registry, "_tools"):
        tools = getattr(registry, "_tools")
        if isinstance(tools, dict):
            return [str(x) for x in tools.keys()]

    return []


def bootstrap_system() -> Dict[str, Any]:
    project_root = PROJECT_ROOT
    workspace_root = project_root / "workspace"
    workspace_root.mkdir(parents=True, exist_ok=True)

    RouterClass = _import_first(
        [
            ("core.router", "Router"),
            ("router", "Router"),
        ]
    )

    LLMClientClass = _import_first(
        [
            ("core.llm_client", "LLMClient"),
            ("llm_client", "LLMClient"),
        ]
    )

    ToolRegistryClass = _import_first(
        [
            ("core.tool_registry", "ToolRegistry"),
            ("tool_registry", "ToolRegistry"),
        ]
    )

    AgentLoopClass = _import_first(
        [
            ("core.agent_loop", "AgentLoop"),
            ("agent_loop", "AgentLoop"),
        ]
    )

    router = _instantiate_best(RouterClass) or SimpleRouter()
    llm_client = _instantiate_best(LLMClientClass)

    tool_registry = _instantiate_best(
        ToolRegistryClass,
        workspace_root=str(workspace_root),
    ) or SimpleToolRegistry()

    workspace_tool = WorkspaceTool(workspace_root=workspace_root)
    command_tool = CommandTool(workspace_root=workspace_root)
    task_manager = TaskManager(workspace_root=workspace_root)

    task_runtime = TaskRuntime(
        workspace_root=workspace_root,
        task_manager=task_manager,
        tool_registry=tool_registry,
    )

    scheduler = TaskScheduler(
        task_manager=task_manager,
        task_runtime=task_runtime,
    )

    if not getattr(tool_registry, "has_tool", lambda _name: False)("workspace_tool"):
        _register_tool(tool_registry, workspace_tool)

    if not getattr(tool_registry, "has_tool", lambda _name: False)("command_tool"):
        _register_tool(tool_registry, command_tool)

    AgentLoopClass = AgentLoopClass or SimpleAgentLoop
    agent = _instantiate_best(
        AgentLoopClass,
        router=router,
        llm_client=llm_client,
        tool_registry=tool_registry,
        project_root=project_root,
        workspace_root=workspace_root,
        task_manager=task_manager,
        task_runtime=task_runtime,
        scheduler=scheduler,
    )

    if agent is None:
        agent = SimpleAgentLoop(
            router=router,
            llm_client=llm_client,
            tool_registry=tool_registry,
            project_root=project_root,
            workspace_root=workspace_root,
            task_manager=task_manager,
            task_runtime=task_runtime,
            scheduler=scheduler,
        )

    boot_info = {
        "project_root": str(project_root),
        "workspace_root": str(workspace_root),
        "router_name": router.__class__.__name__ if router else "None",
        "llm_client_name": llm_client.__class__.__name__ if llm_client else "None",
        "agent_loop_name": agent.__class__.__name__ if agent else "None",
        "task_manager_name": task_manager.__class__.__name__ if task_manager else "None",
        "task_runtime_name": task_runtime.__class__.__name__ if task_runtime else "None",
        "scheduler_name": scheduler.__class__.__name__ if scheduler else "None",
        "tool_names": _extract_tool_names(tool_registry),
    }

    return {
        "agent": agent,
        "router": router,
        "llm_client": llm_client,
        "tool_registry": tool_registry,
        "workspace_tool": workspace_tool,
        "command_tool": command_tool,
        "task_manager": task_manager,
        "task_runtime": task_runtime,
        "scheduler": scheduler,
        "project_root": project_root,
        "workspace_root": workspace_root,
        "boot_info": boot_info,
    }


_zero_system_instance: Optional["ZeroSystem"] = None


def get_zero_system() -> "ZeroSystem":
    global _zero_system_instance

    if _zero_system_instance is None:
        boot = bootstrap_system()
        _zero_system_instance = ZeroSystem(boot)

    return _zero_system_instance