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
    EnsureFileStepHandler,
)
from core.runtime.safety_guard import SafetyGuard

StepHandler = Callable[
    [Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Any],
    Dict[str, Any],
]


class StepExecutor:
    """
    ZERO Step Executor v12

    核心規則：
    1. single-shot -> workspace/shared
    2. real task -> workspace/tasks/<task_id>/sandbox
    3. execute_step 前先經過 safety guard
    4. 自動修正常見 path 重複前綴：
       - shared/xxx
       - workspace/shared/xxx
       - ./shared/xxx
       - .\\shared\\xxx
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

        self.safety_guard = SafetyGuard(
            workspace_root=self.workspace_root,
            shared_dir=self.shared_dir,
            debug=self.debug,
        )

        self.handlers: Dict[str, StepHandler] = {}
        self._register_builtin_handlers()

        print("### StepExecutor v12 (guard enabled, ensure_file added, single-shot -> shared, task -> sandbox, path normalize fixed) ###")

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
        self.register_handler("ensure_file", EnsureFileStepHandler(self).handle)
        self.register_handler("read_file", ReadFileStepHandler(self).handle)
        self.register_handler("workspace_read", ReadFileStepHandler(self).handle)
        self.register_handler("respond", RespondStepHandler(self).handle)
        self.register_handler("final_answer", RespondStepHandler(self).handle)
        self.register_handler("llm", LLMStepHandler(self).handle)
        self.register_handler("llm_generate", LLMStepHandler(self).handle)

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
            print(f"[StepExecutor] task = {task}")

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

        guard_result = self.safety_guard.check_step(
            step=step,
            task=task,
            context=context,
            executor=self,
        )
        if not guard_result.get("ok", False):
            return {
                "ok": False,
                "error": f"safety_guard blocked step: {guard_result.get('error')}",
                "result": {
                    "guard_result": guard_result,
                },
                "step": copy.deepcopy(step),
            }

        try:
            result = handler(step, task, context, previous_result)

            if not isinstance(result, dict):
                return {
                    "ok": False,
                    "error": "step handler returned non-dict result",
                    "result": {"raw_result": result},
                    "step": copy.deepcopy(step),
                }

            return result

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
        """
        規則：
        - task mode: 正常 enrich_task，保留真正 task_id / sandbox
        - single-shot: 補一個 pseudo-task，但 file path 一律導到 shared
        """
        if not isinstance(task, dict):
            return self._build_shared_pseudo_task()

        normalized = copy.deepcopy(task)

        try:
            normalized = self.path_manager.enrich_task(normalized)
        except Exception:
            normalized = copy.deepcopy(task)

        normalized.setdefault("workspace_root", self.workspace_root)
        normalized.setdefault("shared_dir", self.shared_dir)

        if not normalized.get("task_id") and not normalized.get("id"):
            pseudo = self._build_shared_pseudo_task()
            pseudo.update(normalized)
            pseudo["is_pseudo_task"] = True
            pseudo["mode"] = "single_shot"
            pseudo["task_dir"] = self.shared_dir
            pseudo["sandbox_dir"] = self.shared_dir
            normalized = pseudo
        else:
            task_dir = normalized.get("task_dir")
            if isinstance(task_dir, str) and task_dir.strip():
                sandbox_dir = os.path.join(task_dir, "sandbox")
                normalized.setdefault("sandbox_dir", sandbox_dir)

        return normalized

    def _build_shared_pseudo_task(self) -> Dict[str, Any]:
        return {
            "mode": "single_shot",
            "is_pseudo_task": True,
            "task_id": "",
            "id": "",
            "task_name": "single_shot",
            "workspace_root": self.workspace_root,
            "shared_dir": self.shared_dir,
            "task_dir": self.shared_dir,
            "sandbox_dir": self.shared_dir,
        }

    def _normalize_relative_path(self, relative_path: str) -> str:
        """
        將常見的 shared/workspace/shared 前綴統一剝掉，
        讓 single-shot 一律落到 workspace/shared/<filename>
        """
        path = str(relative_path or "").strip().replace("\\", "/")

        while path.startswith("./"):
            path = path[2:]

        prefixes = [
            "workspace/shared/",
            "shared/",
        ]

        changed = True
        while changed:
            changed = False
            for prefix in prefixes:
                if path.startswith(prefix):
                    path = path[len(prefix):]
                    changed = True

        return path.strip("/")

    def resolve_file_path(
        self,
        relative_path: str,
        task: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Path resolve rules:
        1. absolute path -> direct
        2. shared/... -> workspace/shared/...
        3. workspace/shared/... -> workspace/shared/...
        4. pseudo-task(single-shot) -> workspace/shared/...
        5. real task -> workspace/tasks/<task_id>/sandbox/...
        6. fallback -> workspace/shared/...
        """
        raw_path = str(relative_path or "").strip()
        if not raw_path:
            return self.shared_dir

        if os.path.isabs(raw_path):
            return os.path.abspath(raw_path)

        normalized_rel = self._normalize_relative_path(raw_path)

        if not normalized_rel:
            return self.shared_dir

        normalized_task = self._normalize_task(task)

        if isinstance(normalized_task, dict):
            if normalized_task.get("is_pseudo_task") is True:
                return os.path.join(self.shared_dir, normalized_rel)

            sandbox_dir = normalized_task.get("sandbox_dir")
            task_dir = normalized_task.get("task_dir")

            if isinstance(sandbox_dir, str) and sandbox_dir.strip():
                sandbox_dir = os.path.abspath(sandbox_dir)
                os.makedirs(sandbox_dir, exist_ok=True)
                return os.path.join(sandbox_dir, normalized_rel)

            if isinstance(task_dir, str) and task_dir.strip():
                task_dir = os.path.abspath(task_dir)
                sandbox = os.path.join(task_dir, "sandbox")
                os.makedirs(sandbox, exist_ok=True)
                return os.path.join(sandbox, normalized_rel)

        return os.path.join(self.shared_dir, normalized_rel)

    # ============================================================
    # Compatibility helpers for step_handlers.py
    # ============================================================

    def _extract_inner_ok(self, result: Any) -> bool:
        if isinstance(result, dict):
            if "ok" in result:
                return bool(result.get("ok"))
            if "success" in result:
                return bool(result.get("success"))
        return result is not None

    def _resolve_cwd(
        self,
        step: Optional[Dict[str, Any]] = None,
        task: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        step = step if isinstance(step, dict) else {}
        task = self._normalize_task(task)
        context = context if isinstance(context, dict) else {}

        cwd = step.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            cwd = cwd.strip()
            if os.path.isabs(cwd):
                return cwd
            return os.path.abspath(cwd)

        if isinstance(task, dict) and task.get("is_pseudo_task") is True:
            return self.shared_dir

        if isinstance(task, dict):
            sandbox_dir = task.get("sandbox_dir")
            if isinstance(sandbox_dir, str) and sandbox_dir.strip():
                os.makedirs(sandbox_dir, exist_ok=True)
                return os.path.abspath(sandbox_dir)

            task_dir = task.get("task_dir")
            if isinstance(task_dir, str) and task_dir.strip():
                sandbox_dir = os.path.join(task_dir, "sandbox")
                os.makedirs(sandbox_dir, exist_ok=True)
                return os.path.abspath(sandbox_dir)

        cwd_from_context = context.get("cwd")
        if isinstance(cwd_from_context, str) and cwd_from_context.strip():
            if os.path.isabs(cwd_from_context):
                return cwd_from_context
            return os.path.abspath(cwd_from_context)

        return os.path.abspath(self.workspace_root)