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
    VerifyStepHandler,
    RunPythonStepHandler,
)

StepHandler = Callable[[Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Any], Dict[str, Any]]


class StepExecutor:
    """
    ZERO Step Executor

    這版收束目標：
    1. step handler 輸出統一 envelope
    2. unsupported / exception 錯誤格式統一
    3. execute_steps 批次結果格式統一
    4. 與目前 tool registry 的 outer/inner ok 結構對齊
    """

    def __init__(
        self,
        tool_registry=None,
        runtime_store=None,
        reflection_engine=None,
        llm_client=None,
        workspace_root: str = "workspace",
        debug: bool = False,
    ) -> None:
        self.tool_registry = tool_registry
        self.runtime_store = runtime_store
        self.reflection_engine = reflection_engine
        self.llm_client = llm_client
        self.workspace_root = os.path.abspath(workspace_root)
        self.debug = debug

        self.path_manager = TaskPathManager(workspace_root=self.workspace_root)
        self.path_manager.ensure_workspace()

        self.handlers: Dict[str, StepHandler] = {}
        self._register_builtin_handlers()

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
        self.register_handler("run_python", RunPythonStepHandler(self).handle)
        self.register_handler("write_file", WriteFileStepHandler(self).handle)
        self.register_handler("workspace_write", WriteFileStepHandler(self).handle)
        self.register_handler("read_file", ReadFileStepHandler(self).handle)
        self.register_handler("workspace_read", ReadFileStepHandler(self).handle)
        self.register_handler("ensure_file", EnsureFileStepHandler(self).handle)
        self.register_handler("verify", VerifyStepHandler(self).handle)
        self.register_handler("respond", RespondStepHandler(self).handle)
        self.register_handler("final_answer", RespondStepHandler(self).handle)
        self.register_handler("llm", LLMStepHandler(self).handle)
        self.register_handler("llm_generate", LLMStepHandler(self).handle)

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
        raw_step = copy.deepcopy(step or {})
        normalized_task = self._normalize_task(task)
        normalized_context = copy.deepcopy(context) if isinstance(context, dict) else {}

        step_payload = self._merge_execution_context(
            step=raw_step,
            task=normalized_task,
            context=normalized_context,
            step_index=step_index,
            step_count=step_count,
        )

        step_type = str(step_payload.get("type", "")).strip().lower()

        if self.debug:
            print(f"[StepExecutor] step_type = {step_type}")

        handler = self.handlers.get(step_type)
        if handler is None:
            return self._error_step_result(
                step=step_payload,
                task=normalized_task,
                error_type="unsupported_step_type",
                message=f"unsupported step type: {step_type}",
                details={"supported_step_types": self.list_handlers()},
            )

        try:
            raw_result = handler(step_payload, normalized_task, normalized_context, previous_result)
            return self._normalize_step_result(
                raw_result=raw_result,
                step=step_payload,
                task=normalized_task,
            )
        except Exception as exc:
            return self._error_step_result(
                step=step_payload,
                task=normalized_task,
                error_type="step_handler_exception",
                message=str(exc),
                details={"exception_class": exc.__class__.__name__},
            )

    def execute_steps(
        self,
        steps: List[Dict[str, Any]],
        task: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        previous_result: Any = None
        total_steps = len(steps or [])

        for i, raw_step in enumerate(steps or []):
            result = self.execute_step(
                step=raw_step,
                task=task,
                context=context,
                previous_result=previous_result,
                step_index=i,
                step_count=total_steps,
            )
            results.append(result)
            previous_result = result

            if not result.get("ok", False):
                return {
                    "ok": False,
                    "summary": "step execution failed",
                    "step_count": total_steps,
                    "completed_steps": i,
                    "failed_step": i,
                    "results": results,
                    "error": result.get("error"),
                }

        return {
            "ok": True,
            "summary": "all steps executed",
            "step_count": total_steps,
            "completed_steps": total_steps,
            "failed_step": None,
            "results": results,
            "error": None,
        }

    def resolve_write_path(
        self,
        relative_path: str,
        task: Optional[Dict[str, Any]] = None,
        default_scope: str = "sandbox",
    ) -> str:
        normalized_task = self._normalize_task(task)
        return self.path_manager.resolve_write_path(
            relative_path,
            task=normalized_task,
            default_scope=default_scope,
        )

    def resolve_read_path(
        self,
        relative_path: str,
        task: Optional[Dict[str, Any]] = None,
        prefer_scopes: tuple[str, ...] = ("sandbox", "shared"),
        return_fallback_candidate_if_missing: bool = True,
    ) -> str:
        normalized_task = self._normalize_task(task)
        return self.path_manager.resolve_read_path(
            relative_path,
            task=normalized_task,
            prefer_scopes=prefer_scopes,
            return_fallback_candidate_if_missing=return_fallback_candidate_if_missing,
        )

    def resolve_read_candidates(
        self,
        relative_path: str,
        task: Optional[Dict[str, Any]] = None,
        prefer_scopes: tuple[str, ...] = ("sandbox", "shared"),
    ) -> List[str]:
        normalized_task = self._normalize_task(task)
        return self.path_manager.resolve_read_candidates(
            relative_path,
            task=normalized_task,
            prefer_scopes=prefer_scopes,
        )

    def resolve_file_path(
        self,
        relative_path: str,
        task: Optional[Dict[str, Any]] = None,
        for_read: bool = False,
    ) -> str:
        if for_read:
            return self.resolve_read_path(relative_path=relative_path, task=task)
        return self.resolve_write_path(relative_path=relative_path, task=task)

    def _resolve_base_dir_for_file(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]] = None,
    ) -> str:
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
            for key in ("task_dir", "cwd", "workspace"):
                value = step.get(key)
                if isinstance(value, str) and value.strip():
                    return value

        if isinstance(task, dict):
            try:
                normalized_task = self._normalize_task(task)
            except Exception:
                normalized_task = copy.deepcopy(task)
            return self.path_manager.resolve_command_cwd(
                task=normalized_task,
                prefer_workspace_root=False,
            )

        if isinstance(context, dict):
            for key in ("task_dir", "cwd", "workspace"):
                value = context.get(key)
                if isinstance(value, str) and value.strip():
                    return value

        return self.workspace_root

    def _normalize_task(self, task: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(task, dict):
            return task
        try:
            return self.path_manager.enrich_task(task)
        except Exception:
            return copy.deepcopy(task)

    def _merge_execution_context(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        step_index: Optional[int],
        step_count: Optional[int],
    ) -> Dict[str, Any]:
        merged = copy.deepcopy(step or {})

        if isinstance(task, dict):
            for key in (
                "task_id",
                "task_name",
                "task_dir",
                "sandbox_dir",
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
                if key not in merged and key in task:
                    merged[key] = task.get(key)

        if isinstance(context, dict):
            for key in ("workspace", "cwd", "task_dir", "sandbox_dir"):
                if key not in merged and key in context:
                    merged[key] = context.get(key)

        if step_index is not None and "step_index" not in merged:
            merged["step_index"] = step_index

        if step_count is not None and "step_count" not in merged:
            merged["step_count"] = step_count

        return merged

    def _normalize_step_result(
        self,
        raw_result: Any,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if isinstance(raw_result, dict):
            inner_result = copy.deepcopy(raw_result)
        else:
            inner_result = {"result": raw_result}

        ok = self._extract_inner_ok(inner_result)
        step_type = str(step.get("type", "")).strip().lower()

        if ok:
            return {
                "ok": True,
                "step_type": step_type,
                "step_index": step.get("step_index"),
                "step_count": step.get("step_count"),
                "task_id": self._extract_task_id(task),
                "step": copy.deepcopy(step),
                "result": inner_result,
                "error": None,
            }

        error_payload = self._extract_error_payload(inner_result)
        return {
            "ok": False,
            "step_type": step_type,
            "step_index": step.get("step_index"),
            "step_count": step.get("step_count"),
            "task_id": self._extract_task_id(task),
            "step": copy.deepcopy(step),
            "result": inner_result,
            "error": error_payload,
        }

    def _error_step_result(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        error_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        step_type = str(step.get("type", "")).strip().lower()
        return {
            "ok": False,
            "step_type": step_type,
            "step_index": step.get("step_index"),
            "step_count": step.get("step_count"),
            "task_id": self._extract_task_id(task),
            "step": copy.deepcopy(step),
            "result": {},
            "error": {
                "type": error_type,
                "message": message,
                "retryable": False,
                "details": details or {},
            },
        }

    def _extract_error_payload(self, result: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(result.get("error"), dict):
            error_dict = copy.deepcopy(result["error"])
            if "type" not in error_dict:
                error_dict["type"] = "step_error"
            if "message" not in error_dict:
                error_dict["message"] = str(error_dict)
            if "retryable" not in error_dict:
                error_dict["retryable"] = False
            return error_dict

        if isinstance(result.get("error"), str) and result.get("error"):
            return {
                "type": "step_error",
                "message": str(result.get("error")),
                "retryable": False,
                "details": {},
            }

        if "message" in result and isinstance(result.get("message"), str):
            return {
                "type": "step_error",
                "message": str(result.get("message")),
                "retryable": False,
                "details": {},
            }

        return {
            "type": "step_error",
            "message": "step failed",
            "retryable": False,
            "details": {},
        }

    def _extract_task_id(self, task: Optional[Dict[str, Any]]) -> Optional[str]:
        if not isinstance(task, dict):
            return None
        value = str(
            task.get("task_id")
            or task.get("task_name")
            or task.get("id")
            or ""
        ).strip()
        return value or None

    def _extract_inner_ok(self, result: Any) -> bool:
        if not isinstance(result, dict):
            return True

        if "ok" in result:
            return bool(result.get("ok"))

        if "success" in result:
            return bool(result.get("success"))

        if "output" in result and isinstance(result.get("output"), dict):
            output = result.get("output")
            if "ok" in output:
                return bool(output.get("ok"))
            if "success" in output:
                return bool(output.get("success"))

        if "returncode" in result:
            try:
                return int(result.get("returncode", 1)) == 0
            except Exception:
                return False

        return True