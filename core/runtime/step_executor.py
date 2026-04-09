from __future__ import annotations

import copy
import os
from typing import Any, Callable, Dict, List, Optional

from core.tasks.task_paths import TaskPathManager
from core.runtime.step_handlers import (
    ToolStepHandler,
    CommandStepHandler,
    WriteFileStepHandler,
    ReadFileStepHandler,
    RespondStepHandler,
    LLMStepHandler,
)

StepHandler = Callable[[Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Any], Dict[str, Any]]


class StepExecutor:
    """
    ZERO Step Executor v6

    Path resolve priority:
    1. shared/... -> workspace/shared/
    2. task sandbox
    3. fallback -> workspace/shared/
    """

    def __init__(
        self,
        tool_registry=None,
        runtime_store=None,
        reflection_engine=None,
        llm_client=None,
        workspace_root: str = "workspace",
        debug: bool = False,
    ):
        self.tool_registry = tool_registry
        self.runtime_store = runtime_store
        self.reflection_engine = reflection_engine
        self.llm_client = llm_client
        self.workspace_root = os.path.abspath(workspace_root)
        self.debug = debug

        self.path_manager = TaskPathManager(workspace_root=self.workspace_root)
        self.path_manager.ensure_workspace()

        self.shared_dir = os.path.join(self.workspace_root, "shared")
        os.makedirs(self.shared_dir, exist_ok=True)

        self.handlers: Dict[str, StepHandler] = {}
        self._register_builtin_handlers()

    # ============================================================
    # Handler registry
    # ============================================================

    def register_handler(self, step_type: str, handler: StepHandler) -> None:
        key = str(step_type or "").strip().lower()
        if not key:
            raise ValueError("step_type is empty")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self.handlers[key] = handler

    def has_handler(self, step_type: str) -> bool:
        key = str(step_type or "").strip().lower()
        return key in self.handlers

    def list_handlers(self) -> List[str]:
        return sorted(self.handlers.keys())

    def _register_builtin_handlers(self) -> None:
        self.register_handler("tool", ToolStepHandler(self).handle)
        self.register_handler("command", CommandStepHandler(self).handle)
        self.register_handler("write_file", WriteFileStepHandler(self).handle)
        self.register_handler("workspace_write", WriteFileStepHandler(self).handle)
        self.register_handler("read_file", ReadFileStepHandler(self).handle)
        self.register_handler("workspace_read", ReadFileStepHandler(self).handle)
        self.register_handler("respond", RespondStepHandler(self).handle)
        self.register_handler("final_answer", RespondStepHandler(self).handle)
        self.register_handler("llm", LLMStepHandler(self).handle)

    # ============================================================
    # Execute
    # ============================================================

    def execute(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        previous_result: Any = None,
        step_index: Optional[int] = None,
        step_count: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return self.execute_step(
            step=step,
            task=task,
            context=context,
            previous_result=previous_result,
            step_index=step_index,
            step_count=step_count,
            **kwargs,
        )

    # ============================================================
    # Single step
    # ============================================================

    def execute_step(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        previous_result: Any = None,
        step_index: Optional[int] = None,
        step_count: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        step = copy.deepcopy(step or {})
        task = self._normalize_task(task)
        context = copy.deepcopy(context) if isinstance(context, dict) else {}

        step_type = str(step.get("type", "")).lower().strip()

        if self.debug:
            print(f"[StepExecutor] step_type = {step_type}")

        handler = self.handlers.get(step_type)
        if handler is None:
            return {
                "ok": False,
                "error": f"unsupported step type: {step_type}",
                "result": {
                    "supported_step_types": self.list_handlers(),
                },
                "step": copy.deepcopy(step),
            }

        try:
            return handler(step, task, context, previous_result)
        except Exception as e:
            return {
                "ok": False,
                "error": f"step handler exception: {e}",
                "result": {},
                "step": copy.deepcopy(step),
            }

    # ============================================================
    # Helpers
    # ============================================================

    def _normalize_task(self, task: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(task, dict):
            return task

        normalized = copy.deepcopy(task)

        try:
            normalized = self.path_manager.enrich_task(normalized)
        except Exception:
            normalized = copy.deepcopy(task)

        normalized.setdefault("workspace_root", self.workspace_root)
        normalized.setdefault("shared_dir", self.shared_dir)

        return normalized

    # ============================================================
    # File path resolve (IMPORTANT)
    # ============================================================

    def resolve_file_path(
        self,
        relative_path: str,
        task: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Resolve file path with fallback:
        1. shared/xxx -> workspace/shared/xxx
        2. task sandbox
        3. workspace/shared fallback
        """
        relative_path = (relative_path or "").replace("\\", "/").strip()

        # shared path
        if relative_path.startswith("shared/"):
            return os.path.join(self.shared_dir, relative_path[len("shared/"):])

        # task sandbox
        if isinstance(task, dict):
            task_dir = task.get("task_dir")
            if task_dir:
                sandbox = os.path.join(task_dir, "sandbox")
                path = os.path.join(sandbox, relative_path)
                if os.path.exists(path):
                    return path

        # fallback -> shared
        return os.path.join(self.shared_dir, relative_path)