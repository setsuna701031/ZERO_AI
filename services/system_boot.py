from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CURRENT_FILE = Path(__file__).resolve()
SERVICES_DIR = CURRENT_FILE.parent
PROJECT_ROOT = SERVICES_DIR.parent
CORE_DIR = PROJECT_ROOT / "core"
TOOLS_DIR = PROJECT_ROOT / "tools"

for path in [
    PROJECT_ROOT,
    CORE_DIR,
    TOOLS_DIR,
    SERVICES_DIR,
]:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from core.task_manager import TaskManager
from core.task_runtime import TaskRuntime
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
    """
    備援版 AgentLoop
    只保留最小 Runtime 流程：
    - tool 模式 -> 跑工具
    - 其他 -> create_task -> run_task
    """

    def __init__(
        self,
        router: Any = None,
        llm_client: Any = None,
        tool_registry: Any = None,
        task_manager: Any = None,
        task_runtime: Any = None,
        **kwargs: Any,
    ) -> None:
        self.router = router or SimpleRouter()
        self.llm_client = llm_client
        self.tool_registry = tool_registry or SimpleToolRegistry()
        self.task_manager = task_manager
        self.task_runtime = task_runtime
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

        if self.task_manager is None:
            return {
                "success": False,
                "mode": "task",
                "summary": "Task manager is not available.",
                "data": {},
                "error": "task_manager is not configured.",
            }

        if self.task_runtime is None:
            return {
                "success": False,
                "mode": "runtime",
                "summary": "Task runtime is not available.",
                "data": {},
                "error": "task_runtime is not configured.",
            }

        try:
            task = self.task_manager.create_task(user_input)
        except Exception as exc:
            return {
                "success": False,
                "mode": "task",
                "summary": "Failed to create task.",
                "data": {},
                "error": str(exc),
            }

        try:
            runtime_result = self.task_runtime.run_task(task)
        except Exception as exc:
            return {
                "success": False,
                "mode": "runtime",
                "summary": "Task runtime execution failed.",
                "data": {"task": task},
                "error": str(exc),
            }

        normalized_result = self._normalize_runtime_result(runtime_result)

        return {
            "success": normalized_result["success"],
            "mode": "runtime",
            "summary": normalized_result["summary"],
            "data": {
                "task": task,
                "runtime_result": normalized_result["data"],
            },
            "error": normalized_result["error"],
        }

    def _normalize_runtime_result(self, runtime_result: Any) -> Dict[str, Any]:
        if isinstance(runtime_result, dict):
            success = bool(runtime_result.get("success", True))
            summary = str(runtime_result.get("summary", "Task executed."))
            data = runtime_result.get("data", runtime_result)
            error = runtime_result.get("error")
            return {
                "success": success,
                "summary": summary,
                "data": data,
                "error": error,
            }

        if isinstance(runtime_result, str):
            return {
                "success": True,
                "summary": "Task executed.",
                "data": {"answer": runtime_result},
                "error": None,
            }

        if runtime_result is None:
            return {
                "success": True,
                "summary": "Task executed with no result.",
                "data": {},
                "error": None,
            }

        return {
            "success": True,
            "summary": "Task executed.",
            "data": {"result": runtime_result},
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

    if hasattr(registry, "register") and callable(getattr(registry, "register")):
        try:
            registry.register(tool)
            return
        except TypeError:
            pass

    if hasattr(registry, "register_tool") and callable(getattr(registry, "register_tool")):
        registry.register_tool(tool)
        return

    if hasattr(registry, "tools") and isinstance(getattr(registry, "tools"), dict):
        tool_name = getattr(tool, "name", tool.__class__.__name__.lower())
        registry.tools[tool_name] = tool
        return

    raise RuntimeError("Tool registry does not support register/register_tool/tools dict.")


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
            return list(tools.keys())

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
        )

    boot_info = {
        "project_root": str(project_root),
        "workspace_root": str(workspace_root),
        "router_name": router.__class__.__name__ if router else "None",
        "llm_client_name": llm_client.__class__.__name__ if llm_client else "None",
        "agent_loop_name": agent.__class__.__name__ if agent else "None",
        "task_manager_name": task_manager.__class__.__name__ if task_manager else "None",
        "task_runtime_name": task_runtime.__class__.__name__ if task_runtime else "None",
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
        "project_root": project_root,
        "workspace_root": workspace_root,
        "boot_info": boot_info,
    }