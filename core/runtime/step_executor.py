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

        # 直接由 StepExecutor 自己處理，避免外部 handler 吃掉 file_content
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

        normalized_task = self._normalize_task(task)
        normalized_context = copy.deepcopy(context) if isinstance(context, dict) else {}
        normalized_steps = [self._normalize_step_payload(copy.deepcopy(step or {})) for step in (steps or [])]

        for zero_based_index, raw_step in enumerate(normalized_steps):
            one_based_index = zero_based_index + 1

            result = self.execute_step(
                step=raw_step,
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
                    # 維持既有測試契約：這兩個欄位用 0-based
                    "completed_steps": zero_based_index,
                    "failed_step": zero_based_index,
                    "results": results,
                    "last_result": copy.deepcopy(result),
                    "error": copy.deepcopy(result.get("error")),
                }

        last_result = copy.deepcopy(results[-1]) if results else None
        return {
            "ok": True,
            "summary": "all steps executed",
            "message": self._extract_step_message(last_result, failed=False) if isinstance(last_result, dict) else "執行完成",
            "final_answer": self._extract_step_final_answer(last_result, failed=False) if isinstance(last_result, dict) else "執行完成",
            "step_count": total_steps,
            # success case 維持舊語意：完成數量 = 總步數
            "completed_steps": total_steps,
            "failed_step": None,
            "results": results,
            "last_result": last_result,
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

        return payload

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
        task_id = self._extract_task_id(task)
        message = self._extract_message_from_inner_result(inner_result, step_type=step_type, ok=ok)
        final_answer = self._extract_final_answer_from_inner_result(inner_result, step_type=step_type, ok=ok)

        if ok:
            return {
                "ok": True,
                "step_type": step_type,
                "step_index": step.get("step_index"),
                "step_count": step.get("step_count"),
                "task_id": task_id,
                "step": copy.deepcopy(step),
                "result": inner_result,
                "message": message,
                "final_answer": final_answer,
                "error": None,
            }

        error_payload = self._extract_error_payload(inner_result)
        if not error_payload.get("message") and message:
            error_payload["message"] = message

        return {
            "ok": False,
            "step_type": step_type,
            "step_index": step.get("step_index"),
            "step_count": step.get("step_count"),
            "task_id": task_id,
            "step": copy.deepcopy(step),
            "result": inner_result,
            "message": message or error_payload.get("message") or "step failed",
            "final_answer": final_answer or error_payload.get("message") or "step failed",
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
        for key in ("message", "content", "text", "response", "answer", "final_answer"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        nested_result = result.get("result")
        if isinstance(nested_result, dict):
            for key in ("message", "content", "text", "response", "answer", "final_answer"):
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
            return "命令執行完成"

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
        for key in ("final_answer", "answer", "response", "message", "content", "text"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        nested_result = result.get("result")
        if isinstance(nested_result, dict):
            for key in ("final_answer", "answer", "response", "message", "content", "text"):
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

    # ============================================================
    # LLM helpers
    # ============================================================

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
            for key in ("text", "content", "message", "response", "final_answer", "stdout"):
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

    def _safe_int(self, value: Any, default: Any = 0) -> Any:
        try:
            return int(value)
        except Exception:
            return default