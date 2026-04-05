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
    ZERO Step Executor v5

    新增：
    1. shared workspace path resolve
    2. shared/... 路徑會落到 workspace/shared/
    3. task sandbox 仍維持預設行為
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
    # Compatibility entry
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

        if isinstance(task, dict):
            for key in (
                "task_id",
                "task_name",
                "task_dir",
                "workspace",
                "cwd",
                "workspace_dir",
                "workspace_root",
                "shared_dir",
                "plan_file",
                "runtime_state_file",
                "result_file",
                "execution_log_file",
                "log_file",
            ):
                if key not in step and key in task:
                    step[key] = task.get(key)

        if isinstance(context, dict):
            for key in ("workspace", "cwd", "task_dir", "workspace_root", "shared_dir"):
                if key not in step and key in context:
                    step[key] = context.get(key)

        if step_index is not None and "step_index" not in step:
            step["step_index"] = step_index

        if step_count is not None and "step_count" not in step:
            step["step_count"] = step_count

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
    # Multi step
    # ============================================================

    def execute_steps(
        self,
        steps: List[Dict[str, Any]],
        task: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        previous_result: Any = None

        for i, raw_step in enumerate(steps):
            step = copy.deepcopy(raw_step)
            step["step_index"] = i
            step["step_count"] = len(steps)

            result = self.execute_step(
                step=step,
                task=task,
                context=context,
                previous_result=previous_result,
                step_index=i,
                step_count=len(steps),
            )

            results.append(result)
            previous_result = result

            if not result.get("ok", False):
                return {
                    "ok": False,
                    "failed_step": i,
                    "results": results,
                }

        return {
            "ok": True,
            "results": results,
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

    def _extract_inner_ok(self, result: Any) -> bool:
        if isinstance(result, dict):
            if "ok" in result:
                return bool(result.get("ok"))
            if "success" in result:
                return bool(result.get("success"))
            if "returncode" in result:
                try:
                    return int(result.get("returncode", 1)) == 0
                except Exception:
                    return False
        return True

    def _resolve_base_dir_for_file(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]] = None,
    ) -> str:
        path = str(step.get("path", "") or "").replace("\\", "/").strip()
        if path.startswith("shared/"):
            if isinstance(step, dict):
                shared_dir = step.get("shared_dir")
                if isinstance(shared_dir, str) and shared_dir.strip():
                    return shared_dir
            if isinstance(task, dict):
                shared_dir = task.get("shared_dir")
                if isinstance(shared_dir, str) and shared_dir.strip():
                    return shared_dir
            return self.shared_dir

        if isinstance(step, dict):
            for key in ("task_dir", "cwd", "workspace"):
                value = step.get(key)
                if isinstance(value, str) and value.strip():
                    return value

        if isinstance(task, dict):
            for key in ("task_dir", "cwd", "workspace", "workspace_dir"):
                value = task.get(key)
                if isinstance(value, str) and value.strip():
                    return value

        return self.workspace_root

    def _resolve_cwd(
        self,
        step: Optional[Dict[str, Any]] = None,
        task: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if isinstance(step, dict):
            command = str(step.get("command", "") or "").replace("\\", "/")
            if " shared/" in f" {command}" or command.startswith("shared/"):
                shared_dir = step.get("shared_dir")
                if isinstance(shared_dir, str) and shared_dir.strip():
                    return str(step.get("workspace_root") or self.workspace_root)

            for key in ("task_dir", "cwd", "workspace"):
                value = step.get(key)
                if isinstance(value, str) and value.strip():
                    return value

        if isinstance(task, dict):
            for key in ("task_dir", "cwd", "workspace", "workspace_dir"):
                value = task.get(key)
                if isinstance(value, str) and value.strip():
                    return value

        if isinstance(context, dict):
            for key in ("task_dir", "cwd", "workspace"):
                value = context.get(key)
                if isinstance(value, str) and value.strip():
                    return value

        return self.workspace_root