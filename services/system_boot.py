from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _workspace_root() -> Path:
    return _project_root() / "workspace"


def _ensure_workspace_layout(workspace_root: Path) -> None:
    (workspace_root / "tasks").mkdir(parents=True, exist_ok=True)
    (workspace_root / "memory").mkdir(parents=True, exist_ok=True)
    (workspace_root / "temp").mkdir(parents=True, exist_ok=True)
    (workspace_root / "test").mkdir(parents=True, exist_ok=True)
    (workspace_root / "logs").mkdir(parents=True, exist_ok=True)


def _import_first(class_name: str, module_candidates: List[str]) -> Any:
    last_error: Optional[Exception] = None

    for module_name in module_candidates:
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, class_name):
                return getattr(module, class_name)
        except Exception as exc:
            last_error = exc

    tried = ", ".join(module_candidates)
    if last_error is not None:
        raise ImportError(
            f"Cannot import {class_name}. Tried modules: {tried}. Last error: {last_error}"
        )
    raise ImportError(f"Cannot import {class_name}. Tried modules: {tried}.")


def _build_kwargs_for_callable(target: Any, raw_kwargs: Dict[str, Any]) -> Dict[str, Any]:
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError):
        return raw_kwargs

    params = signature.parameters
    has_var_kwargs = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
    )
    if has_var_kwargs:
        return raw_kwargs

    accepted: Dict[str, Any] = {}
    for key, value in raw_kwargs.items():
        if key in params:
            accepted[key] = value
    return accepted


def _safe_construct(cls: Any, **kwargs: Any) -> Any:
    accepted_kwargs = _build_kwargs_for_callable(cls, kwargs)
    return cls(**accepted_kwargs)


def bootstrap_system() -> Dict[str, Any]:
    project_root = _project_root()
    workspace_root = _workspace_root()
    _ensure_workspace_layout(workspace_root)

    Router = _import_first(
        "Router",
        [
            "core.router",
            "router",
            "services.router",
        ],
    )

    ToolRegistry = _import_first(
        "ToolRegistry",
        [
            "core.tool_registry",
            "tool_registry",
            "services.tool_registry",
        ],
    )

    TaskManager = _import_first(
        "TaskManager",
        [
            "core.task_manager",
            "task_manager",
            "services.task_manager",
        ],
    )

    Planner = _import_first(
        "Planner",
        [
            "core.planner",
            "planner",
            "services.planner",
        ],
    )

    AgentLoop = _import_first(
        "AgentLoop",
        [
            "core.agent_loop",
            "agent_loop",
            "services.agent_loop",
        ],
    )

    StepExecutor = _import_first(
        "StepExecutor",
        [
            "core.step_executor",
            "step_executor",
            "services.step_executor",
        ],
    )

    TaskRuntime = _import_first(
        "TaskRuntime",
        [
            "core.task_runtime",
            "task_runtime",
            "services.task_runtime",
        ],
    )

    LlmClientClass: Optional[Any] = None
    for module_name in [
        "core.llm_client",
        "llm_client",
        "services.llm_client",
    ]:
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, "LLMClient"):
                LlmClientClass = getattr(module, "LLMClient")
                break
            if hasattr(module, "LlmClient"):
                LlmClientClass = getattr(module, "LlmClient")
                break
        except Exception:
            continue

    CommandToolClass: Optional[Any] = None
    WorkspaceToolClass: Optional[Any] = None
    FileToolClass: Optional[Any] = None
    WebSearchToolClass: Optional[Any] = None

    for module_name in [
        "tools.command_tool",
        "command_tool",
        "services.command_tool",
    ]:
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, "CommandTool"):
                CommandToolClass = getattr(module, "CommandTool")
                break
        except Exception:
            continue

    for module_name in [
        "tools.workspace_tool",
        "workspace_tool",
        "services.workspace_tool",
    ]:
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, "WorkspaceTool"):
                WorkspaceToolClass = getattr(module, "WorkspaceTool")
                break
        except Exception:
            continue

    for module_name in [
        "tools.file_tool",
        "file_tool",
        "services.file_tool",
    ]:
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, "FileTool"):
                FileToolClass = getattr(module, "FileTool")
                break
        except Exception:
            continue

    for module_name in [
        "tools.web_search_tool",
        "tools.web_search_service",
        "web_search_tool",
        "web_search",
        "services.web_search",
    ]:
        try:
            module = importlib.import_module(module_name)
            if hasattr(module, "WebSearchTool"):
                WebSearchToolClass = getattr(module, "WebSearchTool")
                break
            if hasattr(module, "WebSearchService"):
                WebSearchToolClass = getattr(module, "WebSearchService")
                break
            if hasattr(module, "WebSearch"):
                WebSearchToolClass = getattr(module, "WebSearch")
                break
        except Exception:
            continue

    router = _safe_construct(Router)

    llm_client = None
    if LlmClientClass is not None:
        llm_client = _safe_construct(
            LlmClientClass,
            project_root=str(project_root),
            workspace_root=str(workspace_root),
        )

    tool_registry = _safe_construct(
        ToolRegistry,
        workspace_root=str(workspace_root),
        project_root=str(project_root),
    )

    command_tool = None
    if CommandToolClass is not None:
        command_tool = _safe_construct(
            CommandToolClass,
            workspace_root=str(workspace_root),
            project_root=str(project_root),
        )
        tool_registry.register_tool("command_tool", command_tool)

    workspace_tool = None
    if WorkspaceToolClass is not None:
        workspace_tool = _safe_construct(
            WorkspaceToolClass,
            workspace_root=str(workspace_root),
            project_root=str(project_root),
        )
        tool_registry.register_tool("workspace_tool", workspace_tool)

    file_tool = None
    if FileToolClass is not None:
        file_tool = _safe_construct(
            FileToolClass,
            workspace_root=str(workspace_root),
            project_root=str(project_root),
        )
        tool_registry.register_tool("file_tool", file_tool)

    web_search_tool = None
    if WebSearchToolClass is not None:
        web_search_tool = _safe_construct(
            WebSearchToolClass,
            workspace_root=str(workspace_root),
            project_root=str(project_root),
        )
        tool_registry.register_tool("web_search", web_search_tool)

    planner = _safe_construct(
        Planner,
        llm_client=llm_client,
        tool_registry=tool_registry,
        workspace_root=str(workspace_root),
        project_root=str(project_root),
    )

    task_manager = _safe_construct(
        TaskManager,
        workspace_root=str(workspace_root),
        planner=planner,
    )

    step_executor = _safe_construct(
        StepExecutor,
        task_manager=task_manager,
        tasks_root=str(workspace_root / "tasks"),
        workspace_root=str(workspace_root),
        command_tool=command_tool,
        workspace_tool=workspace_tool,
        file_tool=file_tool,
        web_search=web_search_tool,
        web_search_tool=web_search_tool,
        project_root=str(project_root),
    )

    task_runtime = _safe_construct(
        TaskRuntime,
        task_manager=task_manager,
        step_executor=step_executor,
        planner=planner,
        max_auto_retries=1,
    )

    agent_loop = _safe_construct(
        AgentLoop,
        router=router,
        llm_client=llm_client,
        tool_registry=tool_registry,
        planner=planner,
        task_manager=task_manager,
        task_runtime=task_runtime,
        step_executor=step_executor,
        command_tool=command_tool,
        workspace_tool=workspace_tool,
        file_tool=file_tool,
        web_search=web_search_tool,
        web_search_tool=web_search_tool,
        workspace_root=str(workspace_root),
        project_root=str(project_root),
    )

    return {
        "project_root": str(project_root),
        "workspace_root": str(workspace_root),
        "router": router,
        "llm_client": llm_client,
        "tool_registry": tool_registry,
        "planner": planner,
        "task_manager": task_manager,
        "task_runtime": task_runtime,
        "step_executor": step_executor,
        "agent_loop": agent_loop,
        "command_tool": command_tool,
        "workspace_tool": workspace_tool,
        "file_tool": file_tool,
        "web_search": web_search_tool,
        "web_search_tool": web_search_tool,
    }