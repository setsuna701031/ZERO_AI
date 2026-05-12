from __future__ import annotations

import copy
import hashlib
import json
import os
import py_compile
import re
import shutil
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional

from core.tasks.task_paths import TaskPathManager
from core.runtime.step_handlers import (
    ToolStepHandler,
    CommandStepHandler,
    WriteFileStepHandler,
    ReadFileStepHandler,
    RespondStepHandler,
    EnsureFileStepHandler,
    VerifyStepHandler,
    RunPythonStepHandler,
)

StepHandler = Callable[[Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Any], Dict[str, Any]]


class StepExecutor:
    """
    ZERO Step Executor

    本版重點：
    1. step handler 輸出統一 envelope
    2. unsupported / exception 錯誤格式統一
    3. execute_steps 批次結果格式統一
    4. 與目前 tool registry 的 outer/inner ok 結構對齊
    5. 直接在 StepExecutor 內接管 llm / llm_generate，修正 document flow 的 {{file_content}} 注入
    6. 補 execution contract 收束：message / final_answer / normalized payload
    7. 保留既有 batch summary contract：failed_step / completed_steps 維持舊測試語意
    8. 新增最小可用 retry：僅在 StepExecutor.execute_step 統一重試，避免責任散落
    9. 錯誤分類改為看整個 failed result（error + stderr + stdout + returncode）
    10. command_failed 分流：
        - fatal -> 1 次
        - generic -> 2 次
        - transient -> 依設定次數
    11. execution_trace 由 StepExecutor 統一產生，作為正式 trace source
    12. command cwd policy 收束：
        - 預設 command 在 project root 執行
        - 僅 command_cwd / cwd_override / run_in_task_dir=True 才覆蓋
        - 一般 task/context 注入進來的 cwd 不算 explicit command cwd
    13. command result contract 收束：
        - 原始 step 保持原樣，不再把誤導性的 cwd 混進 step record
        - 真正執行 cwd 統一寫到 result.effective_cwd 與 result.result.cwd
    14. command stdout/result normalization：
        - 保留完整 stdout / stderr
        - 補 output_text / parsed_output
    15. command message/final_answer summarization：
        - message / final_answer 不再塞整包 JSON
        - 改為短摘要
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
        self.register_handler("append_file", self._handle_append_file_step)
        self.register_handler("workspace_append", self._handle_append_file_step)
        self.register_handler("read_file", ReadFileStepHandler(self).handle)
        self.register_handler("workspace_read", ReadFileStepHandler(self).handle)
        self.register_handler("ensure_file", EnsureFileStepHandler(self).handle)
        self.register_handler("verify", VerifyStepHandler(self).handle)
        self.register_handler("verify_file", VerifyStepHandler(self).handle)
        self.register_handler("verify_python_syntax", self._handle_verify_python_syntax_step)
        self.register_handler("python_syntax_check", self._handle_verify_python_syntax_step)
        self.register_handler("verify_unified_diff", self._handle_verify_unified_diff_step)
        self.register_handler("verify_patch", self._handle_verify_unified_diff_step)
        self.register_handler("apply_unified_diff", self._handle_apply_unified_diff_step)
        self.register_handler("apply_patch", self._handle_apply_unified_diff_step)
        self.register_handler("respond", RespondStepHandler(self).handle)
        self.register_handler("final_answer", RespondStepHandler(self).handle)

        self.register_handler("llm", self._handle_llm_step)
        self.register_handler("llm_generate", self._handle_llm_step)

    def register_handlers(self, handlers: Dict[str, StepHandler]) -> None:
        if not isinstance(handlers, dict):
            raise TypeError("handlers must be a dict")
        for step_type, handler in handlers.items():
            self.register_handler(step_type, handler)

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

        step_payload = self._normalize_step_payload(step_payload)
        step_payload = self._apply_previous_result_substitution(
            step=step_payload,
            previous_result=previous_result,
            context=normalized_context,
        )
        step_type = str(step_payload.get("type", "")).strip().lower()

        if self.debug:
            print(f"[StepExecutor] step_type = {step_type}")

        handler = self.handlers.get(step_type)
        if handler is None:
            result = self._error_step_result(
                step=step_payload,
                task=normalized_task,
                error_type="unsupported_step_type",
                message=f"unsupported step type: {step_type}",
                details={"supported_step_types": self.list_handlers()},
            )
            return self._attach_execution_trace(raw_step, result)

        configured_max_attempts = self._safe_int(
            kwargs.get("max_attempts", step_payload.get("max_attempts", 3)),
            3,
        )
        if configured_max_attempts < 1:
            configured_max_attempts = 1

        attempts: List[Dict[str, Any]] = []
        last_result: Optional[Dict[str, Any]] = None

        for attempt_number in range(1, configured_max_attempts + 1):
            current_step_payload = copy.deepcopy(step_payload)
            current_step_payload["attempt"] = attempt_number
            current_step_payload["max_attempts"] = configured_max_attempts

            if self.debug:
                print(f"[StepExecutor] step_type = {step_type} attempt = {attempt_number}/{configured_max_attempts}")

            try:
                raw_result = handler(current_step_payload, normalized_task, normalized_context, previous_result)
                normalized_result = self._normalize_step_result(
                    raw_result=raw_result,
                    step=current_step_payload,
                    original_step=raw_step,
                    task=normalized_task,
                )
            except Exception as exc:
                normalized_result = self._error_step_result(
                    step=current_step_payload,
                    task=normalized_task,
                    error_type="step_handler_exception",
                    message=str(exc),
                    details={"exception_class": exc.__class__.__name__},
                )
                normalized_result["step"] = copy.deepcopy(raw_step or {})
                normalized_result = self._attach_effective_cwd(
                    step_type=step_type,
                    execution_step=current_step_payload,
                    normalized_result=normalized_result,
                )

            attempts.append(
                {
                    "attempt": attempt_number,
                    "ok": bool(normalized_result.get("ok", False)),
                    "message": normalized_result.get("message"),
                    "error": copy.deepcopy(normalized_result.get("error")),
                }
            )

            if normalized_result.get("ok", False):
                if attempt_number > 1:
                    normalized_result["retry"] = {
                        "used": True,
                        "attempts": attempt_number,
                        "max_attempts": configured_max_attempts,
                        "history": copy.deepcopy(attempts),
                    }
                    if isinstance(normalized_result.get("result"), dict):
                        normalized_result["result"]["retry"] = copy.deepcopy(normalized_result["retry"])

                return self._attach_execution_trace(raw_step, normalized_result)

            last_result = normalized_result

            if attempt_number >= configured_max_attempts:
                break

            effective_max_attempts = self._effective_max_attempts_for_failure(
                failure=normalized_result,
                configured_max_attempts=configured_max_attempts,
            )

            should_retry = (
                attempt_number < effective_max_attempts
                and self._is_retryable_failure(normalized_result)
            )

            if not should_retry:
                break

        retry_result = self._build_retry_step_result(
            failed_result=last_result,
            attempts=attempts,
            max_attempts=configured_max_attempts,
        )
        retry_result["step"] = copy.deepcopy(raw_step or {})
        return self._attach_execution_trace(raw_step, retry_result)

    def execute_steps(
        self,
        steps: List[Dict[str, Any]],
        task: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        previous_result: Any = None
        total_steps = len(steps or [])

        normalized_task = self._normalize_task(task)
        normalized_context = copy.deepcopy(context) if isinstance(context, dict) else {}
        raw_steps = [copy.deepcopy(step or {}) for step in (steps or [])]

        for zero_based_index, original_step in enumerate(raw_steps):
            one_based_index = zero_based_index + 1

            result = self.execute_step(
                step=original_step,
                task=normalized_task,
                context=normalized_context,
                previous_result=previous_result,
                step_index=one_based_index,
                step_count=total_steps,
            )
            results.append(result)
            previous_result = result

            if not result.get("ok", False):
                return {
                    "ok": False,
                    "summary": "step execution failed",
                    "message": self._extract_step_message(result, failed=True),
                    "final_answer": self._extract_step_final_answer(result, failed=True),
                    "step_count": total_steps,
                    "completed_steps": zero_based_index,
                    "failed_step": zero_based_index,
                    "results": results,
                    "last_result": copy.deepcopy(result),
                    "error": copy.deepcopy(result.get("error")),
                    "execution_trace": self._merge_execution_traces(results),
                }

        last_result = copy.deepcopy(results[-1]) if results else None
        return {
            "ok": True,
            "summary": "all steps executed",
            "message": self._extract_step_message(last_result, failed=False) if isinstance(last_result, dict) else "執行完成",
            "final_answer": self._extract_step_final_answer(last_result, failed=False) if isinstance(last_result, dict) else "執行完成",
            "step_count": total_steps,
            "completed_steps": total_steps,
            "failed_step": None,
            "results": results,
            "last_result": last_result,
            "error": None,
            "execution_trace": self._merge_execution_traces(results),
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
        step_type = ""
        if isinstance(step, dict):
            step_type = str(step.get("type") or "").strip().lower()

        if step_type in {"command", "shell", "run_python"}:
            explicit_cwd = self._extract_explicit_command_cwd(step=step, task=task, context=context)
            if explicit_cwd:
                return explicit_cwd
            return self._resolve_project_root_cwd(task=task)

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

    def _extract_explicit_command_cwd(
        self,
        step: Optional[Dict[str, Any]] = None,
        task: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if isinstance(step, dict):
            for key in ("command_cwd", "cwd_override"):
                value = step.get(key)
                if isinstance(value, str) and value.strip():
                    return os.path.abspath(value.strip())

            if bool(step.get("run_in_task_dir")):
                task_dir = self._task_dir_from_any(task, context, step)
                if task_dir:
                    return task_dir

        return ""

    def _resolve_project_root_cwd(
        self,
        task: Optional[Dict[str, Any]] = None,
    ) -> str:
        candidates: List[str] = []

        if isinstance(task, dict):
            workspace_root = task.get("workspace_root")
            if isinstance(workspace_root, str) and workspace_root.strip():
                candidates.append(os.path.abspath(workspace_root.strip()))

            workspace_dir = task.get("workspace_dir")
            if isinstance(workspace_dir, str) and workspace_dir.strip():
                candidates.append(os.path.abspath(workspace_dir.strip()))

        candidates.append(os.path.abspath(self.workspace_root))

        for workspace_candidate in candidates:
            project_root = os.path.abspath(os.path.dirname(workspace_candidate))
            if os.path.isfile(os.path.join(project_root, "app.py")):
                return project_root

        for workspace_candidate in candidates:
            if os.path.isdir(workspace_candidate):
                return workspace_candidate

        return os.path.abspath(os.path.dirname(self.workspace_root))

    def _task_dir_from_any(
        self,
        task: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        step: Optional[Dict[str, Any]] = None,
    ) -> str:
        for payload in (step, task, context):
            if isinstance(payload, dict):
                value = payload.get("task_dir")
                if isinstance(value, str) and value.strip():
                    return os.path.abspath(value.strip())
        return ""

    def _normalize_runtime_mode(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in {"execute", "replay", "audit", "repair_replay"}:
            return text
        return "execute"

    def _extract_runtime_mode_from_mapping(self, value: Any) -> str:
        if not isinstance(value, dict):
            return ""
        for key in ("runtime_mode", "mode", "execution_mode"):
            raw = value.get(key)
            if raw is not None and str(raw).strip():
                return self._normalize_runtime_mode(raw)
        runtime_context = value.get("runtime_context")
        if isinstance(runtime_context, dict):
            for key in ("runtime_mode", "mode", "execution_mode"):
                raw = runtime_context.get(key)
                if raw is not None and str(raw).strip():
                    return self._normalize_runtime_mode(raw)
        return ""

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
                "runtime_mode",
            ):
                if key not in merged and key in task:
                    merged[key] = task.get(key)

        if isinstance(context, dict):
            for key in ("workspace", "cwd", "task_dir", "sandbox_dir", "file_content", "runtime_mode"):
                if key not in merged and key in context:
                    merged[key] = context.get(key)

        if "runtime_mode" not in merged or not str(merged.get("runtime_mode") or "").strip():
            runtime_mode = (
                self._extract_runtime_mode_from_mapping(context)
                or self._extract_runtime_mode_from_mapping(task)
                or "execute"
            )
            merged["runtime_mode"] = runtime_mode

        if step_index is not None and "step_index" not in merged:
            merged["step_index"] = step_index

        if step_count is not None and "step_count" not in merged:
            merged["step_count"] = step_count

        return merged

    def _normalize_step_payload(self, step: Dict[str, Any]) -> Dict[str, Any]:
        payload = copy.deepcopy(step or {})

        step_type = str(payload.get("type") or "unknown").strip().lower()
        payload["type"] = step_type
        payload["runtime_mode"] = self._normalize_runtime_mode(payload.get("runtime_mode") or "execute")

        if "step_index" in payload:
            payload["step_index"] = self._safe_int(payload.get("step_index"), payload.get("step_index"))

        if "step_count" in payload:
            payload["step_count"] = self._safe_int(payload.get("step_count"), payload.get("step_count"))

        if step_type in {"read_file", "write_file", "append_file", "workspace_append", "ensure_file", "run_python", "verify", "verify_file", "verify_python_syntax", "python_syntax_check"}:
            payload["path"] = str(payload.get("path") or "")

        if step_type == "command":
            payload["command"] = str(payload.get("command") or "")

        if step_type == "tool":
            payload["tool_name"] = str(payload.get("tool_name") or payload.get("tool") or "")

        if step_type in {"llm", "llm_generate"}:
            payload["prompt"] = str(payload.get("prompt") or "")
            payload["prompt_template"] = str(payload.get("prompt_template") or payload.get("prompt") or "")
            if "mode" in payload and payload["mode"] is not None:
                payload["mode"] = str(payload.get("mode") or "")

        if step_type in {"write_file", "append_file", "workspace_append"}:
            payload["content"] = str(payload.get("content") or "")

        if "scope" in payload and payload["scope"] is not None:
            payload["scope"] = str(payload.get("scope") or "")

        if "attempt" in payload:
            payload["attempt"] = self._safe_int(payload.get("attempt"), payload.get("attempt"))

        if "max_attempts" in payload:
            payload["max_attempts"] = self._safe_int(payload.get("max_attempts"), payload.get("max_attempts"))

        return payload


    def _apply_previous_result_substitution(
        self,
        step: Dict[str, Any],
        previous_result: Any,
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload = copy.deepcopy(step or {})
        step_type = str(payload.get("type") or "").strip().lower()

        if step_type not in {"write_file", "append_file", "workspace_append"}:
            return payload

        raw_content = payload.get("content")
        if not isinstance(raw_content, str) or not raw_content:
            return payload

        previous_text = self._extract_previous_text(previous_result=previous_result, context=context)
        previous_json = self._extract_previous_json_text(previous_result=previous_result)

        replaced = str(raw_content)

        if "{{previous_result_text}}" in replaced:
            replaced = replaced.replace("{{previous_result_text}}", previous_text)

        if "{{previous_result}}" in replaced:
            replacement = previous_text or previous_json
            replaced = replaced.replace("{{previous_result}}", replacement)

        payload["content"] = replaced
        return payload

    def _extract_previous_json_text(self, previous_result: Any) -> str:
        candidate = self._extract_json_like_payload(previous_result)
        if candidate in (None, "", [], {}):
            return ""

        try:
            if isinstance(candidate, str):
                return candidate
            return json.dumps(candidate, ensure_ascii=False, indent=2)
        except Exception:
            return str(candidate)

    def _extract_json_like_payload(self, payload: Any, depth: int = 0) -> Any:
        if depth > 8 or payload is None:
            return None

        if isinstance(payload, (dict, list)):
            if isinstance(payload, dict):
                for key in ("parsed_output", "result", "output", "data", "raw", "payload"):
                    if key in payload:
                        nested = self._extract_json_like_payload(payload.get(key), depth + 1)
                        if nested not in (None, "", [], {}):
                            return nested
                return payload
            return payload

        return None

    def _normalize_step_result(
        self,
        raw_result: Any,
        step: Dict[str, Any],
        original_step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if isinstance(raw_result, dict):
            inner_result = copy.deepcopy(raw_result)
        else:
            inner_result = {"result": raw_result}

        step_type = str(step.get("type", "")).strip().lower()
        runtime_mode = self._normalize_runtime_mode(step.get("runtime_mode") or "execute")

        if step_type in {"command", "shell", "run_python"}:
            inner_result = self._normalize_command_inner_result(inner_result)

        ok = self._extract_inner_ok(inner_result)
        task_id = self._extract_task_id(task)
        message = self._extract_message_from_inner_result(inner_result, step_type=step_type, ok=ok)
        final_answer = self._extract_final_answer_from_inner_result(inner_result, step_type=step_type, ok=ok)

        if ok:
            normalized = {
                "ok": True,
                "step_type": step_type,
                "step_index": step.get("step_index"),
                "step_count": step.get("step_count"),
                "task_id": task_id,
                "runtime_mode": runtime_mode,
                "step": copy.deepcopy(original_step or {}),
                "result": inner_result,
                "message": message,
                "final_answer": final_answer,
                "error": None,
            }
            return self._attach_effective_cwd(
                step_type=step_type,
                execution_step=step,
                normalized_result=normalized,
            )

        error_payload = self._extract_error_payload(inner_result)
        if not error_payload.get("message") and message:
            error_payload["message"] = message

        normalized = {
            "ok": False,
            "step_type": step_type,
            "step_index": step.get("step_index"),
            "step_count": step.get("step_count"),
            "task_id": task_id,
            "runtime_mode": runtime_mode,
            "step": copy.deepcopy(original_step or {}),
            "result": inner_result,
            "message": message or error_payload.get("message") or "step failed",
            "final_answer": final_answer or error_payload.get("message") or "step failed",
            "error": error_payload,
        }
        return self._attach_effective_cwd(
            step_type=step_type,
            execution_step=step,
            normalized_result=normalized,
        )

    def _normalize_command_inner_result(self, inner_result: Dict[str, Any]) -> Dict[str, Any]:
        normalized = copy.deepcopy(inner_result)

        nested_result = normalized.get("result")
        if not isinstance(nested_result, dict):
            return normalized

        stdout = nested_result.get("stdout")
        stderr = nested_result.get("stderr")

        stdout_text = stdout if isinstance(stdout, str) else ""
        stderr_text = stderr if isinstance(stderr, str) else ""

        preferred_text = stdout_text.strip() or stderr_text.strip() or ""
        parsed_output = self._parse_command_output(preferred_text)

        output_text = preferred_text
        if isinstance(parsed_output, (dict, list)):
            pretty = self._safe_json_dumps(parsed_output)
            if pretty:
                output_text = pretty

        summary_text = self._summarize_command_output(
            parsed_output=parsed_output,
            output_text=output_text,
            ok=bool(normalized.get("ok", False)),
        )

        nested_result["output_text"] = output_text
        nested_result["parsed_output"] = copy.deepcopy(parsed_output)
        nested_result["summary_text"] = summary_text

        normalized["output_text"] = output_text
        normalized["parsed_output"] = copy.deepcopy(parsed_output)
        normalized["summary_text"] = summary_text

        if normalized.get("ok"):
            normalized["message"] = summary_text
            normalized["final_answer"] = summary_text

        return normalized

    def _summarize_command_output(
        self,
        parsed_output: Any,
        output_text: str,
        ok: bool,
    ) -> str:
        if isinstance(parsed_output, dict):
            parts: List[str] = []

            if "ok" in parsed_output:
                parts.append("ok" if bool(parsed_output.get("ok")) else "failed")

            if "mode" in parsed_output and isinstance(parsed_output.get("mode"), str):
                parts.append(f"mode={parsed_output.get('mode')}")

            if "count" in parsed_output:
                parts.append(f"count={parsed_output.get('count')}")

            if "results" in parsed_output and isinstance(parsed_output.get("results"), list):
                parts.append(f"results={len(parsed_output.get('results', []))}")

            if "executed_count" in parsed_output:
                parts.append(f"executed={parsed_output.get('executed_count')}")

            if parts:
                return "command executed successfully: " + ", ".join(parts)

            return "command executed successfully" if ok else "command failed"

        compact = str(output_text or "").strip().replace("\r", " ").replace("\n", " ")
        if len(compact) > 160:
            compact = compact[:157] + "..."

        if compact:
            return compact

        return "command executed successfully" if ok else "command failed"

    def _parse_command_output(self, text: str) -> Any:
        raw = str(text or "").strip()
        if not raw:
            return None

        try:
            return json.loads(raw)
        except Exception:
            return raw

    def _safe_json_dumps(self, value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return ""

    def _attach_effective_cwd(
        self,
        step_type: str,
        execution_step: Dict[str, Any],
        normalized_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        if step_type not in {"command", "shell", "run_python"}:
            return normalized_result

        effective_cwd = self._resolve_effective_cwd_from_result(
            normalized_result=normalized_result,
            execution_step=execution_step,
        )

        if not effective_cwd:
            return normalized_result

        normalized = copy.deepcopy(normalized_result)
        normalized["effective_cwd"] = effective_cwd

        result_payload = normalized.get("result")
        if isinstance(result_payload, dict):
            result_payload["effective_cwd"] = effective_cwd

            nested_result = result_payload.get("result")
            if isinstance(nested_result, dict):
                nested_result["cwd"] = effective_cwd

        return normalized

    def _resolve_effective_cwd_from_result(
        self,
        normalized_result: Dict[str, Any],
        execution_step: Dict[str, Any],
    ) -> str:
        result_payload = normalized_result.get("result")
        if isinstance(result_payload, dict):
            nested_result = result_payload.get("result")
            if isinstance(nested_result, dict):
                cwd = nested_result.get("cwd")
                if isinstance(cwd, str) and cwd.strip():
                    return cwd.strip()

        cwd = execution_step.get("effective_cwd")
        if isinstance(cwd, str) and cwd.strip():
            return cwd.strip()

        cwd = execution_step.get("command_cwd")
        if isinstance(cwd, str) and cwd.strip():
            return os.path.abspath(cwd.strip())

        return ""

    def _error_step_result(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        error_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        step_type = str(step.get("type", "")).strip().lower()
        runtime_mode = self._normalize_runtime_mode(step.get("runtime_mode") or "execute")
        return {
            "ok": False,
            "step_type": step_type,
            "runtime_mode": runtime_mode,
            "step_index": step.get("step_index"),
            "step_count": step.get("step_count"),
            "task_id": self._extract_task_id(task),
            "step": {},
            "result": {},
            "message": message,
            "final_answer": message,
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
            if "details" not in error_dict or not isinstance(error_dict.get("details"), dict):
                error_dict["details"] = {}
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

    def _extract_message_from_inner_result(
        self,
        result: Dict[str, Any],
        step_type: str,
        ok: bool,
    ) -> str:
        if not ok:
            error = result.get("error")
            if isinstance(error, dict):
                msg = error.get("message")
                if isinstance(msg, str) and msg.strip():
                    return msg.strip()
            if isinstance(error, str) and error.strip():
                return error.strip()

            nested_result = result.get("result")
            if isinstance(nested_result, dict):
                nested_error = nested_result.get("error")
                if isinstance(nested_error, dict):
                    msg = nested_error.get("message")
                    if isinstance(msg, str) and msg.strip():
                        return msg.strip()
                if isinstance(nested_error, str) and nested_error.strip():
                    return nested_error.strip()

            for key in ("message", "summary_text", "output_text", "stderr", "stdout"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

            if isinstance(nested_result, dict):
                for key in ("message", "summary_text", "output_text", "stderr", "stdout"):
                    value = nested_result.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()

            return "step failed"

        for key in ("message", "summary_text", "content", "text", "response", "answer", "final_answer", "output_text"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        nested_result = result.get("result")
        if isinstance(nested_result, dict):
            for key in ("message", "summary_text", "content", "text", "response", "answer", "final_answer", "output_text"):
                value = nested_result.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        if step_type == "write_file":
            path = str(result.get("path") or "").strip()
            return f"已寫入檔案：{path}" if path else "已寫入檔案"

        if step_type in {"append_file", "workspace_append"}:
            path = str(result.get("path") or "").strip()
            return f"已追加檔案：{path}" if path else "已追加檔案"

        if step_type == "read_file":
            path = str(result.get("path") or "").strip()
            return f"已讀取檔案：{path}" if path else "已讀取檔案"

        if step_type in {"verify", "verify_file"}:
            return "verify ok"

        if step_type in {"verify_python_syntax", "python_syntax_check"}:
            path = str(result.get("path") or "").strip()
            return f"python syntax ok: {path}" if path else "python syntax ok"

        if step_type == "command":
            return "command executed successfully"

        if step_type in {"llm", "llm_generate"}:
            return "LLM 已完成回應"

        return "執行完成"

    def _extract_final_answer_from_inner_result(
        self,
        result: Dict[str, Any],
        step_type: str,
        ok: bool,
    ) -> str:
        if not ok:
            return self._extract_message_from_inner_result(result=result, step_type=step_type, ok=ok)

        for key in ("final_answer", "summary_text", "answer", "response", "message", "content", "text", "output_text"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        nested_result = result.get("result")
        if isinstance(nested_result, dict):
            for key in ("final_answer", "summary_text", "answer", "response", "message", "content", "text", "output_text"):
                value = nested_result.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return self._extract_message_from_inner_result(result=result, step_type=step_type, ok=ok)

    def _extract_step_message(self, result: Any, failed: bool) -> str:
        if not isinstance(result, dict):
            return "執行失敗" if failed else "執行完成"

        value = result.get("message")
        if isinstance(value, str) and value.strip():
            return value.strip()

        error = result.get("error")
        if failed and isinstance(error, dict):
            msg = error.get("message")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()

        return "執行失敗" if failed else "執行完成"

    def _extract_step_final_answer(self, result: Any, failed: bool) -> str:
        if not isinstance(result, dict):
            return "執行失敗" if failed else "執行完成"

        value = result.get("final_answer")
        if isinstance(value, str) and value.strip():
            return value.strip()

        return self._extract_step_message(result, failed=failed)

    def _failure_text_blob(self, failure: Any) -> str:
        parts: List[str] = []

        if isinstance(failure, dict):
            error = failure.get("error")
            if isinstance(error, dict):
                error_message = error.get("message")
                if isinstance(error_message, str) and error_message.strip():
                    parts.append(error_message)

            result_payload = failure.get("result")
            if isinstance(result_payload, dict):
                for key in ("stderr", "stdout", "message", "content", "text", "output_text", "summary_text"):
                    value = result_payload.get(key)
                    if isinstance(value, str) and value.strip():
                        parts.append(value)

                nested_result = result_payload.get("result")
                if isinstance(nested_result, dict):
                    for key in ("stderr", "stdout", "message", "content", "text", "output_text", "summary_text"):
                        value = nested_result.get(key)
                        if isinstance(value, str) and value.strip():
                            parts.append(value)

        return "\n".join(parts).lower()

    def _classify_failure(self, failure: Any) -> str:
        if not isinstance(failure, dict):
            return "fatal"

        error = failure.get("error")
        error_type = ""
        if isinstance(error, dict):
            error_type = str(error.get("type") or "").strip().lower()

        text_blob = self._failure_text_blob(failure)

        fatal_types = {
            "unsupported_step_type",
            "guard_blocked",
            "guard_violation",
            "guard_safety",
            "validation_error",
            "schema_error",
            "policy_blocked",
            "permission_denied",
        }
        if error_type in fatal_types:
            return "fatal"

        transient_types = {
            "step_handler_exception",
            "timeout",
            "tool_timeout",
            "command_timeout",
            "transient_error",
            "temporary_error",
            "rate_limit",
            "resource_busy",
        }
        if error_type in transient_types:
            return "transient"

        transient_keywords = (
            "timeout",
            "timed out",
            "temporarily unavailable",
            "temporary failure",
            "rate limit",
            "busy",
            "connection reset",
            "connection aborted",
            "connection refused",
            "try again",
        )

        fatal_command_keywords = (
            "not found",
            "no such file",
            "is not recognized",
            "syntaxerror",
            "invalid syntax",
            "module not found",
            "modulenotfounderror",
            "permission denied",
            "access is denied",
            "nameerror",
            "attributeerror",
            "typeerror",
            "valueerror",
        )

        if error_type == "command_failed":
            if any(keyword in text_blob for keyword in transient_keywords):
                return "transient"
            if any(keyword in text_blob for keyword in fatal_command_keywords):
                return "fatal"
            return "generic_command_failure"

        if any(keyword in text_blob for keyword in transient_keywords):
            return "transient"

        return "fatal"

    def _is_retryable_failure(self, failure: Any) -> bool:
        classification = self._classify_failure(failure)
        return classification in {"transient", "generic_command_failure"}

    def _effective_max_attempts_for_failure(
        self,
        failure: Any,
        configured_max_attempts: int,
    ) -> int:
        classification = self._classify_failure(failure)

        if classification == "fatal":
            return 1

        if classification == "generic_command_failure":
            return min(configured_max_attempts, 2)

        return configured_max_attempts

    def _build_retry_step_result(
        self,
        failed_result: Optional[Dict[str, Any]],
        attempts: List[Dict[str, Any]],
        max_attempts: int,
    ) -> Dict[str, Any]:
        if not isinstance(failed_result, dict):
            return {
                "ok": False,
                "step_type": "",
                "step_index": None,
                "step_count": None,
                "task_id": None,
                "step": {},
                "result": {},
                "message": "step failed",
                "final_answer": "step failed",
                "error": {
                    "type": "retry_exhausted",
                    "message": "step failed after retry attempts",
                    "retryable": False,
                    "details": {
                        "attempts": copy.deepcopy(attempts),
                        "max_attempts": max_attempts,
                    },
                },
                "retry": {
                    "used": max_attempts > 1,
                    "attempts": len(attempts),
                    "max_attempts": max_attempts,
                    "history": copy.deepcopy(attempts),
                },
            }

        result = copy.deepcopy(failed_result)

        retry_payload = {
            "used": len(attempts) > 1,
            "attempts": len(attempts),
            "max_attempts": max_attempts,
            "history": copy.deepcopy(attempts),
        }
        result["retry"] = retry_payload

        if not isinstance(result.get("error"), dict):
            result["error"] = {
                "type": "retry_exhausted",
                "message": result.get("message") or "step failed after retry attempts",
                "retryable": False,
                "details": {},
            }

        error_payload = result["error"]
        error_payload["retryable"] = False

        details = error_payload.get("details")
        if not isinstance(details, dict):
            details = {}
            error_payload["details"] = details

        details["attempts"] = copy.deepcopy(attempts)
        details["max_attempts"] = max_attempts
        details["classification"] = self._classify_failure(result)

        if len(attempts) >= max_attempts and max_attempts > 1:
            result["message"] = result.get("message") or "step failed after retry attempts"
            result["final_answer"] = result.get("final_answer") or result["message"]

        if isinstance(result.get("result"), dict):
            result["result"]["retry"] = copy.deepcopy(retry_payload)

        return result

    def _handle_verify_python_syntax_step(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        """Compile-check a generated Python file without executing it.

        Code Chain v0.2 safety boundary:
        - This step only validates syntax with py_compile.
        - It does not run the generated program.
        - It only allows workspace/shared or shared .py targets.
        """
        _ = context
        _ = previous_result

        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            return {
                "ok": False,
                "type": "verify_python_syntax",
                "path": raw_path,
                "message": "verify_python_syntax step missing path",
                "final_answer": "verify_python_syntax step missing path",
                "error": {
                    "type": "validation_error",
                    "message": "verify_python_syntax step missing path",
                    "retryable": False,
                },
            }

        normalized_path = raw_path.replace("\\", "/")
        if not normalized_path.endswith(".py"):
            return {
                "ok": False,
                "type": "verify_python_syntax",
                "path": raw_path,
                "message": "verify_python_syntax only supports .py files",
                "final_answer": "verify_python_syntax only supports .py files",
                "error": {
                    "type": "validation_error",
                    "message": "verify_python_syntax only supports .py files",
                    "retryable": False,
                },
            }

        if not (normalized_path.startswith("workspace/shared/") or normalized_path.startswith("shared/")):
            return {
                "ok": False,
                "type": "verify_python_syntax",
                "path": raw_path,
                "message": "verify_python_syntax only allows workspace/shared Python files",
                "final_answer": "verify_python_syntax only allows workspace/shared Python files",
                "error": {
                    "type": "policy_blocked",
                    "message": "verify_python_syntax only allows workspace/shared Python files",
                    "retryable": False,
                },
            }

        try:
            full_path = self.resolve_read_path(
                relative_path=raw_path,
                task=task,
                prefer_scopes=("shared", "sandbox"),
                return_fallback_candidate_if_missing=True,
            )
        except Exception as exc:
            return {
                "ok": False,
                "type": "verify_python_syntax",
                "path": raw_path,
                "message": f"verify_python_syntax path resolve failed: {exc}",
                "final_answer": f"verify_python_syntax path resolve failed: {exc}",
                "error": {
                    "type": "path_resolve_failed",
                    "message": str(exc),
                    "retryable": False,
                },
            }

        if not os.path.exists(full_path):
            return {
                "ok": False,
                "type": "verify_python_syntax",
                "path": raw_path,
                "full_path": full_path,
                "message": f"python syntax target not found: {full_path}",
                "final_answer": f"python syntax target not found: {full_path}",
                "error": {
                    "type": "file_not_found",
                    "message": f"python syntax target not found: {full_path}",
                    "retryable": False,
                },
            }

        try:
            py_compile.compile(full_path, doraise=True)
        except py_compile.PyCompileError as exc:
            message = str(exc)
            return {
                "ok": False,
                "type": "verify_python_syntax",
                "path": raw_path,
                "full_path": full_path,
                "message": f"python syntax failed: {message}",
                "final_answer": f"python syntax failed: {message}",
                "error": {
                    "type": "python_syntax_error",
                    "message": message,
                    "retryable": False,
                },
                "result": {
                    "path": raw_path,
                    "full_path": full_path,
                    "syntax_ok": False,
                    "error": message,
                },
            }
        except Exception as exc:
            message = str(exc)
            return {
                "ok": False,
                "type": "verify_python_syntax",
                "path": raw_path,
                "full_path": full_path,
                "message": f"python syntax check failed: {message}",
                "final_answer": f"python syntax check failed: {message}",
                "error": {
                    "type": "python_syntax_check_failed",
                    "message": message,
                    "retryable": False,
                },
                "result": {
                    "path": raw_path,
                    "full_path": full_path,
                    "syntax_ok": False,
                    "error": message,
                },
            }

        return {
            "ok": True,
            "type": "verify_python_syntax",
            "path": raw_path,
            "full_path": full_path,
            "message": f"python syntax ok: {raw_path}",
            "final_answer": f"python syntax ok: {raw_path}",
            "result": {
                "path": raw_path,
                "full_path": full_path,
                "syntax_ok": True,
            },
            "error": None,
        }


    def _handle_verify_unified_diff_step(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        """Validate that a generated patch looks like a unified diff.

        Code Chain v0.3 safety boundary:
        - This step only validates patch shape.
        - It does not apply the patch.
        - It only allows workspace/shared .patch or .diff targets.
        """
        _ = context
        _ = previous_result

        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            return {
                "ok": False,
                "type": "verify_unified_diff",
                "path": raw_path,
                "message": "verify_unified_diff step missing path",
                "final_answer": "verify_unified_diff step missing path",
                "error": {"type": "validation_error", "message": "verify_unified_diff step missing path", "retryable": False},
            }

        normalized_path = raw_path.replace("\\", "/")
        if not normalized_path.lower().endswith((".patch", ".diff")):
            return {
                "ok": False,
                "type": "verify_unified_diff",
                "path": raw_path,
                "message": "verify_unified_diff only supports .patch or .diff files",
                "final_answer": "verify_unified_diff only supports .patch or .diff files",
                "error": {"type": "validation_error", "message": "verify_unified_diff only supports .patch or .diff files", "retryable": False},
            }

        if not (normalized_path.startswith("workspace/shared/") or normalized_path.startswith("shared/")):
            return {
                "ok": False,
                "type": "verify_unified_diff",
                "path": raw_path,
                "message": "verify_unified_diff only allows workspace/shared patch files",
                "final_answer": "verify_unified_diff only allows workspace/shared patch files",
                "error": {"type": "policy_blocked", "message": "verify_unified_diff only allows workspace/shared patch files", "retryable": False},
            }

        try:
            full_path = self.resolve_read_path(
                relative_path=raw_path,
                task=task,
                prefer_scopes=("shared", "sandbox"),
                return_fallback_candidate_if_missing=True,
            )
        except Exception as exc:
            return {
                "ok": False,
                "type": "verify_unified_diff",
                "path": raw_path,
                "message": f"verify_unified_diff path resolve failed: {exc}",
                "final_answer": f"verify_unified_diff path resolve failed: {exc}",
                "error": {"type": "path_resolve_failed", "message": str(exc), "retryable": False},
            }

        if not os.path.exists(full_path):
            return {
                "ok": False,
                "type": "verify_unified_diff",
                "path": raw_path,
                "full_path": full_path,
                "message": f"unified diff target not found: {full_path}",
                "final_answer": f"unified diff target not found: {full_path}",
                "error": {"type": "file_not_found", "message": f"unified diff target not found: {full_path}", "retryable": False},
            }

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as exc:
            return {
                "ok": False,
                "type": "verify_unified_diff",
                "path": raw_path,
                "full_path": full_path,
                "message": f"verify_unified_diff read failed: {exc}",
                "final_answer": f"verify_unified_diff read failed: {exc}",
                "error": {"type": "read_failed", "message": str(exc), "retryable": False},
            }

        validation = self._validate_unified_diff_text(content)
        if not validation.get("ok"):
            message = str(validation.get("message") or "invalid unified diff")
            return {
                "ok": False,
                "type": "verify_unified_diff",
                "path": raw_path,
                "full_path": full_path,
                "message": message,
                "final_answer": message,
                "error": {"type": "invalid_unified_diff", "message": message, "retryable": False, "details": validation},
                "result": {"path": raw_path, "full_path": full_path, "diff_ok": False, "validation": validation},
            }

        return {
            "ok": True,
            "type": "verify_unified_diff",
            "path": raw_path,
            "full_path": full_path,
            "message": f"unified diff ok: {raw_path}",
            "final_answer": f"unified diff ok: {raw_path}",
            "result": {"path": raw_path, "full_path": full_path, "diff_ok": True, "validation": validation},
            "error": None,
        }

    def _validate_unified_diff_text(self, text: str) -> Dict[str, Any]:
        content = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = content.split("\n")
        nonempty = [line for line in lines if line.strip()]

        if not nonempty:
            return {"ok": False, "message": "unified diff is empty"}

        has_old_header = any(line.startswith("--- ") for line in nonempty)
        has_new_header = any(line.startswith("+++ ") for line in nonempty)
        has_hunk = any(line.startswith("@@ ") and line.rstrip().endswith("@@") for line in nonempty)
        has_added_or_removed = any((line.startswith("+") and not line.startswith("+++")) or (line.startswith("-") and not line.startswith("---")) for line in nonempty)

        if not has_old_header:
            return {"ok": False, "message": "unified diff missing --- header"}
        if not has_new_header:
            return {"ok": False, "message": "unified diff missing +++ header"}
        if not has_hunk:
            return {"ok": False, "message": "unified diff missing @@ hunk"}
        if not has_added_or_removed:
            return {"ok": False, "message": "unified diff has no changed lines"}
        if "```" in content:
            return {"ok": False, "message": "unified diff contains Markdown fences"}

        return {
            "ok": True,
            "message": "unified diff shape accepted",
            "line_count": len(lines),
            "changed_line_count": sum(1 for line in nonempty if (line.startswith("+") and not line.startswith("+++")) or (line.startswith("-") and not line.startswith("---"))),
        }

    def _handle_apply_unified_diff_step(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        """Apply a single-file unified diff inside workspace/shared only.

        Code Chain v0.4 safety boundary:
        - Only .patch/.diff files from workspace/shared are accepted.
        - Only workspace/shared target files are writable.
        - A .bak_v04 backup is written before applying.
        - This handler applies the patch directly; it does not run generated code.
        """
        _ = context
        _ = previous_result

        patch_path = str(step.get("patch_path") or step.get("path") or "").strip()
        target_path = str(step.get("target_path") or step.get("target") or "").strip()
        preflight = self._analyze_apply_patch_preflight(step, task=task)
        transaction = self._build_apply_patch_transaction(preflight, status="planned")
        if not bool(preflight.get("preflight_ok", False)):
            transaction = self._mark_apply_patch_transaction(transaction, status="blocked", error_reason=str(preflight.get("conflict_reason") or "apply_patch preflight failed"))
            return self._apply_patch_error(
                "preflight_failed",
                str(preflight.get("conflict_reason") or "apply_patch preflight failed"),
                patch_path,
                target_path,
                details={"preflight": preflight, "transaction": transaction},
            )

        if not patch_path:
            return self._apply_patch_error("validation_error", "apply_patch step missing patch_path", patch_path, target_path, details={"preflight": preflight, "transaction": transaction})
        if not target_path:
            return self._apply_patch_error("validation_error", "apply_patch step missing target_path", patch_path, target_path, details={"preflight": preflight, "transaction": transaction})

        patch_norm = patch_path.replace("\\", "/")
        target_norm = target_path.replace("\\", "/")
        repo_source_target_allowed = bool(preflight.get("repo_source") and preflight.get("confirmed"))

        if not patch_norm.lower().endswith((".patch", ".diff")):
            return self._apply_patch_error("validation_error", "apply_patch only supports .patch or .diff files", patch_path, target_path, details={"preflight": preflight, "transaction": transaction})

        if not (patch_norm.startswith("workspace/shared/") or patch_norm.startswith("shared/")):
            return self._apply_patch_error("policy_blocked", "apply_patch only allows workspace/shared patch files", patch_path, target_path, details={"preflight": preflight, "transaction": transaction})

        if not repo_source_target_allowed and not (target_norm.startswith("workspace/shared/") or target_norm.startswith("shared/")):
            return self._apply_patch_error("policy_blocked", "apply_patch only allows workspace/shared target files", patch_path, target_path, details={"preflight": preflight, "transaction": transaction})

        try:
            full_patch_path = self.resolve_read_path(
                relative_path=patch_path,
                task=task,
                prefer_scopes=("shared", "sandbox"),
                return_fallback_candidate_if_missing=True,
            )
            if repo_source_target_allowed:
                full_target_path = os.path.abspath(target_path)
            else:
                full_target_path = self.resolve_write_path(
                    relative_path=target_path,
                    task=task,
                    default_scope="shared",
                )
        except Exception as exc:
            return self._apply_patch_error("path_resolve_failed", f"apply_patch path resolve failed: {exc}", patch_path, target_path, details={"preflight": preflight, "transaction": transaction})

        if not os.path.exists(full_patch_path):
            return self._apply_patch_error("file_not_found", f"patch file not found: {full_patch_path}", patch_path, target_path, full_patch_path=full_patch_path, full_target_path=full_target_path, details={"preflight": preflight, "transaction": transaction})
        if not os.path.exists(full_target_path):
            return self._apply_patch_error("file_not_found", f"target file not found: {full_target_path}", patch_path, target_path, full_patch_path=full_patch_path, full_target_path=full_target_path, details={"preflight": preflight, "transaction": transaction})

        try:
            with open(full_patch_path, "r", encoding="utf-8") as f:
                patch_text = f.read()
            with open(full_target_path, "r", encoding="utf-8") as f:
                original_text = f.read()
        except Exception as exc:
            return self._apply_patch_error("read_failed", f"apply_patch read failed: {exc}", patch_path, target_path, full_patch_path=full_patch_path, full_target_path=full_target_path, details={"preflight": preflight, "transaction": transaction})

        backup_path = full_target_path + ".bak_v04"
        try:
            self._create_apply_patch_backup(full_target_path, backup_path)
            transaction = self._attach_apply_patch_backup_snapshot(
                transaction,
                [{"target_path": target_path, "full_target_path": full_target_path, "backup_path": backup_path}],
            )
        except Exception as exc:
            transaction = self._mark_apply_patch_transaction(transaction, status="failed", error_reason=f"apply_patch backup failed: {exc}")
            return self._apply_patch_error("backup_failed", f"apply_patch backup failed: {exc}", patch_path, target_path, full_patch_path=full_patch_path, full_target_path=full_target_path, backup_path=backup_path, details={"preflight": preflight, "transaction": transaction})

        validation = self._validate_unified_diff_text(patch_text)
        if not validation.get("ok"):
            message = str(validation.get("message") or "invalid unified diff")
            transaction = self._mark_apply_patch_transaction(transaction, status="failed", error_reason=message)
            return self._apply_patch_error("invalid_unified_diff", message, patch_path, target_path, full_patch_path=full_patch_path, full_target_path=full_target_path, backup_path=backup_path, details={"preflight": preflight, "transaction": transaction, "validation": validation})

        try:
            patched_text, apply_meta = self._apply_unified_diff_text(original_text, patch_text)
        except Exception as exc:
            transaction = self._mark_apply_patch_transaction(transaction, status="failed", error_reason=f"patch apply failed: {exc}")
            return self._apply_patch_error("patch_apply_failed", f"patch apply failed: {exc}", patch_path, target_path, full_patch_path=full_patch_path, full_target_path=full_target_path, backup_path=backup_path, details={"preflight": preflight, "transaction": transaction})

        if patched_text == original_text:
            transaction = self._mark_apply_patch_transaction(transaction, status="failed", error_reason="patch produced no changes")
            return self._apply_patch_error("patch_no_change", "patch produced no changes", patch_path, target_path, full_patch_path=full_patch_path, full_target_path=full_target_path, backup_path=backup_path, details={"preflight": preflight, "transaction": transaction, "apply_meta": apply_meta})

        try:
            os.makedirs(os.path.dirname(full_target_path), exist_ok=True)
            with open(full_target_path, "w", encoding="utf-8") as f:
                f.write(patched_text)
        except Exception as exc:
            rollback_applied, rollback_error = self._rollback_apply_patch_target(full_target_path, backup_path)
            transaction = self._mark_apply_patch_transaction(transaction, status="failed", error_reason=f"apply_patch write failed: {exc}")
            return self._apply_patch_error(
                "write_failed",
                f"apply_patch write failed: {exc}",
                patch_path,
                target_path,
                full_patch_path=full_patch_path,
                full_target_path=full_target_path,
                backup_path=backup_path,
                rollback_applied=rollback_applied,
                details={"preflight": preflight, "transaction": transaction, "backup_path": backup_path, "rollback_error": rollback_error},
            )

        transaction = self._mark_apply_patch_transaction(transaction, status="applied", changed_files=[target_path])
        transaction = self._mark_apply_patch_transaction(transaction, status="verifying", changed_files=[target_path])
        verification = self._run_apply_patch_verify_boundary(
            step,
            transaction,
            [{"target_path": target_path, "full_target_path": full_target_path, "backup_path": backup_path}],
        )
        transaction = verification.get("transaction") if isinstance(verification.get("transaction"), dict) else transaction
        if not bool(verification.get("ok", False)):
            rollback_applied, rollback_error = self._rollback_apply_patch_target(full_target_path, backup_path)
            message = str(verification.get("message") or "apply_patch verification failed")
            rollback_result = self._build_apply_patch_rollback_result(
                [{"target_path": target_path, "full_target_path": full_target_path, "backup_path": backup_path, "rollback_applied": rollback_applied, "rollback_error": rollback_error}]
            )
            transaction = self._mark_apply_patch_transaction(
                transaction,
                status="failed",
                error_reason=message,
                changed_files=[target_path],
                rollback_result=rollback_result,
            )
            return self._apply_patch_error(
                "verification_failed",
                message,
                patch_path,
                target_path,
                full_patch_path=full_patch_path,
                full_target_path=full_target_path,
                backup_path=backup_path,
                rollback_applied=rollback_applied,
                changed=False,
                verification_ok=False,
                details={"preflight": preflight, "transaction": transaction, "verification": verification, "rollback_result": rollback_result, "rollback_error": rollback_error},
            )

        transaction = self._mark_apply_patch_transaction(transaction, status="committed", changed_files=[target_path])
        return {
            "ok": True,
            "type": "apply_patch",
            "patch_path": patch_path,
            "target_path": target_path,
            "full_patch_path": full_patch_path,
            "full_target_path": full_target_path,
            "backup_path": backup_path,
            "transaction_ok": True,
            "preflight_ok": True,
            "preflight": preflight,
            "transaction": transaction,
            "verification_ok": True,
            "verification": verification,
            "rollback_applied": False,
            "changed": True,
            "message": f"patch applied: {target_path}",
            "final_answer": f"patch applied: {target_path}",
            "result": {
                "patch_path": patch_path,
                "target_path": target_path,
                "full_patch_path": full_patch_path,
                "full_target_path": full_target_path,
                "backup_path": backup_path,
                "transaction_ok": True,
                "preflight_ok": True,
                "preflight": preflight,
                "transaction": transaction,
                "verification_ok": True,
                "verification": verification,
                "rollback_applied": False,
                "changed": True,
                "applied": True,
                "apply_meta": apply_meta,
            },
            "error": None,
        }

    def _apply_patch_error(
        self,
        error_type: str,
        message: str,
        patch_path: str = "",
        target_path: str = "",
        full_patch_path: str = "",
        full_target_path: str = "",
        backup_path: str = "",
        rollback_applied: bool = False,
        changed: bool = False,
        verification_ok: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "ok": False,
            "type": "apply_patch",
            "patch_path": patch_path,
            "target_path": target_path,
            "full_patch_path": full_patch_path,
            "full_target_path": full_target_path,
            "backup_path": backup_path,
            "transaction_ok": False,
            "preflight_ok": bool((details or {}).get("preflight", {}).get("preflight_ok", False)),
            "preflight": copy.deepcopy((details or {}).get("preflight", {})),
            "transaction": copy.deepcopy((details or {}).get("transaction", {})),
            "verification_ok": bool(verification_ok),
            "rollback_applied": bool(rollback_applied),
            "rollback_result": copy.deepcopy((details or {}).get("rollback_result", {})),
            "changed": bool(changed),
            "message": message,
            "final_answer": message,
            "error": {
                "type": error_type,
                "message": message,
                "retryable": False,
                "details": details or {},
            },
            "result": {
                "patch_path": patch_path,
                "target_path": target_path,
                "full_patch_path": full_patch_path,
                "full_target_path": full_target_path,
                "backup_path": backup_path,
                "transaction_ok": False,
                "preflight_ok": bool((details or {}).get("preflight", {}).get("preflight_ok", False)),
                "preflight": copy.deepcopy((details or {}).get("preflight", {})),
                "transaction": copy.deepcopy((details or {}).get("transaction", {})),
                "verification_ok": bool(verification_ok),
                "verification": copy.deepcopy((details or {}).get("verification", {})),
                "rollback_applied": bool(rollback_applied),
                "rollback_result": copy.deepcopy((details or {}).get("rollback_result", {})),
                "changed": bool(changed),
                "applied": False,
            },
        }

    def _create_apply_patch_backup(self, full_target_path: str, backup_path: str) -> str:
        if not full_target_path or not backup_path:
            raise ValueError("backup requires target and backup path")
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copyfile(full_target_path, backup_path)
        return backup_path

    def _rollback_apply_patch_target(self, full_target_path: str, backup_path: str) -> Tuple[bool, str]:
        if not full_target_path or not backup_path or not os.path.exists(backup_path):
            return False, ""
        try:
            shutil.copyfile(backup_path, full_target_path)
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def _analyze_apply_patch_preflight(self, step: Dict[str, Any], task: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        step = step if isinstance(step, dict) else {}
        patches_value = step.get("patches")
        patch_items: List[Dict[str, Any]] = []
        conflict_reasons: List[str] = []

        if isinstance(patches_value, list):
            if not patches_value:
                conflict_reasons.append("empty patch list")
            for item in patches_value:
                patch_items.append(item if isinstance(item, dict) else {})
        else:
            patch_items.append(step)

        patch_files: List[str] = []
        target_files: List[str] = []
        full_patch_files: List[str] = []
        full_target_files: List[str] = []

        for index, item in enumerate(patch_items):
            patch_path = str(item.get("patch_path") or item.get("path") or "").strip()
            target_path = str(item.get("target_path") or item.get("target") or "").strip()
            patch_norm = patch_path.replace("\\", "/").lstrip("./")
            target_norm = target_path.replace("\\", "/").lstrip("./")

            if not patch_norm:
                conflict_reasons.append(f"patch[{index}] missing patch_path")
            else:
                patch_files.append(patch_norm)
                if not patch_norm.lower().endswith((".patch", ".diff")):
                    conflict_reasons.append(f"patch[{index}] invalid patch extension: {patch_norm}")
                try:
                    full_patch_path = self.resolve_read_path(
                        relative_path=patch_path,
                        task=task,
                        prefer_scopes=("shared", "sandbox"),
                        return_fallback_candidate_if_missing=True,
                    )
                except Exception as exc:
                    full_patch_path = ""
                    conflict_reasons.append(f"patch[{index}] patch path resolve failed: {exc}")
                if full_patch_path:
                    full_patch_files.append(full_patch_path)
                    if not os.path.exists(full_patch_path):
                        conflict_reasons.append(f"patch[{index}] patch file missing: {patch_norm}")

            if not target_norm:
                conflict_reasons.append(f"patch[{index}] missing target_path")
            else:
                target_files.append(target_norm)
                full_target_path = ""
                try:
                    if self._is_repo_source_patch_path(target_norm):
                        full_target_path = os.path.abspath(target_norm)
                    else:
                        full_target_path = self.resolve_write_path(
                            relative_path=target_path,
                            task=task,
                            default_scope="shared",
                        )
                except Exception as exc:
                    conflict_reasons.append(f"patch[{index}] target path resolve failed: {exc}")
                if full_target_path:
                    full_target_files.append(full_target_path)
                    if not os.path.exists(full_target_path):
                        conflict_reasons.append(f"patch[{index}] target file missing: {target_norm}")

        duplicate_targets = sorted({path for path in target_files if target_files.count(path) > 1})
        if duplicate_targets:
            conflict_reasons.append("duplicate target path in same transaction: " + ", ".join(duplicate_targets))

        changed_files = list(dict.fromkeys(target_files))
        repo_source_files = [path for path in changed_files if self._is_repo_source_patch_path(path)]
        repo_source = bool(repo_source_files)
        edit_scope = "single_file"
        if len(changed_files) > 1:
            edit_scope = "repo_scale" if repo_source else "multi_file"

        sensitive_tokens = ("scheduler", "execution_guard", "step_executor", "task_runner", "task_runtime")
        sensitive = any(token in path.lower() for path in changed_files for token in sensitive_tokens)
        risk_level = "low"
        if repo_source:
            risk_level = "medium"
        if repo_source and (len(changed_files) > 1 or sensitive):
            risk_level = "high"

        requires_confirmation = bool(repo_source)
        confirmed = bool(step.get("confirmed") or step.get("confirmation") or step.get("repo_scale_confirmed") or step.get("scope_confirmed"))
        if requires_confirmation and not confirmed:
            conflict_reasons.append("repo source apply requires confirmation")

        conflict_reasons = list(dict.fromkeys(reason for reason in conflict_reasons if str(reason).strip()))
        conflict_detected = bool(conflict_reasons)
        return {
            "preflight_ok": not conflict_detected,
            "target_files": changed_files,
            "patch_files": list(dict.fromkeys(patch_files)),
            "changed_files": changed_files,
            "full_target_files": full_target_files,
            "full_patch_files": full_patch_files,
            "repo_source": repo_source,
            "repo_source_files": repo_source_files,
            "edit_scope": edit_scope,
            "risk_level": risk_level,
            "requires_confirmation": requires_confirmation,
            "confirmed": confirmed,
            "conflict_detected": conflict_detected,
            "conflict_reason": "; ".join(conflict_reasons),
        }

    def _is_repo_source_patch_path(self, path_text: str) -> bool:
        lowered = str(path_text or "").replace("\\", "/").lstrip("./").lower()
        return lowered.startswith(("core/", "services/", "tests/", "runtime/", "tasks/", "planning/"))

    def _build_apply_patch_transaction(self, preflight: Dict[str, Any], status: str = "planned", error_reason: str = "") -> Dict[str, Any]:
        preflight = preflight if isinstance(preflight, dict) else {}
        target_files = [str(item) for item in preflight.get("target_files", []) if str(item).strip()]
        patch_files = [str(item) for item in preflight.get("patch_files", []) if str(item).strip()]
        seed = json.dumps(
            {
                "target_files": target_files,
                "patch_files": patch_files,
                "repo_source": bool(preflight.get("repo_source", False)),
                "edit_scope": str(preflight.get("edit_scope") or ""),
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        created_at = str(int(time.time() * 1000))
        transaction_id = f"patch_tx:{created_at}:{digest}"
        return {
            "transaction_id": transaction_id,
            "transaction_scope": str(preflight.get("edit_scope") or "single_file"),
            "transaction_files": target_files,
            "backup_files": [],
            "backup_snapshot": {},
            "preflight_ok": bool(preflight.get("preflight_ok", False)),
            "risk_level": str(preflight.get("risk_level") or "low"),
            "requires_confirmation": bool(preflight.get("requires_confirmation", False)),
            "repo_source": bool(preflight.get("repo_source", False)),
            "edit_scope": str(preflight.get("edit_scope") or "single_file"),
            "status": str(status or "planned"),
            "error_reason": str(error_reason or ""),
            "patch_files": patch_files,
            "created_at_ms": created_at,
            "content_hash": digest,
        }

    def _attach_apply_patch_backup_snapshot(self, transaction: Dict[str, Any], backups: List[Dict[str, Any]]) -> Dict[str, Any]:
        updated = copy.deepcopy(transaction if isinstance(transaction, dict) else {})
        snapshot = updated.get("backup_snapshot") if isinstance(updated.get("backup_snapshot"), dict) else {}
        backup_files = updated.get("backup_files") if isinstance(updated.get("backup_files"), list) else []
        for item in backups or []:
            if not isinstance(item, dict):
                continue
            target_path = str(item.get("target_path") or item.get("full_target_path") or "").strip()
            backup_path = str(item.get("backup_path") or "").strip()
            full_target_path = str(item.get("full_target_path") or "").strip()
            if backup_path:
                backup_files.append(backup_path)
            if target_path:
                snapshot[target_path] = {
                    "target_path": target_path,
                    "full_target_path": full_target_path,
                    "backup_path": backup_path,
                }
        updated["backup_files"] = list(dict.fromkeys(backup_files))
        updated["backup_snapshot"] = snapshot
        return updated

    def _mark_apply_patch_transaction(
        self,
        transaction: Dict[str, Any],
        status: str,
        error_reason: str = "",
        changed_files: Optional[List[str]] = None,
        rollback_result: Optional[Dict[str, Any]] = None,
        verify_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        updated = copy.deepcopy(transaction if isinstance(transaction, dict) else {})
        previous_status = str(updated.get("status") or "")
        updated["status"] = str(status or updated.get("status") or "")
        updated["error_reason"] = str(error_reason or "")
        if changed_files is not None:
            updated["changed_files"] = list(dict.fromkeys(str(item) for item in changed_files if str(item).strip()))
        if rollback_result is not None:
            updated["rollback_result"] = copy.deepcopy(rollback_result)
            updated["rollback_error"] = str(rollback_result.get("rollback_error") or "")
        if verify_metadata is not None:
            updated.update(copy.deepcopy(verify_metadata))
        history = updated.get("status_history") if isinstance(updated.get("status_history"), list) else []
        if not history or previous_status != updated["status"]:
            history.append({"status": updated["status"], "ts_ms": str(int(time.time() * 1000))})
        updated["status_history"] = history[-20:]
        return updated

    def _run_apply_patch_verify_boundary(
        self,
        step: Dict[str, Any],
        transaction: Dict[str, Any],
        changed_items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        verify_started_at = str(int(time.time() * 1000))
        checks: List[str] = []
        errors: List[str] = []
        step = step if isinstance(step, dict) else {}

        def add_error(message: str) -> None:
            if message:
                errors.append(str(message))

        checks.append("changed_files_exists")
        if not changed_items:
            add_error("changed_files is empty")

        for item in changed_items or []:
            full_target_path = str(item.get("full_target_path") or "")
            backup_path = str(item.get("backup_path") or "")
            target_path = str(item.get("target_path") or full_target_path)

            checks.append("file_exists")
            if not full_target_path or not os.path.exists(full_target_path):
                add_error(f"target file missing after apply: {target_path}")
                continue

            checks.append("file_content_changed")
            if backup_path and os.path.exists(backup_path):
                try:
                    with open(full_target_path, "r", encoding="utf-8") as target_fh:
                        current_text = target_fh.read()
                    with open(backup_path, "r", encoding="utf-8") as backup_fh:
                        backup_text = backup_fh.read()
                    if current_text == backup_text:
                        add_error(f"file content did not change: {target_path}")
                except Exception as exc:
                    add_error(f"file content changed check failed for {target_path}: {exc}")

            legacy_verify = self._verify_apply_patch_target(step, full_target_path)
            checks.extend(str(check) for check in legacy_verify.get("checks", []) if str(check))
            if not bool(legacy_verify.get("ok", False)):
                add_error(str(legacy_verify.get("message") or "legacy verification failed"))

            if bool(step.get("verify_compile", False)):
                checks.append("verify_compile")
                if full_target_path.endswith(".py"):
                    try:
                        py_compile.compile(full_target_path, doraise=True)
                    except py_compile.PyCompileError as exc:
                        add_error(f"compile verification failed for {target_path}: {exc}")
                    except Exception as exc:
                        add_error(f"compile verification error for {target_path}: {exc}")

        verify_command = str(step.get("verify_command") or "").strip()
        if verify_command:
            checks.append("verify_command")
            try:
                command_result = subprocess.run(
                    verify_command,
                    shell=True,
                    cwd=str(step.get("command_cwd") or step.get("cwd") or os.getcwd()),
                    capture_output=True,
                    text=True,
                    timeout=int(step.get("verify_timeout", 30) or 30),
                )
                if command_result.returncode != 0:
                    add_error(
                        "verify_command failed: "
                        + verify_command
                        + f" (returncode={command_result.returncode})"
                        + (f" stderr={command_result.stderr.strip()}" if command_result.stderr else "")
                    )
            except Exception as exc:
                add_error(f"verify_command error: {exc}")

        verify_finished_at = str(int(time.time() * 1000))
        ok = not errors
        verify_metadata = {
            "verify_started_at": verify_started_at,
            "verify_finished_at": verify_finished_at,
            "verify_result": "passed" if ok else "failed",
            "verify_checks": list(dict.fromkeys(checks)),
            "verify_errors": errors,
        }
        transaction = self._mark_apply_patch_transaction(
            transaction,
            status="verifying",
            verify_metadata=verify_metadata,
        )
        return {
            "ok": ok,
            "verification_ok": ok,
            "message": "verification passed" if ok else "; ".join(errors),
            **verify_metadata,
            "transaction": transaction,
        }

    def _build_apply_patch_rollback_result(self, rollback_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        rollback_error = "; ".join(
            str(item.get("rollback_error") or "")
            for item in rollback_items or []
            if str(item.get("rollback_error") or "").strip()
        )
        return {
            "rollback_applied": any(bool(item.get("rollback_applied")) for item in rollback_items or []),
            "rollback_error": rollback_error,
            "rolled_back_files": [
                str(item.get("target_path") or item.get("full_target_path") or "")
                for item in rollback_items or []
                if bool(item.get("rollback_applied"))
            ],
            "items": copy.deepcopy(rollback_items or []),
        }

    def _verify_apply_patch_target(self, step: Dict[str, Any], full_target_path: str) -> Dict[str, Any]:
        step = step if isinstance(step, dict) else {}
        checks: List[str] = []
        verify_contains = step.get("verify_contains")
        verify_not_contains = step.get("verify_not_contains")
        verify_python_syntax = bool(step.get("verify_python_syntax", False))

        if isinstance(verify_contains, str) and verify_contains:
            checks.append("verify_contains")
        if isinstance(verify_not_contains, str) and verify_not_contains:
            checks.append("verify_not_contains")
        if verify_python_syntax:
            checks.append("verify_python_syntax")

        if not checks:
            return {"ok": True, "verification_ok": True, "skipped": True, "checks": []}

        try:
            with open(full_target_path, "r", encoding="utf-8") as fh:
                current_text = fh.read()
        except Exception as exc:
            return {
                "ok": False,
                "verification_ok": False,
                "checks": checks,
                "message": f"verify read failed: {exc}",
                "error_type": "verify_read_failed",
            }

        if isinstance(verify_contains, str) and verify_contains and verify_contains not in current_text:
            return {
                "ok": False,
                "verification_ok": False,
                "checks": checks,
                "message": f"verify_contains failed: {verify_contains!r} not found",
                "error_type": "verify_contains_failed",
                "verify_contains": verify_contains,
            }

        if isinstance(verify_not_contains, str) and verify_not_contains and verify_not_contains in current_text:
            return {
                "ok": False,
                "verification_ok": False,
                "checks": checks,
                "message": f"verify_not_contains failed: {verify_not_contains!r} found",
                "error_type": "verify_not_contains_failed",
                "verify_not_contains": verify_not_contains,
            }

        if verify_python_syntax:
            if not str(full_target_path).endswith(".py"):
                return {
                    "ok": False,
                    "verification_ok": False,
                    "checks": checks,
                    "message": "verify_python_syntax only supports .py files",
                    "error_type": "verify_python_syntax_non_python_target",
                }
            try:
                py_compile.compile(full_target_path, doraise=True)
            except py_compile.PyCompileError as exc:
                return {
                    "ok": False,
                    "verification_ok": False,
                    "checks": checks,
                    "message": f"python syntax failed: {exc}",
                    "error_type": "python_syntax_error",
                    "error": str(exc),
                }
            except Exception as exc:
                return {
                    "ok": False,
                    "verification_ok": False,
                    "checks": checks,
                    "message": f"python syntax check failed: {exc}",
                    "error_type": "python_syntax_check_failed",
                    "error": str(exc),
                }

        return {"ok": True, "verification_ok": True, "skipped": False, "checks": checks}

    def _apply_unified_diff_text(self, original_text: str, patch_text: str) -> Tuple[str, Dict[str, Any]]:
        original_lines = str(original_text or "").splitlines(keepends=True)
        patch_lines = str(patch_text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines(keepends=True)

        result_lines: List[str] = []
        original_index = 0
        hunk_count = 0
        added_count = 0
        removed_count = 0
        patch_index = 0

        while patch_index < len(patch_lines):
            line = patch_lines[patch_index]
            if not line.startswith("@@ "):
                patch_index += 1
                continue

            header = line.strip()
            match = re.match(r"@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@", header)
            if not match:
                raise ValueError(f"invalid hunk header: {header}")

            old_start = int(match.group(1))
            hunk_original_index = max(0, old_start - 1)

            if hunk_original_index < original_index:
                raise ValueError("overlapping hunks are not supported")

            result_lines.extend(original_lines[original_index:hunk_original_index])
            original_index = hunk_original_index
            patch_index += 1
            hunk_count += 1

            while patch_index < len(patch_lines):
                hunk_line = patch_lines[patch_index]
                if hunk_line.startswith("@@ "):
                    break
                if hunk_line.startswith("--- ") or hunk_line.startswith("+++ "):
                    break

                if hunk_line.startswith("\\ No newline at end of file"):
                    patch_index += 1
                    continue

                if not hunk_line:
                    patch_index += 1
                    continue

                marker = hunk_line[0]
                payload = hunk_line[1:]

                if marker == " ":
                    if original_index >= len(original_lines):
                        raise ValueError("context line exceeds target length")
                    if original_lines[original_index].rstrip("\n") != payload.rstrip("\n"):
                        raise ValueError(f"context mismatch near line {original_index + 1}")
                    result_lines.append(original_lines[original_index])
                    original_index += 1
                elif marker == "-":
                    if original_index >= len(original_lines):
                        raise ValueError("remove line exceeds target length")
                    if original_lines[original_index].rstrip("\n") != payload.rstrip("\n"):
                        raise ValueError(f"remove mismatch near line {original_index + 1}")
                    original_index += 1
                    removed_count += 1
                elif marker == "+":
                    result_lines.append(payload)
                    added_count += 1
                else:
                    # Unknown lines inside a hunk are unsafe because they may be explanations.
                    if hunk_line.strip():
                        raise ValueError(f"unsupported hunk line: {hunk_line.strip()}")

                patch_index += 1

        if hunk_count <= 0:
            raise ValueError("patch contains no hunks")

        result_lines.extend(original_lines[original_index:])
        patched_text = "".join(result_lines)
        return patched_text, {
            "hunk_count": hunk_count,
            "added_count": added_count,
            "removed_count": removed_count,
        }

    def _handle_append_file_step(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        """Append UTF-8 text to a workspace file without overwriting existing content.

        Boundary:
        - This is a StepExecutor runtime handler, not the planner and not the
          generic tool registry.
        - It only appends content to paths resolved by TaskPathManager.
        - Parent directories are created when needed.
        """
        _ = context

        raw_path = str(step.get("path") or "").strip()
        if not raw_path:
            return {
                "ok": False,
                "type": "append_file",
                "path": raw_path,
                "message": "append_file step missing path",
                "final_answer": "append_file step missing path",
                "error": {
                    "type": "validation_error",
                    "message": "append_file step missing path",
                    "retryable": False,
                },
            }

        if bool(step.get("use_previous_text", False)):
            content = self._extract_previous_text(previous_result=previous_result, context=context)
        else:
            content = step.get("content", "")

        if content is None:
            content = ""
        content = str(content)

        scope = str(step.get("scope") or "").strip().lower()
        default_scope = "shared" if scope == "shared" or raw_path.replace("\\", "/").startswith("workspace/shared/") or raw_path.replace("\\", "/").startswith("shared/") else "sandbox"

        try:
            full_path = self.resolve_write_path(
                relative_path=raw_path,
                task=task,
                default_scope=default_scope,
            )
        except Exception as exc:
            return {
                "ok": False,
                "type": "append_file",
                "path": raw_path,
                "message": f"append_file path resolve failed: {exc}",
                "final_answer": f"append_file path resolve failed: {exc}",
                "error": {
                    "type": "path_resolve_failed",
                    "message": str(exc),
                    "retryable": False,
                },
            }

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        file_existed = os.path.exists(full_path)

        newline = step.get("newline", None)
        append_text = content
        if newline is True and append_text and not append_text.endswith("\n"):
            append_text += "\n"

        with open(full_path, "a", encoding="utf-8") as f:
            f.write(append_text)

        return {
            "ok": True,
            "type": "append_file",
            "path": raw_path,
            "full_path": full_path,
            "scope": default_scope,
            "bytes_appended": len(append_text.encode("utf-8")),
            "content": content,
            "message": content,
            "final_answer": content,
            "file_existed": file_existed,
            "used_previous_text": bool(step.get("use_previous_text", False)),
            "result": {
                "path": raw_path,
                "full_path": full_path,
                "scope": default_scope,
                "bytes_appended": len(append_text.encode("utf-8")),
                "content": content,
                "file_existed": file_existed,
            },
            "error": None,
        }


    def _handle_llm_step(
        self,
        step: Dict[str, Any],
        task: Optional[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
        previous_result: Any,
    ) -> Dict[str, Any]:
        _ = task

        prompt_template = str(step.get("prompt_template") or step.get("prompt") or "").strip()
        previous_text = self._extract_previous_text(previous_result=previous_result, context=context)

        if not previous_text and isinstance(step.get("file_content"), str):
            previous_text = str(step.get("file_content") or "")

        prompt = prompt_template.replace("{{file_content}}", previous_text)
        prompt = prompt.replace("{{previous_result}}", previous_text)
        prompt = prompt.replace("{{previous_result_text}}", previous_text)

        mode = str(step.get("mode") or "").strip().lower()
        raw_llm_text = self._call_llm(prompt)
        llm_text = str(raw_llm_text or "")

        if self._is_code_chain_diff_mode(mode):
            cleaned_text = self._sanitize_unified_diff_output(llm_text)
            validation = self._validate_unified_diff_text(cleaned_text)
            if not validation.get("ok"):
                message = str(validation.get("message") or "code chain diff output validation failed")
                return {
                    "ok": False,
                    "type": "llm",
                    "mode": mode,
                    "prompt": prompt,
                    "prompt_template": prompt_template,
                    "input_text": previous_text,
                    "text": cleaned_text,
                    "content": cleaned_text,
                    "message": message,
                    "final_answer": message,
                    "result": {"prompt": prompt, "text": cleaned_text, "raw_text": llm_text, "validation": validation},
                    "error": {"type": "code_chain_diff_output_invalid", "message": message, "retryable": False, "details": validation},
                }
            llm_text = cleaned_text

        if self._is_code_chain_mode(mode):
            cleaned_text = self._sanitize_code_chain_output(llm_text)
            validation = self._validate_code_chain_output(
                text=cleaned_text,
                original_text=llm_text,
                source_text=previous_text,
            )
            if not validation.get("ok"):
                message = str(validation.get("message") or "code chain output validation failed")
                return {
                    "ok": False,
                    "type": "llm",
                    "mode": mode,
                    "prompt": prompt,
                    "prompt_template": prompt_template,
                    "input_text": previous_text,
                    "text": cleaned_text,
                    "content": cleaned_text,
                    "message": message,
                    "final_answer": message,
                    "result": {
                        "prompt": prompt,
                        "text": cleaned_text,
                        "raw_text": llm_text,
                        "validation": validation,
                    },
                    "error": {
                        "type": str(validation.get("error_type") or "code_chain_output_invalid"),
                        "message": message,
                        "retryable": False,
                        "details": validation,
                    },
                }
            llm_text = cleaned_text

        return {
            "ok": True,
            "type": "llm",
            "mode": mode,
            "prompt": prompt,
            "prompt_template": prompt_template,
            "input_text": previous_text,
            "text": llm_text,
            "content": llm_text,
            "message": llm_text,
            "final_answer": llm_text,
            "result": {
                "prompt": prompt,
                "text": llm_text,
                "message": llm_text,
                "final_answer": llm_text,
            },
            "error": None,
        }

    def _extract_previous_text(
        self,
        previous_result: Any,
        context: Optional[Dict[str, Any]],
    ) -> str:
        if isinstance(context, dict):
            file_content = context.get("file_content")
            if isinstance(file_content, str) and file_content:
                return file_content

        text = self._extract_text_deep(previous_result)
        if text:
            return text

        return ""

    def _extract_text_deep(self, payload: Any, depth: int = 0) -> str:
        if depth > 10:
            return ""

        if payload is None:
            return ""

        if isinstance(payload, str):
            return payload

        if isinstance(payload, dict):
            # Prefer actual file/LLM payload content over wrapper summaries.
            # Runtime wrappers often store useful content under:
            #   previous_result["result"]["content"]
            #   previous_result["result"]["result"]["content"]
            # while the outer "message" / "final_answer" may only be a status
            # such as "已讀取檔案".  File Chain v3 depends on the real file
            # content being injected into the LLM prompt.
            for nested_key in ("result", "output", "data", "payload", "raw", "previous_result"):
                nested = payload.get(nested_key)
                if isinstance(nested, dict):
                    for content_key in (
                        "content",
                        "text",
                        "file_content",
                        "output_text",
                        "summary_text",
                        "stdout",
                        "message",
                        "final_answer",
                        "response",
                        "answer",
                    ):
                        value = nested.get(content_key)
                        if isinstance(value, str) and value:
                            return value

                    deeper = self._extract_text_deep(nested, depth + 1)
                    if deeper:
                        return deeper

                elif isinstance(nested, list):
                    deeper = self._extract_text_deep(nested, depth + 1)
                    if deeper:
                        return deeper

            for key in (
                "file_content",
                "content",
                "text",
                "output_text",
                "summary_text",
                "stdout",
                "message",
                "response",
                "final_answer",
                "answer",
            ):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value

        if isinstance(payload, list):
            for item in reversed(payload):
                text = self._extract_text_deep(item, depth + 1)
                if text:
                    return text

        return ""

    def _is_code_chain_diff_mode(self, mode: str) -> bool:
        normalized = str(mode or "").strip().lower()
        return normalized in {"code_chain_diff_v0", "code_chain_v0_diff", "code_chain_patch_v0", "code_diff", "patch_diff"}

    def _sanitize_unified_diff_output(self, text: str) -> str:
        """Clean LLM diff output before writing a .patch/.diff file."""
        value = str(text or "").strip()
        if not value:
            return ""

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            try:
                decoded = json.loads(value)
                if isinstance(decoded, str):
                    value = decoded.strip()
            except Exception:
                pass

        lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")

        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and lines[0].strip().startswith("```"):
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and lines[-1].strip() == "```":
            lines.pop()

        cleaned = "\n".join(lines).strip("\n")

        # If the model included prose before the diff, keep from the first --- header.
        diff_start = cleaned.find("--- ")
        if diff_start > 0:
            cleaned = cleaned[diff_start:]

        return cleaned.strip("\n")

    def _is_code_chain_mode(self, mode: str) -> bool:
        normalized = str(mode or "").strip().lower()
        return normalized.startswith("code_chain") or normalized in {
            "code_rewrite",
            "code_edit",
            "code_modify",
            "code_comments",
        }

    def _sanitize_code_chain_output(self, text: str) -> str:
        """Clean LLM code output before a downstream write_file step persists it.

        Code Chain v0.1 keeps the capability small and safe:
        - remove Markdown fences such as ```python ... ```
        - remove common leading labels
        - decode a fully JSON-quoted string when the model returns one
        - keep the result as complete plain file content
        """
        value = str(text or "").strip()
        if not value:
            return ""

        # Some models return the whole file as a JSON string literal.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            try:
                decoded = json.loads(value)
                if isinstance(decoded, str):
                    value = decoded.strip()
            except Exception:
                pass

        lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")

        # Drop a leading Markdown code fence: ```python / ```py / ```
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and lines[0].strip().startswith("```"):
            lines.pop(0)

        # Drop a trailing Markdown code fence.
        while lines and not lines[-1].strip():
            lines.pop()
        if lines and lines[-1].strip() == "```":
            lines.pop()

        cleaned = "\n".join(lines).strip("\n")

        # Remove common prose prefixes if the model ignored the instruction.
        prefixes = (
            "here is the complete rewritten file:",
            "here is the rewritten file:",
            "here is the code:",
            "updated code:",
            "rewritten code:",
        )
        lowered = cleaned.lower().lstrip()
        for prefix in prefixes:
            if lowered.startswith(prefix):
                cleaned = cleaned.lstrip()[len(prefix):].lstrip("\n: ")
                break

        # If there is still an embedded fenced block, keep the first fenced body.
        stripped = cleaned.strip()
        first_fence = stripped.find("```")
        if first_fence >= 0:
            after = stripped[first_fence + 3:]
            newline_index = after.find("\n")
            if newline_index >= 0:
                body = after[newline_index + 1:]
                end = body.find("```")
                if end >= 0:
                    stripped = body[:end].strip("\n")
                    cleaned = stripped

        return cleaned.strip("\n")

    def _validate_code_chain_output(
        self,
        text: str,
        original_text: str,
        source_text: str,
    ) -> Dict[str, Any]:
        cleaned = str(text or "")
        raw = str(original_text or "")
        source = str(source_text or "")
        lowered = cleaned.strip().lower()
        raw_lowered = raw.strip().lower()

        if not cleaned.strip():
            return {
                "ok": False,
                "error_type": "code_chain_empty_output",
                "message": "code chain produced empty output; refusing to write file",
            }

        refusal_markers = (
            "i don't see any content",
            "i do not see any content",
            "i cannot read",
            "i can't read",
            "i don't have access",
            "i do not have access",
            "please provide",
            "share the file",
            "no content provided",
            "file is unavailable",
        )
        if any(marker in lowered for marker in refusal_markers) or any(marker in raw_lowered for marker in refusal_markers):
            return {
                "ok": False,
                "error_type": "code_chain_refusal_output",
                "message": "code chain LLM output looks like a refusal instead of file content; refusing to write file",
                "raw_prefix": raw[:240],
            }

        if "```" in cleaned:
            return {
                "ok": False,
                "error_type": "code_chain_markdown_fence_remaining",
                "message": "code chain output still contains Markdown fences after sanitization; refusing to write file",
            }

        # Very small sanity check: code rewrite output should still look like code.
        code_signals = (
            "def ",
            "class ",
            "import ",
            "from ",
            "return ",
            "if __name__",
            "function ",
            "const ",
            "let ",
            "var ",
            "public ",
            "private ",
            "package ",
            "#include",
        )
        if not any(signal in cleaned for signal in code_signals):
            return {
                "ok": False,
                "error_type": "code_chain_no_code_signal",
                "message": "code chain output does not look like code; refusing to write file",
                "output_prefix": cleaned[:240],
            }

        if source.strip() and len(cleaned.strip()) < max(8, int(len(source.strip()) * 0.2)):
            return {
                "ok": False,
                "error_type": "code_chain_output_too_short",
                "message": "code chain output is suspiciously short; refusing to write file",
                "source_length": len(source.strip()),
                "output_length": len(cleaned.strip()),
            }

        return {
            "ok": True,
            "message": "code chain output accepted",
            "output_length": len(cleaned),
            "raw_length": len(raw),
        }

    def _call_llm(self, prompt: str) -> str:
        client = self.llm_client
        if client is None:
            raise RuntimeError("llm_client is missing")

        if hasattr(client, "generate_general") and callable(client.generate_general):
            data = client.generate_general(prompt)
            if isinstance(data, dict):
                return str(data.get("response", "") or "")
            return str(data or "")

        if hasattr(client, "chat_general") and callable(client.chat_general):
            return str(client.chat_general(prompt) or "")

        if hasattr(client, "generate") and callable(client.generate):
            data = client.generate(prompt)
            if isinstance(data, dict):
                return str(data.get("response", "") or "")
            return str(data or "")

        if hasattr(client, "chat") and callable(client.chat):
            return str(client.chat(prompt) or "")

        raise RuntimeError("llm_client has no usable generate/chat method")

    def _build_execution_trace(self, step: Dict[str, Any], result: Dict[str, Any]) -> List[Dict[str, Any]]:
        error_payload = result.get("error") if isinstance(result.get("error"), dict) else {}
        retry_payload = result.get("retry") if isinstance(result.get("retry"), dict) else {}

        error_type = str(error_payload.get("type") or "")
        error_details = error_payload.get("details") if isinstance(error_payload.get("details"), dict) else {}

        step_payload = result.get("step") if isinstance(result.get("step"), dict) else step
        step_type = str(
            result.get("step_type")
            or (step_payload.get("type") if isinstance(step_payload, dict) else "")
            or ""
        ).strip().lower()

        runtime_mode = self._normalize_runtime_mode(
            result.get("runtime_mode")
            or (step_payload.get("runtime_mode") if isinstance(step_payload, dict) else "")
            or "execute"
        )

        event: Dict[str, Any] = {
            "step_index": result.get("step_index"),
            "step_type": step_type,
            "runtime_mode": runtime_mode,
            "ok": bool(result.get("ok", False)),
            "message": result.get("message"),
            "final_answer": result.get("final_answer"),
            "error_type": error_type or None,
            "classification": error_details.get("classification"),
            "attempts": self._safe_int(retry_payload.get("attempts", 1), 1),
            "max_attempts": self._safe_int(retry_payload.get("max_attempts", 1), 1),
            "retry_used": bool(retry_payload.get("used", False)),
        }

        if isinstance(step_payload, dict):
            step_id = str(step_payload.get("id") or "").strip()
            if step_id:
                event["step_id"] = step_id

        return [event]

    def _attach_execution_trace(self, step: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        normalized = copy.deepcopy(result)
        normalized["runtime_mode"] = self._normalize_runtime_mode(
            normalized.get("runtime_mode")
            or (step.get("runtime_mode") if isinstance(step, dict) else "")
            or "execute"
        )
        normalized["execution_trace"] = self._build_execution_trace(step, normalized)

        if isinstance(normalized.get("result"), dict):
            normalized["result"]["runtime_mode"] = normalized["runtime_mode"]
            normalized["result"]["execution_trace"] = copy.deepcopy(normalized["execution_trace"])

        try:
            from core.runtime.payload_normalizer import normalize_runtime_adapter_payload

            normalized["adapter_payload"] = normalize_runtime_adapter_payload(normalized)
        except Exception:
            normalized["adapter_payload"] = {
                "ok": normalized.get("ok"),
                "message": str(normalized.get("message") or ""),
                "final_answer": str(normalized.get("final_answer") or ""),
                "text": str(normalized.get("message") or normalized.get("final_answer") or ""),
                "error_text": "",
                "error_type": "",
                "runtime_mode": str(normalized.get("runtime_mode") or ""),
                "last_result": normalized.get("last_result") if isinstance(normalized.get("last_result"), dict) else None,
                "execution_trace": copy.deepcopy(normalized.get("execution_trace")) if isinstance(normalized.get("execution_trace"), list) else [],
                "raw": copy.deepcopy(normalized),
            }

        return normalized

    def _merge_execution_traces(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        for item in results or []:
            if not isinstance(item, dict):
                continue
            trace = item.get("execution_trace")
            if isinstance(trace, list):
                for event in trace:
                    if isinstance(event, dict):
                        merged.append(copy.deepcopy(event))
        return merged

    def _safe_int(self, value: Any, default: Any = 0) -> Any:
        try:
            return int(value)
        except Exception:
            return default

# ============================================================
# ZERO v7.0.0 - Code Chain repair step handler shim
# ============================================================
# Narrow handler for planner-driven autonomous repair tasks.  The handler keeps
# the existing StepExecutor class intact and registers a new step type:
#   code_chain_repair

_ZERO_V7_ORIGINAL_REGISTER_BUILTINS = StepExecutor._register_builtin_handlers


def _zero_v7_register_builtin_handlers(self):
    _ZERO_V7_ORIGINAL_REGISTER_BUILTINS(self)
    self.register_handler("code_chain_repair", _zero_v7_handle_code_chain_repair_step.__get__(self, StepExecutor))
    self.register_handler("autonomous_code_repair", _zero_v7_handle_code_chain_repair_step.__get__(self, StepExecutor))


def _zero_v7_normalize_rel_path(path_text: str) -> str:
    value = str(path_text or "").strip().strip("'\"`").replace("\\", "/")
    while "//" in value:
        value = value.replace("//", "/")
    return value.lstrip("./")


def _zero_v7_extract_workspace_py_path(text: str) -> str:
    match = re.search(r"(workspace[/\\][A-Za-z0-9_./\\ -]+?\.py)", str(text or ""), flags=re.IGNORECASE)
    if not match:
        return ""
    return _zero_v7_normalize_rel_path(match.group(1))


def _zero_v7_find_function_block(lines, function_name: str):
    pattern = re.compile(r"^\s*def\s+" + re.escape(function_name) + r"\s*\(")
    start = None
    for index, line in enumerate(lines):
        if pattern.search(line):
            start = index
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if re.match(r"^\s*def\s+[A-Za-z_]\w*\s*\(", line):
            end = index
            break
    return start, end


def _zero_v7_patch_function_block(lines, function_name: str, expected_operator: str):
    block = _zero_v7_find_function_block(lines, function_name)
    if block is None:
        return False, f"function not found: {function_name}", lines
    start, end = block
    new_lines = list(lines)
    changed = False
    for index in range(start + 1, end):
        stripped = new_lines[index].strip()
        if not stripped.startswith("return "):
            continue
        if function_name == "add" and stripped == "return a + b":
            return False, "already correct", lines
        if function_name == "multiply" and stripped == "return a * b":
            return False, "already correct", lines
        indent = new_lines[index][: len(new_lines[index]) - len(new_lines[index].lstrip(" \t"))]
        desired = f"{indent}return a {expected_operator} b"
        if new_lines[index] != desired:
            new_lines[index] = desired
            changed = True
        break
    if not changed:
        return False, f"no return line patched for: {function_name}", lines
    return True, "patched", new_lines


def _zero_v7_verify_math_functions(content: str, requested_functions):
    failed = []
    if "add" in requested_functions and not re.search(r"def\s+add\s*\([^)]*\):[\s\S]*?return\s+a\s*\+\s*b", content):
        failed.append("add")
    if "multiply" in requested_functions and not re.search(r"def\s+multiply\s*\([^)]*\):[\s\S]*?return\s+a\s*\*\s*b", content):
        failed.append("multiply")
    return {"ok": not failed, "failed_functions": failed, "requested_functions": list(requested_functions)}


def _zero_v7_handle_code_chain_repair_step(self, step, task=None, context=None, previous_result=None):
    from pathlib import Path
    import datetime
    import difflib
    import json
    import shutil

    payload = step if isinstance(step, dict) else {}
    task_text = str(
        payload.get("task_text")
        or payload.get("instruction")
        or payload.get("goal")
        or (task.get("goal") if isinstance(task, dict) else "")
        or ""
    ).strip()
    target_path = _zero_v7_normalize_rel_path(payload.get("target_path") or _zero_v7_extract_workspace_py_path(task_text))

    if not target_path:
        return {
            "ok": False,
            "message": "planner autonomous repair failed: missing target path",
            "final_answer": "planner autonomous repair failed: missing target path",
            "error": "missing_target_path",
            "result": {"planner_autonomous_repair": True, "changed_files": [], "rollback": False},
        }

    if not target_path.startswith("workspace/") or not target_path.endswith(".py"):
        return {
            "ok": False,
            "message": f"planner autonomous repair failed: unsafe target path: {target_path}",
            "final_answer": f"planner autonomous repair failed: unsafe target path: {target_path}",
            "error": "unsafe_target_path",
            "result": {"planner_autonomous_repair": True, "target_path": target_path, "changed_files": [], "rollback": False},
        }

    project_root = Path.cwd()
    file_path = (project_root / target_path).resolve()
    try:
        file_path.relative_to(project_root.resolve())
    except Exception:
        return {
            "ok": False,
            "message": f"planner autonomous repair failed: path escapes repo root: {target_path}",
            "final_answer": f"planner autonomous repair failed: path escapes repo root: {target_path}",
            "error": "path_escapes_repo_root",
            "result": {"planner_autonomous_repair": True, "target_path": target_path, "changed_files": [], "rollback": False},
        }

    if not file_path.exists():
        return {
            "ok": False,
            "message": f"planner autonomous repair failed: file not found: {target_path}",
            "final_answer": f"planner autonomous repair failed: file not found: {target_path}",
            "error": "file_not_found",
            "result": {"planner_autonomous_repair": True, "target_path": target_path, "changed_files": [], "rollback": False},
        }

    before = file_path.read_text(encoding="utf-8")
    lowered = task_text.lower()
    requested = []
    if "add" in lowered or "math" in lowered or "function" in lowered:
        requested.append("add")
    if "multiply" in lowered or "math" in lowered or "function" in lowered:
        requested.append("multiply")
    requested = list(dict.fromkeys(requested)) or ["add", "multiply"]

    before_verify = _zero_v7_verify_math_functions(before, requested)
    if before_verify.get("ok"):
        final = f"planner autonomous repair check: functions already appear correct in {target_path}; changed_files=0"
        return {
            "ok": True,
            "message": final,
            "final_answer": final,
            "result": {
                "planner_autonomous_repair": True,
                "status": "success",
                "reason": "already_correct",
                "target_path": target_path,
                "changed_files": [],
                "verification": {"ok": True, "status": "passed", "already_correct": True},
                "rollback": False,
                "changed_lines": 0,
            },
        }

    lines = before.splitlines()
    patched_lines = list(lines)
    events = []
    for fn, op in (("add", "+"), ("multiply", "*")):
        if fn not in requested:
            continue
        did_change, reason, patched_lines = _zero_v7_patch_function_block(patched_lines, fn, op)
        events.append({"function": fn, "changed": did_change, "reason": reason})

    after = "\n".join(patched_lines)
    if before.endswith("\n"):
        after += "\n"

    if after == before:
        final = f"planner autonomous repair failed: no patch generated for {target_path}; changed_files=0"
        return {
            "ok": False,
            "message": final,
            "final_answer": final,
            "error": "no_patch_generated",
            "result": {
                "planner_autonomous_repair": True,
                "status": "failed",
                "target_path": target_path,
                "changed_files": [],
                "events": events,
                "rollback": False,
                "changed_lines": 0,
            },
        }

    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    safe_name = target_path.replace("/", "_").replace("\\", "_")
    backup_dir = project_root / "workspace" / "backups" / "code_chain"
    diff_dir = project_root / "workspace" / "audit" / "code_chain" / "diffs"
    audit_dir = project_root / "workspace" / "audit" / "code_chain"
    backup_dir.mkdir(parents=True, exist_ok=True)
    diff_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{timestamp}_{safe_name}.bak"
    diff_path = diff_dir / f"{timestamp}_{safe_name}.diff"
    audit_path = audit_dir / f"{timestamp}_{safe_name}.json"

    shutil.copyfile(file_path, backup_path)
    diff_text = "".join(difflib.unified_diff(
        before.splitlines(True),
        after.splitlines(True),
        fromfile=f"before/{target_path}",
        tofile=f"after/{target_path}",
    ))
    diff_path.write_text(diff_text, encoding="utf-8")
    file_path.write_text(after, encoding="utf-8")

    verification = _zero_v7_verify_math_functions(after, requested)
    rollback = False
    if not verification.get("ok"):
        shutil.copyfile(backup_path, file_path)
        rollback = True

    changed_lines = sum(1 for line in diff_text.splitlines() if line.startswith("+") or line.startswith("-"))
    audit_payload = {
        "planner_autonomous_repair": True,
        "target_path": target_path,
        "task_text": task_text,
        "events": events,
        "verification": verification,
        "rollback": rollback,
        "backup": str(backup_path).replace("\\", "/"),
        "diff": str(diff_path).replace("\\", "/"),
        "changed_lines": changed_lines,
        "changed_files": [] if rollback else [target_path],
    }
    audit_path.write_text(json.dumps(audit_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = bool(verification.get("ok")) and not rollback
    final = (
        f"planner autonomous repair {'succeeded' if ok else 'failed'}: "
        f"verification={'passed' if ok else 'failed'}; rollback={rollback}; "
        f"changed_files={0 if rollback else 1}; backup={backup_path.as_posix()}; "
        f"diff={diff_path.as_posix()}; audit={audit_path.as_posix()}; "
        f"changed_lines={changed_lines}"
    )
    return {
        "ok": ok,
        "message": final,
        "final_answer": final,
        "error": None if ok else "verification_failed",
        "result": audit_payload,
        "execution_trace": [
            {
                "step_type": "code_chain_repair",
                "ok": ok,
                "message": final,
                "final_answer": final,
                "error_type": "" if ok else "verification_failed",
                "classification": "planner_autonomous_repair",
                "attempts": 1,
                "max_attempts": 1,
                "retry_used": False,
            }
        ],
    }


StepExecutor._register_builtin_handlers = _zero_v7_register_builtin_handlers


# ZERO v7.0.2 marker: code_chain_repair handler preserved by StepExecutor v7.0.1 shim.


# ============================================================
# ZERO v7.0.3 - StepExecutor repair handler registration hardening
# ============================================================
# The v7.0.2 shim already defines _zero_v7_handle_code_chain_repair_step.
# This layer makes registration explicit and idempotent for runtimes that were
# instantiated before/around monkey-patching.

_ZERO_V703_ORIGINAL_STEP_EXECUTOR_INIT = StepExecutor.__init__


def _zero_v703_step_executor_init(self, *args, **kwargs):
    _ZERO_V703_ORIGINAL_STEP_EXECUTOR_INIT(self, *args, **kwargs)
    try:
        self.register_handler("code_chain_repair", _zero_v7_handle_code_chain_repair_step.__get__(self, StepExecutor))
        self.register_handler("autonomous_code_repair", _zero_v7_handle_code_chain_repair_step.__get__(self, StepExecutor))
    except Exception:
        pass


StepExecutor.__init__ = _zero_v703_step_executor_init
StepExecutor.CODE_CHAIN_REPAIR_STEP_TYPES = {"code_chain_repair", "autonomous_code_repair"}


# ============================================================
# ZERO v7.1.0 - Code Chain Repair Scope Guard
# ============================================================
# Reinforce the repair handler itself. AgentLoop should block bad repair targets
# before task creation, but direct runtime/planner callers must also fail closed.

_ZERO_V710_ORIGINAL_REGISTER_BUILTINS = StepExecutor._register_builtin_handlers
try:
    _ZERO_V710_ORIGINAL_CODE_CHAIN_REPAIR_HANDLER = _zero_v7_handle_code_chain_repair_step
except NameError:  # pragma: no cover - defensive for partial builds
    _ZERO_V710_ORIGINAL_CODE_CHAIN_REPAIR_HANDLER = None


def _zero_v710_step_normalize_path_text(path_text: str) -> str:
    value = str(path_text or "").strip().strip("'\"`").replace("\\", "/")
    while "//" in value:
        value = value.replace("//", "/")
    return value.lstrip("./")


def _zero_v710_step_extract_any_py_path(text: str) -> str:
    match = re.search(
        r"((?:workspace|core|services|tests|ui)[/\\][A-Za-z0-9_./\\ -]+?\.py|app\.py|system_boot\.py)",
        str(text or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    return _zero_v710_step_normalize_path_text(match.group(1))


def _zero_v710_step_repair_scope_decision(target_path: str) -> Dict[str, Any]:
    normalized = _zero_v710_step_normalize_path_text(target_path)
    if not normalized:
        return {"ok": False, "error": "missing_target_path", "reason": "code_chain_repair step missing target_path", "target_path": ""}
    lowered = normalized.lower()
    protected = (
        lowered == "app.py"
        or lowered == "system_boot.py"
        or lowered.startswith("core/")
        or lowered.startswith("services/")
        or lowered.startswith("tests/")
        or lowered.startswith("ui/")
    )
    if protected:
        return {"ok": False, "error": "repair_scope_blocked", "reason": f"blocked by repair scope guard: {normalized}", "target_path": normalized}
    if not normalized.startswith("workspace/shared/") or not normalized.endswith(".py"):
        return {"ok": False, "error": "repair_scope_blocked", "reason": f"autonomous repair requires workspace/shared/*.py target: {normalized}", "target_path": normalized}
    try:
        from pathlib import Path
        repo_root = Path.cwd().resolve()
        target = (repo_root / normalized).resolve()
        target.relative_to(repo_root)
    except Exception:
        return {"ok": False, "error": "path_escapes_repo_root", "reason": f"repair target escapes repo root: {normalized}", "target_path": normalized}
    if not target.exists():
        return {"ok": False, "error": "file_not_found", "reason": f"file not found: {normalized}", "target_path": normalized}
    return {"ok": True, "error": None, "reason": "repair scope preflight passed", "target_path": normalized}


def _zero_v710_fail_step_result(reason: str, error: str, target_path: str = "") -> Dict[str, Any]:
    final = f"planner autonomous repair preflight failed: {reason}; changed_files=0"
    return {
        "ok": False,
        "message": final,
        "final_answer": final,
        "error": error or reason,
        "result": {
            "planner_autonomous_repair": True,
            "repair_scope_guard": True,
            "status": "failed",
            "target_path": target_path,
            "changed_files": [],
            "rollback": False,
            "error": error or reason,
            "reason": reason,
        },
        "execution_trace": [
            {
                "step_type": "code_chain_repair",
                "ok": False,
                "message": final,
                "final_answer": final,
                "error_type": error or "repair_preflight_failed",
                "classification": "repair_scope_guard",
                "attempts": 1,
                "max_attempts": 1,
                "retry_used": False,
            }
        ],
    }


def _zero_v710_handle_code_chain_repair_step(self, step, task=None, context=None, previous_result=None):
    payload = step if isinstance(step, dict) else {}
    task_text = str(
        payload.get("task_text")
        or payload.get("instruction")
        or payload.get("goal")
        or (task.get("goal") if isinstance(task, dict) else "")
        or ""
    ).strip()
    target_path = _zero_v710_step_normalize_path_text(
        payload.get("target_path")
        or payload.get("path")
        or payload.get("file_path")
        or _zero_v710_step_extract_any_py_path(task_text)
    )
    decision = _zero_v710_step_repair_scope_decision(target_path)
    if not bool(decision.get("ok")):
        return _zero_v710_fail_step_result(
            reason=str(decision.get("reason") or decision.get("error") or "repair preflight failed"),
            error=str(decision.get("error") or "repair_preflight_failed"),
            target_path=str(decision.get("target_path") or target_path),
        )
    if _ZERO_V710_ORIGINAL_CODE_CHAIN_REPAIR_HANDLER is None:
        return _zero_v710_fail_step_result(
            reason="code_chain_repair handler missing",
            error="handler_missing",
            target_path=target_path,
        )
    patched_step = dict(payload)
    patched_step["target_path"] = str(decision.get("target_path") or target_path)
    return _ZERO_V710_ORIGINAL_CODE_CHAIN_REPAIR_HANDLER(self, patched_step, task=task, context=context, previous_result=previous_result)


def _zero_v710_handle_code_chain_repair_preflight_failed_step(self, step, task=None, context=None, previous_result=None):
    payload = step if isinstance(step, dict) else {}
    reason = str(payload.get("reason") or payload.get("error") or "repair preflight failed")
    error = str(payload.get("error") or "repair_preflight_failed")
    target_path = _zero_v710_step_normalize_path_text(payload.get("target_path") or "")
    return _zero_v710_fail_step_result(reason=reason, error=error, target_path=target_path)


def _zero_v710_register_builtin_handlers(self):
    _ZERO_V710_ORIGINAL_REGISTER_BUILTINS(self)
    self.register_handler("code_chain_repair", _zero_v710_handle_code_chain_repair_step.__get__(self, StepExecutor))
    self.register_handler("autonomous_code_repair", _zero_v710_handle_code_chain_repair_step.__get__(self, StepExecutor))
    self.register_handler("code_chain_repair_preflight_failed", _zero_v710_handle_code_chain_repair_preflight_failed_step.__get__(self, StepExecutor))


StepExecutor._register_builtin_handlers = _zero_v710_register_builtin_handlers
StepExecutor.CODE_CHAIN_REPAIR_STEP_TYPES = {"code_chain_repair", "autonomous_code_repair", "code_chain_repair_preflight_failed"}


# ============================================================
# ZERO v7.3.0 - Autonomous Multi-Step Repair Chain handlers
# ============================================================
# Adds explicit analyze / verify steps around the existing code_chain_repair
# handler.  The actual write remains inside the existing guarded repair lane.

def _zero_v730_requested_math_functions(task_text: str):
    lowered = str(task_text or "").strip().lower()
    requested = []
    if "add" in lowered or "math" in lowered or "function" in lowered:
        requested.append("add")
    if "multiply" in lowered or "math" in lowered or "function" in lowered:
        requested.append("multiply")
    return list(dict.fromkeys(requested)) or ["add", "multiply"]


def _zero_v730_resolve_repair_target(step, task=None):
    payload = step if isinstance(step, dict) else {}
    task_payload = task if isinstance(task, dict) else {}
    task_text = str(
        payload.get("task_text")
        or payload.get("instruction")
        or payload.get("goal")
        or task_payload.get("goal")
        or ""
    ).strip()
    target_path = _zero_v7_normalize_rel_path(
        payload.get("target_path")
        or task_payload.get("target_path")
        or _zero_v7_extract_workspace_py_path(task_text)
    )
    return task_text, target_path


def _zero_v730_read_target_for_nonwrite_step(task_text: str, target_path: str):
    from pathlib import Path

    if not target_path:
        return None, {
            "ok": False,
            "error": "missing_target_path",
            "message": "planner autonomous repair failed: missing target path",
        }
    if not target_path.startswith("workspace/shared/") or not target_path.endswith(".py"):
        return None, {
            "ok": False,
            "error": "unsafe_target_path",
            "message": f"planner autonomous repair failed: unsafe target path: {target_path}",
        }

    project_root = Path.cwd().resolve()
    file_path = (project_root / target_path).resolve()
    try:
        file_path.relative_to(project_root)
    except Exception:
        return None, {
            "ok": False,
            "error": "path_escapes_repo_root",
            "message": f"planner autonomous repair failed: path escapes repo root: {target_path}",
        }
    if not file_path.exists():
        return None, {
            "ok": False,
            "error": "file_not_found",
            "message": f"planner autonomous repair failed: file not found: {target_path}",
        }
    try:
        return file_path.read_text(encoding="utf-8"), None
    except Exception as exc:
        return None, {
            "ok": False,
            "error": "read_failed",
            "message": f"planner autonomous repair failed: could not read {target_path}: {exc}",
        }


def _zero_v730_handle_code_chain_analyze_step(self, step, task=None, context=None, previous_result=None):
    task_text, target_path = _zero_v730_resolve_repair_target(step, task=task)
    content, error = _zero_v730_read_target_for_nonwrite_step(task_text, target_path)
    if error:
        message = str(error.get("message") or error.get("error") or "code chain analyze failed")
        return {
            "ok": False,
            "message": message,
            "final_answer": message,
            "error": error.get("error"),
            "result": {
                "planner_autonomous_repair": True,
                "step_type": "code_chain_analyze",
                "target_path": target_path,
                "changed_files": [],
                "analysis_ok": False,
            },
        }

    requested = _zero_v730_requested_math_functions(task_text)
    verification = _zero_v7_verify_math_functions(content, requested)
    failed_functions = list(verification.get("failed_functions") or [])
    already_correct = bool(verification.get("ok"))
    message = (
        f"planner autonomous repair analyze: target={target_path}; "
        f"requested={','.join(requested)}; "
        f"failed_functions={','.join(failed_functions) if failed_functions else 'none'}; "
        f"already_correct={already_correct}"
    )
    return {
        "ok": True,
        "message": message,
        "final_answer": message,
        "error": None,
        "result": {
            "planner_autonomous_repair": True,
            "step_type": "code_chain_analyze",
            "target_path": target_path,
            "requested_functions": requested,
            "failed_functions": failed_functions,
            "already_correct": already_correct,
            "verification": verification,
            "changed_files": [],
            "analysis_ok": True,
        },
        "execution_trace": [
            {
                "step_type": "code_chain_analyze",
                "ok": True,
                "message": message,
                "final_answer": message,
                "error_type": "",
                "classification": "planner_autonomous_repair_analysis",
                "attempts": 1,
                "max_attempts": 1,
                "retry_used": False,
            }
        ],
    }


def _zero_v730_handle_code_chain_verify_step(self, step, task=None, context=None, previous_result=None):
    task_text, target_path = _zero_v730_resolve_repair_target(step, task=task)
    content, error = _zero_v730_read_target_for_nonwrite_step(task_text, target_path)
    if error:
        message = str(error.get("message") or error.get("error") or "code chain verify failed")
        return {
            "ok": False,
            "message": message,
            "final_answer": message,
            "error": error.get("error"),
            "result": {
                "planner_autonomous_repair": True,
                "step_type": "code_chain_verify",
                "target_path": target_path,
                "changed_files": [],
                "verification": {"ok": False, "status": "failed", "error": error.get("error")},
            },
        }

    requested = _zero_v730_requested_math_functions(task_text)
    verification = _zero_v7_verify_math_functions(content, requested)
    ok = bool(verification.get("ok"))
    failed_functions = list(verification.get("failed_functions") or [])
    message = (
        f"planner autonomous repair verify: verification={'passed' if ok else 'failed'}; "
        f"target={target_path}; failed_functions={','.join(failed_functions) if failed_functions else 'none'}"
    )
    return {
        "ok": ok,
        "message": message,
        "final_answer": message,
        "error": None if ok else "verification_failed",
        "result": {
            "planner_autonomous_repair": True,
            "step_type": "code_chain_verify",
            "target_path": target_path,
            "requested_functions": requested,
            "verification": verification,
            "changed_files": [],
            "rollback": False,
        },
        "execution_trace": [
            {
                "step_type": "code_chain_verify",
                "ok": ok,
                "message": message,
                "final_answer": message,
                "error_type": "" if ok else "verification_failed",
                "classification": "planner_autonomous_repair_verification",
                "attempts": 1,
                "max_attempts": 1,
                "retry_used": False,
            }
        ],
    }


_ZERO_V730_ORIGINAL_REGISTER_BUILTIN_HANDLERS = StepExecutor._register_builtin_handlers


def _zero_v730_register_builtin_handlers(self):
    _ZERO_V730_ORIGINAL_REGISTER_BUILTIN_HANDLERS(self)
    self.register_handler("code_chain_analyze", _zero_v730_handle_code_chain_analyze_step.__get__(self, StepExecutor))
    self.register_handler("code_chain_verify", _zero_v730_handle_code_chain_verify_step.__get__(self, StepExecutor))
    # Re-register repair to keep the write step on the already guarded lane.
    if "code_chain_repair" not in self.handlers:
        self.register_handler("code_chain_repair", _zero_v710_handle_code_chain_repair_step.__get__(self, StepExecutor))


StepExecutor._register_builtin_handlers = _zero_v730_register_builtin_handlers
StepExecutor.CODE_CHAIN_REPAIR_STEP_TYPES = {
    "code_chain_analyze",
    "code_chain_repair",
    "autonomous_code_repair",
    "code_chain_verify",
    "code_chain_repair_preflight_failed",
}


# ZERO v7.3.1 marker: code_chain_analyze and code_chain_verify handlers are registered above.
StepExecutor.CODE_CHAIN_WORKFLOW_STEP_TYPES = set(getattr(StepExecutor, "CODE_CHAIN_REPAIR_STEP_TYPES", set())) | {
    "code_chain_analyze",
    "code_chain_repair",
    "autonomous_code_repair",
    "code_chain_verify",
    "code_chain_repair_preflight_failed",
}


# ============================================================
# ZERO v7.3.4 - Repair/Edit payload schema bridge
# ============================================================
# Repair steps in a multi-step chain must hand apply steps a real edit schema:
# old_text + new_text for replacement tools, or complete content for write_file.
# This bridge keeps the schema in the edit execution path and leaves scheduler
# orchestration untouched.

_ZERO_V734_ORIGINAL_STEP_EXECUTOR_INIT = StepExecutor.__init__
_ZERO_V734_ORIGINAL_APPLY_UNIFIED_DIFF_STEP = StepExecutor._handle_apply_unified_diff_step
_ZERO_V734_ORIGINAL_CODE_CHAIN_REPAIR_HANDLER = _zero_v710_handle_code_chain_repair_step


def _zero_v734_step_executor_init(self, *args, **kwargs):
    _ZERO_V734_ORIGINAL_STEP_EXECUTOR_INIT(self, *args, **kwargs)
    try:
        self.register_handler("code_chain_repair", _zero_v734_handle_code_chain_repair_step.__get__(self, StepExecutor))
        self.register_handler("autonomous_code_repair", _zero_v734_handle_code_chain_repair_step.__get__(self, StepExecutor))
        self.register_handler("apply_unified_diff", _zero_v734_handle_apply_step.__get__(self, StepExecutor))
        self.register_handler("apply_patch", _zero_v734_handle_apply_step.__get__(self, StepExecutor))
    except Exception:
        pass


def _zero_v734_read_target_file_for_edit(step, task=None):
    from pathlib import Path

    task_text = str(
        (step.get("task_text") if isinstance(step, dict) else "")
        or (task.get("goal") if isinstance(task, dict) else "")
        or ""
    )
    target_path = _zero_v7_normalize_rel_path(
        (step.get("target_path") if isinstance(step, dict) else "")
        or (step.get("path") if isinstance(step, dict) else "")
        or _zero_v7_extract_workspace_py_path(task_text)
    )
    if not target_path:
        return {"ok": False, "error": "missing_target_path", "target_path": ""}
    if not target_path.startswith("workspace/") or not target_path.endswith(".py"):
        return {"ok": False, "error": "unsafe_target_path", "target_path": target_path}

    project_root = Path.cwd()
    file_path = (project_root / target_path).resolve()
    try:
        file_path.relative_to(project_root.resolve())
    except Exception:
        return {"ok": False, "error": "path_escapes_repo_root", "target_path": target_path}
    if not file_path.exists():
        return {"ok": False, "error": "file_not_found", "target_path": target_path, "full_path": str(file_path)}

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "error": f"read_failed: {exc}", "target_path": target_path, "full_path": str(file_path)}

    return {"ok": True, "target_path": target_path, "full_path": str(file_path), "content": content}


def _zero_v734_extract_function_contract(previous_result=None, step=None, task=None):
    task_text = str(
        (step.get("task_text") if isinstance(step, dict) else "")
        or (task.get("goal") if isinstance(task, dict) else "")
        or ""
    )
    requested = []
    failed = []
    sources = []
    if isinstance(previous_result, dict):
        sources.append(previous_result)
        result = previous_result.get("result")
        if isinstance(result, dict):
            sources.append(result)
            nested = result.get("result")
            if isinstance(nested, dict):
                sources.append(nested)
            verification = result.get("verification")
            if isinstance(verification, dict):
                sources.append(verification)
        verification = previous_result.get("verification")
        if isinstance(verification, dict):
            sources.append(verification)

    if isinstance(task, dict):
        repair_context = task.get("repair_context")
        if isinstance(repair_context, dict):
            sources.append(repair_context)
            verify_result = repair_context.get("verify_result")
            if isinstance(verify_result, dict):
                sources.append(verify_result)
                nested = verify_result.get("result")
                if isinstance(nested, dict):
                    sources.append(nested)

    for source in sources:
        for key in ("requested_functions", "failed_functions"):
            values = source.get(key) if isinstance(source, dict) else None
            if not isinstance(values, list):
                continue
            normalized = [str(item).strip().lower() for item in values if str(item).strip()]
            if key == "requested_functions" and normalized:
                requested.extend(normalized)
            if key == "failed_functions" and normalized:
                failed.extend(normalized)
        verification = source.get("verification") if isinstance(source, dict) else None
        if isinstance(verification, dict):
            for key in ("requested_functions", "failed_functions"):
                values = verification.get(key)
                if not isinstance(values, list):
                    continue
                normalized = [str(item).strip().lower() for item in values if str(item).strip()]
                if key == "requested_functions" and normalized:
                    requested.extend(normalized)
                if key == "failed_functions" and normalized:
                    failed.extend(normalized)

    if not requested:
        requested = _zero_v730_requested_math_functions(task_text)
    requested = list(dict.fromkeys(requested))
    failed = list(dict.fromkeys(failed))
    return {"requested_functions": requested, "failed_functions": failed}


def _zero_v734_build_math_contract_edit_payload(original_text: str, requested_functions):
    requested = [str(item).strip().lower() for item in requested_functions or [] if str(item).strip()]
    supported = [item for item in requested if item in {"add", "multiply"}]
    if not supported:
        return None

    blocks = []
    if "add" in supported:
        blocks.append("def add(a, b):\n    return a + b")
    if "multiply" in supported:
        blocks.append("def multiply(a, b):\n    return a * b")
    new_text = "\n\n".join(blocks) + "\n"

    verification = _zero_v7_verify_math_functions(new_text, supported)
    if not verification.get("ok"):
        return None
    if new_text == str(original_text or ""):
        return None

    return {
        "operation": "replace",
        "old_text": original_text,
        "new_text": new_text,
        "content": new_text,
        "schema": "replacement_pair_v1",
        "requested_functions": supported,
        "failed_functions": list(verification.get("failed_functions") or []),
        "verification": verification,
    }


def _zero_v734_build_python_syntax_edit_payload(original_text: str, requested_functions=None):
    contract_payload = _zero_v734_build_math_contract_edit_payload(original_text, requested_functions)
    if isinstance(contract_payload, dict):
        return contract_payload

    lines = str(original_text or "").splitlines(keepends=True)
    changed = False
    fixed_lines = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^(async\s+def|def)\s+[A-Za-z_][A-Za-z0-9_]*\s*\(.*\)\s*$", stripped):
            newline = "\n" if line.endswith("\n") else ""
            body = line[:-1] if newline else line
            fixed_lines.append(body.rstrip() + ":" + newline)
            changed = True
        else:
            fixed_lines.append(line)

    if not changed:
        return None

    new_text = "".join(fixed_lines)
    try:
        compile(new_text, "<code_chain_repair_candidate>", "exec")
    except Exception:
        return None

    return {
        "operation": "replace",
        "old_text": original_text,
        "new_text": new_text,
        "content": new_text,
        "schema": "replacement_pair_v1",
    }


def _zero_v736_current_strategy(task=None, step=None):
    if isinstance(step, dict) and str(step.get("strategy") or "").strip():
        return str(step.get("strategy")).strip()
    if isinstance(task, dict):
        repair_context = task.get("repair_context")
        if isinstance(repair_context, dict):
            strategy = repair_context.get("strategy")
            if isinstance(strategy, dict) and str(strategy.get("current_strategy") or "").strip():
                return str(strategy.get("current_strategy")).strip()
    return "minimal_patch"


def _zero_v800_requested_contract_is_supported(requested_functions=None):
    requested = [str(item).strip().lower() for item in requested_functions or [] if str(item).strip()]
    supported = [item for item in requested if item in {"add", "multiply"}]
    return bool(supported) and len(supported) == len(list(dict.fromkeys(requested)))


def _zero_v800_build_contract_driven_repair_payload(original_text: str, requested_functions=None):
    """
    ZERO v8.1 Contract-Driven Repair Completion.

    If verification requested a supported function contract, repair must satisfy the
    whole contract, not merely repair the first syntax defect.  This keeps the
    repair payload aligned with the final verify step:

        requested_functions == functions produced by final_edit_payload

    The function remains intentionally narrow for now: it only generates the
    minimal safe math contract currently verified by Code Chain.  Unknown or
    unsupported contracts fall back to the older strategy path instead of making
    uncontrolled guesses.
    """
    requested = [str(item).strip().lower() for item in requested_functions or [] if str(item).strip()]
    requested = list(dict.fromkeys(requested))
    if not requested:
        return None
    if not _zero_v800_requested_contract_is_supported(requested):
        return None
    return _zero_v734_build_math_contract_edit_payload(original_text, requested)


def _zero_v736_build_strategy_edit_payload(original_text: str, requested_functions=None, strategy: str = "minimal_patch"):
    strategy = str(strategy or "minimal_patch").strip()

    # ZERO v8.1: verification contract takes precedence over tactical strategy.
    # If verify says add+multiply are required, even minimal_patch must produce
    # an edit payload that satisfies add+multiply.  Strategy retry is still used
    # for non-contract failures, regression failures, unsupported contracts, or
    # future broader edit modes.
    contract_payload = _zero_v800_build_contract_driven_repair_payload(
        original_text,
        requested_functions=requested_functions,
    )
    if isinstance(contract_payload, dict):
        contract_payload["contract_driven"] = True
        contract_payload["contract_completion"] = {
            "ok": True,
            "requested_functions": list(contract_payload.get("requested_functions") or []),
            "produced_functions": list(contract_payload.get("requested_functions") or []),
            "mode": "supported_math_contract_v1",
        }
        return contract_payload

    if strategy == "minimal_patch":
        return _zero_v734_build_python_syntax_edit_payload(original_text, requested_functions=[])
    if strategy in {"function_rewrite", "full_file_rewrite_safe"}:
        return _zero_v734_build_math_contract_edit_payload(original_text, requested_functions)
    return _zero_v734_build_python_syntax_edit_payload(original_text, requested_functions=requested_functions)


def _zero_v734_validate_edit_payload(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "error": "missing edit payload"}

    file_edits = payload.get("file_edits")
    if not isinstance(file_edits, list):
        file_edits = payload.get("edits")
    if isinstance(file_edits, list) and file_edits:
        normalized = []
        for item in file_edits:
            if not isinstance(item, dict):
                return {"ok": False, "error": "invalid file_edits item"}
            item_validation = _zero_v734_validate_edit_payload({key: value for key, value in item.items() if key not in {"file_edits", "edits"}})
            if not item_validation.get("ok"):
                return {"ok": False, "error": str(item_validation.get("error") or "invalid file edit")}
            target_path = str(item.get("target_path") or item.get("target") or item.get("path") or "").strip()
            if not target_path:
                return {"ok": False, "error": "file_edits item missing target_path"}
            normalized.append({"target_path": target_path, "validation": item_validation, "edit": copy.deepcopy(item)})
        return {"ok": True, "mode": "multi_file", "file_edits": normalized}

    old_text = payload.get("old_text")
    new_text = payload.get("new_text")
    if isinstance(old_text, str) and isinstance(new_text, str) and old_text and new_text and old_text != new_text:
        return {"ok": True, "mode": "replace", "old_text": old_text, "new_text": new_text}

    content = payload.get("content")
    if str(payload.get("operation") or "").strip().lower() == "write_file" and isinstance(content, str) and content:
        return {"ok": True, "mode": "write_file", "content": content}

    return {"ok": False, "error": "missing old_text/new_text replacement pair"}


def _zero_v734_extract_edit_payload(value):
    if not isinstance(value, dict):
        return None

    candidates = [
        value.get("edit_payload"),
        value.get("final_edit_payload"),
        value.get("apply_payload"),
    ]
    result = value.get("result")
    if isinstance(result, dict):
        candidates.extend([result.get("edit_payload"), result.get("final_edit_payload"), result.get("apply_payload")])
        nested = result.get("result")
        if isinstance(nested, dict):
            candidates.extend([nested.get("edit_payload"), nested.get("final_edit_payload"), nested.get("apply_payload")])

    if isinstance(value.get("repair_context"), dict):
        candidates.append(value["repair_context"].get("final_edit_payload"))

    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return None


def _zero_v734_handle_code_chain_repair_step(self, step, task=None, context=None, previous_result=None):
    target = _zero_v734_read_target_file_for_edit(step if isinstance(step, dict) else {}, task=task)
    if target.get("ok"):
        original_text = str(target.get("content") or "")
        contract = _zero_v734_extract_function_contract(previous_result=previous_result, step=step, task=task)
        requested_functions = list(contract.get("requested_functions") or [])
        failed_functions = list(contract.get("failed_functions") or [])
        strategy = _zero_v736_current_strategy(task=task, step=step)
        edit_payload = _zero_v736_build_strategy_edit_payload(original_text, requested_functions=requested_functions, strategy=strategy)
        if isinstance(edit_payload, dict):
            edit_payload["strategy"] = strategy
            target_path = str(target.get("target_path") or "")
            final = f"code chain repair generated edit payload: {target_path}"
            return {
                "ok": True,
                "message": final,
                "final_answer": final,
                "target_path": target_path,
                "original_file_content": original_text,
                "proposed_fix": edit_payload.get("new_text"),
                "requested_functions": requested_functions,
                "failed_functions": failed_functions,
                "strategy": strategy,
                "contract_driven": bool(edit_payload.get("contract_driven", False)),
                "contract_completion": copy.deepcopy(edit_payload.get("contract_completion", {})),
                "edit_payload": copy.deepcopy(edit_payload),
                "final_edit_payload": copy.deepcopy(edit_payload),
                "result": {
                    "planner_autonomous_repair": True,
                    "status": "edit_payload_ready",
                    "target_path": target_path,
                    "original_file_content": original_text,
                    "proposed_fix": edit_payload.get("new_text"),
                    "requested_functions": requested_functions,
                    "failed_functions": failed_functions,
                    "strategy": strategy,
                    "contract_driven": bool(edit_payload.get("contract_driven", False)),
                    "contract_completion": copy.deepcopy(edit_payload.get("contract_completion", {})),
                    "verification": copy.deepcopy(edit_payload.get("verification", {})),
                    "edit_payload": copy.deepcopy(edit_payload),
                    "final_edit_payload": copy.deepcopy(edit_payload),
                    "changed_files": [target_path],
                    "changed_lines": 1,
                },
                "execution_trace": [
                    {
                        "step_type": "code_chain_repair",
                        "ok": True,
                        "message": final,
                        "classification": "repair_edit_payload_schema_v1",
                        "attempts": 1,
                        "max_attempts": 1,
                    }
                ],
            }

    return _ZERO_V734_ORIGINAL_CODE_CHAIN_REPAIR_HANDLER(self, step, task=task, context=context, previous_result=previous_result)


def _zero_v734_resolve_apply_target_path(step, payload):
    target_path = str(
        (step.get("target_path") if isinstance(step, dict) else "")
        or (step.get("target") if isinstance(step, dict) else "")
        or (payload.get("target_path") if isinstance(payload, dict) else "")
        or ""
    ).strip()
    return target_path


def _zero_v735_repo_rel_path(path_text):
    from pathlib import Path

    raw = str(path_text or "").strip().replace("\\", "/")
    if not raw:
        return ""
    try:
        path = Path(raw)
        if path.is_absolute():
            return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except Exception:
        pass
    return raw.lstrip("./")


def _zero_v735_is_repo_source_path(rel_path):
    lowered = _zero_v735_repo_rel_path(rel_path).lower()
    if lowered.startswith("workspace/shared/"):
        return False
    return lowered.startswith(("core/", "services/", "tests/", "runtime/", "tasks/", "planning/"))


def _zero_v735_imported_module_names(rel_path):
    rel = _zero_v735_repo_rel_path(rel_path)
    if not rel.endswith(".py"):
        return set()
    without_ext = rel[:-3]
    parts = [part for part in without_ext.split("/") if part and part != "__init__"]
    names = set()
    if parts:
        names.add(parts[-1])
        for index in range(len(parts)):
            names.add(".".join(parts[index:]))
    return names


def _zero_v735_python_imports(text):
    imports = set()
    for line in str(text or "").splitlines():
        stripped = line.strip()
        match = re.match(r"import\s+(.+)", stripped)
        if match:
            for item in match.group(1).split(","):
                imports.add(item.strip().split(" as ")[0].strip())
            continue
        match = re.match(r"from\s+([A-Za-z0-9_\.]+)\s+import\s+", stripped)
        if match:
            module = match.group(1).strip()
            imports.add(module)
            imported_part = stripped.split(" import ", 1)[1] if " import " in stripped else ""
            for item in imported_part.split(","):
                imported_name = item.strip().split(" as ")[0].strip()
                if imported_name and imported_name != "*":
                    imports.add(imported_name)
                    imports.add(f"{module}.{imported_name}")
    return {item for item in imports if item}


def _zero_v735_find_impacted_files(changed_files):
    return sorted(_zero_v735_dependency_impact(changed_files).get("importers", []))


def _zero_v735_dependency_impact(changed_files):
    from pathlib import Path

    modules = set()
    for changed in changed_files:
        modules.update(_zero_v735_imported_module_names(changed))
    importers = set()
    graph = {}
    if not modules:
        return {"modules": [], "importers": [], "dependency_graph": {}}
    root = Path.cwd()
    for base in ("workspace/shared", "tests", "core"):
        folder = root / base
        if not folder.exists():
            continue
        for path in folder.rglob("*.py"):
            rel = path.relative_to(root).as_posix()
            if rel in changed_files:
                continue
            try:
                imports = _zero_v735_python_imports(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            matched = sorted(
                module
                for imp in imports
                for module in modules
                if imp == module or imp.endswith("." + module) or module.endswith("." + imp)
            )
            if matched:
                importers.add(rel)
                for module in matched:
                    graph.setdefault(module, [])
                    if rel not in graph[module]:
                        graph[module].append(rel)
    return {
        "modules": sorted(modules),
        "importers": sorted(importers),
        "dependency_graph": {key: sorted(value) for key, value in sorted(graph.items())},
    }


def _zero_v735_build_verify_plan(changed_files, impacted_files):
    py_files = [path for path in changed_files if str(path).endswith(".py")]
    impacted_py_files = list(dict.fromkeys(path for path in impacted_files if str(path).endswith(".py")))
    commands = []
    if py_files:
        commands.append("python -m py_compile " + " ".join(py_files))
    if impacted_py_files:
        commands.append("python -m py_compile " + " ".join(impacted_py_files))
    related_tests = [path for path in impacted_files if str(path).startswith("tests/")]
    return {
        "commands": list(dict.fromkeys(commands)),
        "related_tests": related_tests,
        "impacted_files": impacted_py_files,
    }


def _zero_v735_analyze_repo_impact(*, target_path, edit_payload=None, step=None):
    edit_payload = edit_payload if isinstance(edit_payload, dict) else {}
    step = step if isinstance(step, dict) else {}
    changed_files = edit_payload.get("changed_files")
    if not isinstance(changed_files, list) or not changed_files:
        changed_files = step.get("changed_files")
    if not isinstance(changed_files, list) or not changed_files:
        changed_files = [target_path] if target_path else []
    file_edits = edit_payload.get("file_edits")
    if not isinstance(file_edits, list):
        file_edits = edit_payload.get("edits")
    if isinstance(file_edits, list):
        for item in file_edits:
            if isinstance(item, dict):
                item_target = str(item.get("target_path") or item.get("target") or item.get("path") or "").strip()
                if item_target:
                    changed_files.append(item_target)
    changed_files = [_zero_v735_repo_rel_path(path) for path in changed_files if str(path).strip()]
    changed_files = list(dict.fromkeys(changed_files))
    dependency_impact = _zero_v735_dependency_impact(changed_files)
    impacted_files = list(dict.fromkeys(dependency_impact.get("importers", [])))

    source_changes = [path for path in changed_files if _zero_v735_is_repo_source_path(path)]
    core_changes = [
        path for path in changed_files
        if _zero_v735_repo_rel_path(path).lower().startswith(("core/", "runtime/", "tasks/", "planning/"))
    ]
    sensitive = any(
        token in _zero_v735_repo_rel_path(path).lower()
        for path in changed_files
        for token in ("scheduler", "task_runtime", "task_runner", "execution_guard")
    )

    edit_scope = "single_file" if len(changed_files) <= 1 else "multi_file"
    if source_changes and len(changed_files) > 1:
        edit_scope = "repo_scale"

    risk_level = "low"
    requires_confirmation = False
    blocked_reason = ""
    if core_changes:
        risk_level = "medium"
        requires_confirmation = True
        blocked_reason = "repo source apply requires confirmation"
    if len(core_changes) > 1 or sensitive or (source_changes and len(changed_files) > 1):
        risk_level = "high"
        requires_confirmation = True
        blocked_reason = "high-risk repo source apply blocked without confirmation"
    if source_changes and not blocked_reason:
        risk_level = "medium"
        requires_confirmation = True
        blocked_reason = "repo source apply requires confirmation"

    dependency_hints = {
        "imported_module_names": sorted({name for path in changed_files for name in _zero_v735_imported_module_names(path)}),
        "importers": impacted_files,
        "source_changes": source_changes,
    }
    verify_plan = _zero_v735_build_verify_plan(changed_files, impacted_files)
    custom_verify_plan = edit_payload.get("verify_plan")
    if isinstance(custom_verify_plan, dict):
        custom_commands = custom_verify_plan.get("commands")
        if isinstance(custom_commands, list):
            merged = list(verify_plan.get("commands", []))
            merged.extend(str(item).strip() for item in custom_commands if str(item).strip())
            verify_plan["commands"] = list(dict.fromkeys(merged))
    confirmed = bool(step.get("confirmed") or step.get("confirmation") or step.get("repo_scale_confirmed") or step.get("scope_confirmed"))
    auto_apply_allowed = not requires_confirmation or confirmed
    if confirmed:
        blocked_reason = ""

    return {
        "target_path": _zero_v735_repo_rel_path(target_path),
        "changed_files": changed_files,
        "impacted_files": impacted_files,
        "dependency_graph": copy.deepcopy(dependency_impact.get("dependency_graph", {})),
        "dependency_hints": dependency_hints,
        "edit_scope": edit_scope,
        "risk_level": risk_level,
        "requires_confirmation": requires_confirmation,
        "blocked_reason": "" if auto_apply_allowed else blocked_reason,
        "verify_plan": verify_plan,
        "auto_apply_allowed": auto_apply_allowed,
    }


def _zero_v735_atomic_multi_patch_error(
    self,
    *,
    message,
    patch_results,
    changed_files,
    failed_patch_index,
    failed_reason,
    rollback_applied,
    preflight=None,
    transaction=None,
):
    preflight = preflight if isinstance(preflight, dict) else {}
    transaction = transaction if isinstance(transaction, dict) else {}
    return {
        "ok": False,
        "type": "apply_patch",
        "message": message,
        "final_answer": message,
        "transaction_ok": False,
        "preflight_ok": bool(preflight.get("preflight_ok", False)),
        "preflight": copy.deepcopy(preflight),
        "transaction": copy.deepcopy(transaction),
        "atomic": True,
        "rollback_applied": bool(rollback_applied),
        "changed": False,
        "changed_files": list(changed_files or []),
        "patch_results": copy.deepcopy(patch_results or []),
        "failed_patch_index": failed_patch_index,
        "failed_reason": failed_reason,
        "error": {
            "type": "atomic_multi_patch_failed",
            "message": message,
            "retryable": False,
            "details": {
                "atomic": True,
                "preflight": copy.deepcopy(preflight),
                "transaction": copy.deepcopy(transaction),
                "changed_files": list(changed_files or []),
                "patch_results": copy.deepcopy(patch_results or []),
                "failed_patch_index": failed_patch_index,
                "failed_reason": failed_reason,
                "rollback_applied": bool(rollback_applied),
            },
        },
        "result": {
            "transaction_ok": False,
            "preflight_ok": bool(preflight.get("preflight_ok", False)),
            "preflight": copy.deepcopy(preflight),
            "transaction": copy.deepcopy(transaction),
            "atomic": True,
            "rollback_applied": bool(rollback_applied),
            "changed": False,
            "changed_files": list(changed_files or []),
            "patch_results": copy.deepcopy(patch_results or []),
            "failed_patch_index": failed_patch_index,
            "failed_reason": failed_reason,
        },
    }


def _zero_v735_patch_result_field(patch_result, key, default=""):
    if not isinstance(patch_result, dict):
        return default
    if key in patch_result:
        return patch_result.get(key, default)
    nested = patch_result.get("result")
    if isinstance(nested, dict):
        return nested.get(key, default)
    return default


def _zero_v735_atomic_multi_patch_step(self, step, task=None, context=None, previous_result=None):
    patches = step.get("patches") if isinstance(step, dict) else None
    preflight = self._analyze_apply_patch_preflight(step if isinstance(step, dict) else {}, task=task)
    transaction = self._build_apply_patch_transaction(preflight, status="planned")
    if not bool(preflight.get("preflight_ok", False)):
        failed_reason = str(preflight.get("conflict_reason") or "apply_patch preflight failed")
        transaction = self._mark_apply_patch_transaction(transaction, status="blocked", error_reason=failed_reason)
        return _zero_v735_atomic_multi_patch_error(
            self,
            message=failed_reason,
            patch_results=[],
            changed_files=list(preflight.get("changed_files") or []),
            failed_patch_index=None,
            failed_reason=failed_reason,
            rollback_applied=False,
            preflight=preflight,
            transaction=transaction,
        )
    if not isinstance(patches, list) or not patches:
        transaction = self._mark_apply_patch_transaction(transaction, status="blocked", error_reason="apply_patch patches must be a non-empty list")
        return _zero_v735_atomic_multi_patch_error(
            self,
            message="apply_patch patches must be a non-empty list",
            patch_results=[],
            changed_files=list(preflight.get("changed_files") or []),
            failed_patch_index=None,
            failed_reason="apply_patch patches must be a non-empty list",
            rollback_applied=False,
            preflight=preflight,
            transaction=transaction,
        )

    patch_results = []
    changed_files = []
    rollback_applied_any = False
    backup_items = []

    for index, patch_item in enumerate(patches):
        if not isinstance(patch_item, dict):
            failed_reason = "patch item must be an object"
            return _zero_v735_atomic_multi_patch_error(
                self,
                message=failed_reason,
                patch_results=patch_results,
                changed_files=changed_files,
                failed_patch_index=index,
                failed_reason=failed_reason,
                rollback_applied=rollback_applied_any,
                preflight=preflight,
                transaction=self._mark_apply_patch_transaction(transaction, status="failed", error_reason=failed_reason),
            )

        patch_step = copy.deepcopy(step)
        patch_step.pop("patches", None)
        patch_step.update(copy.deepcopy(patch_item))
        patch_step["type"] = "apply_patch"

        patch_result = _ZERO_V734_ORIGINAL_APPLY_UNIFIED_DIFF_STEP(
            self,
            patch_step,
            task=task,
            context=context,
            previous_result=previous_result,
        )
        patch_summary = {
            "patch_index": index,
            "ok": bool(patch_result.get("ok", False)) if isinstance(patch_result, dict) else False,
            "message": patch_result.get("message", "") if isinstance(patch_result, dict) else "invalid patch result",
            "patch_path": _zero_v735_patch_result_field(patch_result, "patch_path", str(patch_item.get("patch_path") or patch_item.get("path") or "")),
            "target_path": _zero_v735_patch_result_field(patch_result, "target_path", str(patch_item.get("target_path") or patch_item.get("target") or "")),
            "full_patch_path": _zero_v735_patch_result_field(patch_result, "full_patch_path", ""),
            "full_target_path": _zero_v735_patch_result_field(patch_result, "full_target_path", ""),
            "backup_path": _zero_v735_patch_result_field(patch_result, "backup_path", ""),
            "transaction_ok": bool(_zero_v735_patch_result_field(patch_result, "transaction_ok", False)),
            "verification_ok": bool(_zero_v735_patch_result_field(patch_result, "verification_ok", False)),
            "rollback_applied": bool(_zero_v735_patch_result_field(patch_result, "rollback_applied", False)),
            "changed": bool(_zero_v735_patch_result_field(patch_result, "changed", False)),
            "result": copy.deepcopy(patch_result),
        }
        patch_results.append(patch_summary)
        if patch_summary.get("backup_path"):
            backup_items.append(
                {
                    "target_path": str(patch_summary.get("target_path") or ""),
                    "full_target_path": str(patch_summary.get("full_target_path") or ""),
                    "backup_path": str(patch_summary.get("backup_path") or ""),
                }
            )
            transaction = self._attach_apply_patch_backup_snapshot(transaction, backup_items)

        if not patch_summary["ok"] or not patch_summary["transaction_ok"]:
            failed_target_path = str(patch_summary.get("target_path") or "").strip()
            if failed_target_path and failed_target_path not in changed_files:
                changed_files.append(failed_target_path)
            for applied in reversed(patch_results[:-1]):
                rollback_applied, _rollback_error = self._rollback_apply_patch_target(
                    str(applied.get("full_target_path") or ""),
                    str(applied.get("backup_path") or ""),
                )
                applied["rollback_applied"] = bool(rollback_applied)
                applied["rollback_error"] = str(_rollback_error or "")
                rollback_applied_any = rollback_applied_any or rollback_applied
            rollback_applied_any = rollback_applied_any or patch_summary["rollback_applied"]
            failed_reason = str(patch_summary.get("message") or "patch failed")
            rollback_items = [
                {
                    "target_path": str(item.get("target_path") or ""),
                    "full_target_path": str(item.get("full_target_path") or ""),
                    "backup_path": str(item.get("backup_path") or ""),
                    "rollback_applied": bool(item.get("rollback_applied")),
                    "rollback_error": str(item.get("rollback_error") or ""),
                }
                for item in patch_results
                if item.get("backup_path")
            ]
            rollback_result = self._build_apply_patch_rollback_result(rollback_items)
            transaction = self._mark_apply_patch_transaction(transaction, status="failed", error_reason=failed_reason, rollback_result=rollback_result)
            return _zero_v735_atomic_multi_patch_error(
                self,
                message=f"atomic multi-file patch failed at index {index}: {failed_reason}",
                patch_results=patch_results,
                changed_files=changed_files,
                failed_patch_index=index,
                failed_reason=failed_reason,
                rollback_applied=rollback_applied_any,
                preflight=preflight,
                transaction=transaction,
            )

        target_path = str(patch_summary.get("target_path") or "").strip()
        if target_path:
            changed_files.append(target_path)

    changed_files = list(dict.fromkeys(changed_files))
    transaction = self._mark_apply_patch_transaction(transaction, status="applied", changed_files=changed_files)
    transaction = self._mark_apply_patch_transaction(transaction, status="verifying", changed_files=changed_files)
    changed_items = [
        {
            "target_path": str(item.get("target_path") or ""),
            "full_target_path": str(item.get("full_target_path") or ""),
            "backup_path": str(item.get("backup_path") or ""),
        }
        for item in patch_results
        if item.get("full_target_path")
    ]
    verification = self._run_apply_patch_verify_boundary(step if isinstance(step, dict) else {}, transaction, changed_items)
    transaction = verification.get("transaction") if isinstance(verification.get("transaction"), dict) else transaction
    if not bool(verification.get("ok", False)):
        rollback_items = []
        rollback_applied_any = False
        for item in reversed(changed_items):
            rollback_applied, rollback_error = self._rollback_apply_patch_target(
                str(item.get("full_target_path") or ""),
                str(item.get("backup_path") or ""),
            )
            rollback_applied_any = rollback_applied_any or rollback_applied
            rollback_items.append(
                {
                    "target_path": str(item.get("target_path") or ""),
                    "full_target_path": str(item.get("full_target_path") or ""),
                    "backup_path": str(item.get("backup_path") or ""),
                    "rollback_applied": rollback_applied,
                    "rollback_error": rollback_error,
                }
            )
        rollback_result = self._build_apply_patch_rollback_result(rollback_items)
        failed_reason = str(verification.get("message") or "multi-file verification failed")
        transaction = self._mark_apply_patch_transaction(
            transaction,
            status="failed",
            error_reason=failed_reason,
            changed_files=changed_files,
            rollback_result=rollback_result,
        )
        return _zero_v735_atomic_multi_patch_error(
            self,
            message=f"atomic multi-file verification failed: {failed_reason}",
            patch_results=patch_results,
            changed_files=changed_files,
            failed_patch_index=None,
            failed_reason=failed_reason,
            rollback_applied=rollback_applied_any,
            preflight=preflight,
            transaction=transaction,
        )

    transaction = self._mark_apply_patch_transaction(transaction, status="committed", changed_files=changed_files)
    return {
        "ok": True,
        "type": "apply_patch",
        "message": f"atomic multi-file patch applied: {len(patch_results)} files",
        "final_answer": f"atomic multi-file patch applied: {len(patch_results)} files",
        "transaction_ok": True,
        "preflight_ok": True,
        "preflight": preflight,
        "transaction": transaction,
        "verification_ok": True,
        "verification": verification,
        "atomic": True,
        "rollback_applied": False,
        "changed": bool(changed_files),
        "changed_files": changed_files,
        "patch_results": copy.deepcopy(patch_results),
        "failed_patch_index": None,
        "failed_reason": "",
        "error": None,
        "result": {
            "transaction_ok": True,
            "preflight_ok": True,
            "preflight": preflight,
            "transaction": transaction,
            "verification_ok": True,
            "verification": verification,
            "atomic": True,
            "rollback_applied": False,
            "changed": bool(changed_files),
            "changed_files": changed_files,
            "patch_results": copy.deepcopy(patch_results),
            "failed_patch_index": None,
            "failed_reason": "",
        },
    }


def _zero_v734_handle_apply_step(self, step, task=None, context=None, previous_result=None):
    patches = step.get("patches") if isinstance(step, dict) else None
    if isinstance(patches, list):
        return _zero_v735_atomic_multi_patch_step(self, step, task=task, context=context, previous_result=previous_result)

    edit_payload = _zero_v734_extract_edit_payload(step if isinstance(step, dict) else {})
    if edit_payload is None:
        edit_payload = _zero_v734_extract_edit_payload(previous_result if isinstance(previous_result, dict) else {})
    if edit_payload is None and isinstance(task, dict):
        repair_context = task.get("repair_context")
        if isinstance(repair_context, dict):
            edit_payload = _zero_v734_extract_edit_payload({"repair_context": repair_context})

    if edit_payload is None:
        has_legacy_patch = bool(str((step or {}).get("patch_path") or (step or {}).get("path") or "").strip())
        if has_legacy_patch:
            return _ZERO_V734_ORIGINAL_APPLY_UNIFIED_DIFF_STEP(self, step, task=task, context=context, previous_result=previous_result)
        message = "missing old_text/new_text replacement pair"
        return self._apply_patch_error("invalid_edit_payload_schema", message, "", _zero_v734_resolve_apply_target_path(step or {}, {}))

    validation = _zero_v734_validate_edit_payload(edit_payload)
    target_path = _zero_v734_resolve_apply_target_path(step or {}, edit_payload)
    if not validation.get("ok"):
        return self._apply_patch_error("invalid_edit_payload_schema", str(validation.get("error") or "invalid edit payload"), "", target_path)
    if not target_path:
        return self._apply_patch_error("validation_error", "apply step missing target_path", "", target_path)

    repo_impact = _zero_v735_analyze_repo_impact(target_path=target_path, edit_payload=edit_payload, step=step)
    is_multi_file_payload = str(validation.get("mode") or "") == "multi_file"
    changed_files = list(repo_impact.get("changed_files") or [])
    shared_changed_files = [path for path in changed_files if str(path).replace("\\", "/").startswith("workspace/shared/")]
    repo_source_changed_files = [path for path in changed_files if _zero_v735_is_repo_source_path(path)]
    if is_multi_file_payload and repo_source_changed_files:
        repo_impact["auto_apply_allowed"] = False
        repo_impact["requires_confirmation"] = True
        repo_impact["risk_level"] = "high"
        repo_impact["blocked_reason"] = "repo source multi-file repair cannot auto apply"
    if is_multi_file_payload and len(shared_changed_files) != len(changed_files):
        repo_impact["auto_apply_allowed"] = False
        repo_impact["requires_confirmation"] = True
        repo_impact["risk_level"] = "high"
        repo_impact["blocked_reason"] = "multi-file auto apply is limited to workspace/shared files"
    if not bool(repo_impact.get("auto_apply_allowed", False)):
        message = str(repo_impact.get("blocked_reason") or "repo source apply blocked without confirmation")
        error = self._apply_patch_error("repo_scope_confirmation_required", message, "", target_path, details={"repo_impact": repo_impact})
        error["repo_impact"] = copy.deepcopy(repo_impact)
        if isinstance(error.get("result"), dict):
            error["result"]["repo_impact"] = copy.deepcopy(repo_impact)
        return error

    if is_multi_file_payload:
        applied_metadata = []
        for item in validation.get("file_edits") or []:
            item_target = _zero_v735_repo_rel_path(item.get("target_path"))
            item_validation = item.get("validation") if isinstance(item.get("validation"), dict) else {}
            try:
                full_target_path = self.resolve_write_path(relative_path=item_target, task=task, default_scope="shared")
                if not os.path.exists(full_target_path):
                    raise FileNotFoundError(f"target file not found: {full_target_path}")
                with open(full_target_path, "r", encoding="utf-8") as fh:
                    original_text = fh.read()
                backup_path = full_target_path + ".bak_edit_payload"
                self._create_apply_patch_backup(full_target_path, backup_path)
                mode = str(item_validation.get("mode") or "")
                if mode == "replace":
                    old_text = str(item_validation.get("old_text") or "")
                    new_text = str(item_validation.get("new_text") or "")
                    if old_text not in original_text:
                        raise ValueError("old_text not found in target file")
                    updated_text = original_text.replace(old_text, new_text, 1)
                else:
                    updated_text = str(item_validation.get("content") or "")
                if updated_text == original_text:
                    raise ValueError("edit payload produced no changes")
                try:
                    with open(full_target_path, "w", encoding="utf-8") as fh:
                        fh.write(updated_text)
                except Exception as write_exc:
                    rollback_applied, rollback_error = self._rollback_apply_patch_target(full_target_path, backup_path)
                    raise RuntimeError(f"write failed: {write_exc}; rollback_applied={rollback_applied}; rollback_error={rollback_error}") from write_exc
                applied_metadata.append(
                    {
                        "target_path": item_target,
                        "full_target_path": full_target_path,
                        "backup_path": backup_path,
                        "transaction_ok": True,
                        "rollback_applied": False,
                        "changed": True,
                        "old_text": original_text,
                        "new_text": updated_text,
                        "schema": str((item.get("edit") or {}).get("schema") or edit_payload.get("schema") or "replacement_pair_v1"),
                        "restore_available": True,
                    }
                )
            except Exception as exc:
                rollback_applied_any = "rollback_applied=True" in str(exc)
                for applied_item in reversed(applied_metadata):
                    rollback_applied, _rollback_error = self._rollback_apply_patch_target(
                        str(applied_item.get("full_target_path") or ""),
                        str(applied_item.get("backup_path") or ""),
                    )
                    rollback_applied_any = rollback_applied_any or rollback_applied
                error = self._apply_patch_error(
                    "multi_file_apply_failed",
                    f"multi-file apply failed for {item_target}: {exc}",
                    "",
                    item_target,
                    backup_path=str((applied_metadata[-1] if applied_metadata else {}).get("backup_path") or ""),
                    rollback_applied=rollback_applied_any,
                    details={"repo_impact": repo_impact, "per_file_rollback_metadata": copy.deepcopy(applied_metadata)},
                )
                error["repo_impact"] = copy.deepcopy(repo_impact)
                error["per_file_rollback_metadata"] = copy.deepcopy(applied_metadata)
                error["rollback_metadata"] = {"restore_available": bool(applied_metadata), "per_file": copy.deepcopy(applied_metadata)}
                if isinstance(error.get("result"), dict):
                    error["result"]["repo_impact"] = copy.deepcopy(repo_impact)
                    error["result"]["per_file_rollback_metadata"] = copy.deepcopy(applied_metadata)
                    error["result"]["rollback_metadata"] = copy.deepcopy(error["rollback_metadata"])
                    error["result"]["transaction_ok"] = False
                    error["result"]["rollback_applied"] = rollback_applied_any
                    error["result"]["changed"] = False
                return error
        first_meta = applied_metadata[0] if applied_metadata else {}
        verification_results = []
        verification_failed = None
        for applied_item in applied_metadata:
            verification = self._verify_apply_patch_target(
                step if isinstance(step, dict) else {},
                str(applied_item.get("full_target_path") or ""),
            )
            verification["target_path"] = applied_item.get("target_path", "")
            verification_results.append(verification)
            if not bool(verification.get("ok", False)) and verification_failed is None:
                verification_failed = verification

        if verification_failed is not None:
            rollback_applied_any = False
            for applied_item in reversed(applied_metadata):
                rollback_applied, _rollback_error = self._rollback_apply_patch_target(
                    str(applied_item.get("full_target_path") or ""),
                    str(applied_item.get("backup_path") or ""),
                )
                rollback_applied_any = rollback_applied_any or rollback_applied
            message = str(verification_failed.get("message") or "multi-file edit verification failed")
            error = self._apply_patch_error(
                "verification_failed",
                message,
                "",
                target_path,
                backup_path=str(first_meta.get("backup_path") or ""),
                rollback_applied=rollback_applied_any,
                changed=False,
                verification_ok=False,
                details={
                    "repo_impact": repo_impact,
                    "verification": verification_failed,
                    "verification_results": verification_results,
                    "per_file_rollback_metadata": copy.deepcopy(applied_metadata),
                },
            )
            error["repo_impact"] = copy.deepcopy(repo_impact)
            error["per_file_rollback_metadata"] = copy.deepcopy(applied_metadata)
            error["rollback_metadata"] = {"restore_available": bool(applied_metadata), "per_file": copy.deepcopy(applied_metadata)}
            if isinstance(error.get("result"), dict):
                error["result"]["repo_impact"] = copy.deepcopy(repo_impact)
                error["result"]["verification_results"] = copy.deepcopy(verification_results)
                error["result"]["per_file_rollback_metadata"] = copy.deepcopy(applied_metadata)
                error["result"]["rollback_metadata"] = copy.deepcopy(error["rollback_metadata"])
            return error

        return {
            "ok": True,
            "type": "apply_patch",
            "target_path": target_path,
            "message": f"multi-file edit payload applied: {len(applied_metadata)} files",
            "final_answer": f"multi-file edit payload applied: {len(applied_metadata)} files",
            "edit_payload": copy.deepcopy(edit_payload),
            "repo_impact": copy.deepcopy(repo_impact),
            "per_file_rollback_metadata": copy.deepcopy(applied_metadata),
            "patch_path": "",
            "backup_path": first_meta.get("backup_path", ""),
            "transaction_ok": True,
            "verification_ok": True,
            "verification": {"ok": True, "verification_ok": True, "results": verification_results},
            "rollback_applied": False,
            "changed": True,
            "rollback_metadata": {
                "target_path": first_meta.get("target_path", target_path),
                "full_target_path": first_meta.get("full_target_path", ""),
                "backup_path": first_meta.get("backup_path", ""),
                "restore_available": bool(applied_metadata),
                "per_file": copy.deepcopy(applied_metadata),
            },
            "result": {
                "target_path": target_path,
                "patch_path": "",
                "backup_path": first_meta.get("backup_path", ""),
                "transaction_ok": True,
                "verification_ok": True,
                "verification": {"ok": True, "verification_ok": True, "results": verification_results},
                "rollback_applied": False,
                "changed": True,
                "applied": True,
                "edit_payload": copy.deepcopy(edit_payload),
                "repo_impact": copy.deepcopy(repo_impact),
                "per_file_rollback_metadata": copy.deepcopy(applied_metadata),
                "rollback_metadata": {
                    "target_path": first_meta.get("target_path", target_path),
                    "full_target_path": first_meta.get("full_target_path", ""),
                    "backup_path": first_meta.get("backup_path", ""),
                    "restore_available": bool(applied_metadata),
                    "per_file": copy.deepcopy(applied_metadata),
                },
            },
            "error": None,
        }

    try:
        full_target_path = self.resolve_write_path(relative_path=target_path, task=task, default_scope="shared")
    except Exception as exc:
        return self._apply_patch_error("path_resolve_failed", f"apply edit path resolve failed: {exc}", "", target_path)
    if not os.path.exists(full_target_path):
        return self._apply_patch_error("file_not_found", f"target file not found: {full_target_path}", "", target_path, full_target_path=full_target_path)

    try:
        with open(full_target_path, "r", encoding="utf-8") as fh:
            original_text = fh.read()
    except Exception as exc:
        return self._apply_patch_error("read_failed", f"apply edit read failed: {exc}", "", target_path, full_target_path=full_target_path)

    backup_path = full_target_path + ".bak_edit_payload"
    try:
        self._create_apply_patch_backup(full_target_path, backup_path)
    except Exception as exc:
        return self._apply_patch_error("backup_failed", f"apply edit backup failed: {exc}", "", target_path, full_target_path=full_target_path, backup_path=backup_path)

    mode = str(validation.get("mode") or "")
    if mode == "replace":
        old_text = str(validation.get("old_text") or "")
        new_text = str(validation.get("new_text") or "")
        if old_text not in original_text:
            return self._apply_patch_error("old_text_not_found", "old_text not found in target file", "", target_path, full_target_path=full_target_path, backup_path=backup_path)
        updated_text = original_text.replace(old_text, new_text, 1)
    else:
        updated_text = str(validation.get("content") or "")

    if updated_text == original_text:
        return self._apply_patch_error("patch_no_change", "edit payload produced no changes", "", target_path, full_target_path=full_target_path, backup_path=backup_path)

    try:
        with open(full_target_path, "w", encoding="utf-8") as fh:
            fh.write(updated_text)
    except Exception as exc:
        rollback_applied, rollback_error = self._rollback_apply_patch_target(full_target_path, backup_path)
        return self._apply_patch_error(
            "write_failed",
            f"apply edit write failed: {exc}",
            "",
            target_path,
            full_target_path=full_target_path,
            backup_path=backup_path,
            rollback_applied=rollback_applied,
            details={"backup_path": backup_path, "rollback_error": rollback_error},
        )

    verification = self._verify_apply_patch_target(step if isinstance(step, dict) else {}, full_target_path)
    if not bool(verification.get("ok", False)):
        rollback_applied, rollback_error = self._rollback_apply_patch_target(full_target_path, backup_path)
        message = str(verification.get("message") or "apply edit verification failed")
        return self._apply_patch_error(
            "verification_failed",
            message,
            "",
            target_path,
            full_target_path=full_target_path,
            backup_path=backup_path,
            rollback_applied=rollback_applied,
            changed=False,
            verification_ok=False,
            details={"backup_path": backup_path, "verification": verification, "rollback_error": rollback_error},
        )

    return {
        "ok": True,
        "type": "apply_patch",
        "target_path": target_path,
        "full_target_path": full_target_path,
        "backup_path": backup_path,
        "patch_path": "",
        "transaction_ok": True,
        "verification_ok": True,
        "verification": verification,
        "rollback_applied": False,
        "changed": True,
        "message": f"edit payload applied: {target_path}",
        "final_answer": f"edit payload applied: {target_path}",
        "edit_payload": copy.deepcopy(edit_payload),
        "repo_impact": copy.deepcopy(repo_impact),
        "rollback_metadata": {
            "target_path": target_path,
            "full_target_path": full_target_path,
            "backup_path": backup_path,
            "old_text": original_text,
            "new_text": updated_text,
            "schema": str(edit_payload.get("schema") or "replacement_pair_v1"),
            "restore_available": True,
        },
        "result": {
            "patch_path": "",
            "target_path": target_path,
            "full_target_path": full_target_path,
            "backup_path": backup_path,
            "transaction_ok": True,
            "verification_ok": True,
            "verification": verification,
            "rollback_applied": False,
            "changed": True,
            "applied": True,
            "edit_payload": copy.deepcopy(edit_payload),
            "repo_impact": copy.deepcopy(repo_impact),
            "old_text": edit_payload.get("old_text"),
            "new_text": edit_payload.get("new_text"),
            "rollback_metadata": {
                "target_path": target_path,
                "full_target_path": full_target_path,
                "backup_path": backup_path,
                "old_text": original_text,
                "new_text": updated_text,
                "schema": str(edit_payload.get("schema") or "replacement_pair_v1"),
                "restore_available": True,
            },
        },
        "error": None,
    }


StepExecutor.__init__ = _zero_v734_step_executor_init
