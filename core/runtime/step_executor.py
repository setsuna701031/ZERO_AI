from __future__ import annotations

import copy
import json
import os
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
        self.register_handler("read_file", ReadFileStepHandler(self).handle)
        self.register_handler("workspace_read", ReadFileStepHandler(self).handle)
        self.register_handler("ensure_file", EnsureFileStepHandler(self).handle)
        self.register_handler("verify", VerifyStepHandler(self).handle)
        self.register_handler("verify_file", VerifyStepHandler(self).handle)
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
            for key in ("workspace", "cwd", "task_dir", "sandbox_dir", "file_content"):
                if key not in merged and key in context:
                    merged[key] = context.get(key)

        if step_index is not None and "step_index" not in merged:
            merged["step_index"] = step_index

        if step_count is not None and "step_count" not in merged:
            merged["step_count"] = step_count

        return merged

    def _normalize_step_payload(self, step: Dict[str, Any]) -> Dict[str, Any]:
        payload = copy.deepcopy(step or {})

        step_type = str(payload.get("type") or "unknown").strip().lower()
        payload["type"] = step_type

        if "step_index" in payload:
            payload["step_index"] = self._safe_int(payload.get("step_index"), payload.get("step_index"))

        if "step_count" in payload:
            payload["step_count"] = self._safe_int(payload.get("step_count"), payload.get("step_count"))

        if step_type in {"read_file", "write_file", "ensure_file", "run_python", "verify", "verify_file"}:
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

        if step_type == "write_file":
            payload["content"] = str(payload.get("content") or "")

        if "scope" in payload and payload["scope"] is not None:
            payload["scope"] = str(payload.get("scope") or "")

        if "attempt" in payload:
            payload["attempt"] = self._safe_int(payload.get("attempt"), payload.get("attempt"))

        if "max_attempts" in payload:
            payload["max_attempts"] = self._safe_int(payload.get("max_attempts"), payload.get("max_attempts"))

        return payload

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
        return {
            "ok": False,
            "step_type": step_type,
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

        if step_type == "read_file":
            path = str(result.get("path") or "").strip()
            return f"已讀取檔案：{path}" if path else "已讀取檔案"

        if step_type in {"verify", "verify_file"} and ok:
            return "verify ok"

        if step_type == "command" and ok:
            return "command executed successfully"

        if step_type in {"llm", "llm_generate"} and ok:
            return "LLM 已完成回應"

        if not ok:
            error = result.get("error")
            if isinstance(error, dict):
                msg = error.get("message")
                if isinstance(msg, str) and msg.strip():
                    return msg.strip()
            if isinstance(error, str) and error.strip():
                return error.strip()
            return "step failed"

        return "執行完成"

    def _extract_final_answer_from_inner_result(
        self,
        result: Dict[str, Any],
        step_type: str,
        ok: bool,
    ) -> str:
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
        llm_text = self._call_llm(prompt)

        return {
            "ok": True,
            "type": "llm",
            "mode": str(step.get("mode") or ""),
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
        if depth > 8:
            return ""

        if payload is None:
            return ""

        if isinstance(payload, str):
            return payload

        if isinstance(payload, dict):
            for key in ("text", "content", "message", "response", "final_answer", "stdout", "output_text", "summary_text"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value

            for nested_key in ("result", "raw", "data", "payload", "output"):
                nested = payload.get(nested_key)
                text = self._extract_text_deep(nested, depth + 1)
                if text:
                    return text

        if isinstance(payload, list):
            for item in reversed(payload):
                text = self._extract_text_deep(item, depth + 1)
                if text:
                    return text

        return ""

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

        event: Dict[str, Any] = {
            "step_index": result.get("step_index"),
            "step_type": step_type,
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
        normalized["execution_trace"] = self._build_execution_trace(step, normalized)

        if isinstance(normalized.get("result"), dict):
            normalized["result"]["execution_trace"] = copy.deepcopy(normalized["execution_trace"])

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