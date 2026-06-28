from __future__ import annotations

import copy
from typing import Any, Dict, Optional

from core.tasks.scheduler_core.llm_step_contract import (
    build_llm_contract_request,
    llm_contract_error,
    llm_contract_metadata,
    normalize_llm_mode,
)


_TEXT_KEYS = (
    "text",
    "content",
    "message",
    "response",
    "final_answer",
    "stdout",
    "checked_text",
    "summary",
    "summary_text",
    "output_text",
)


def _extract_text_deep(payload: Any, depth: int = 0) -> str:
    if depth > 8:
        return ""

    if payload is None:
        return ""

    if isinstance(payload, str):
        return payload

    if isinstance(payload, dict):
        for key in _TEXT_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value

        for nested_key in ("result", "raw", "data", "payload"):
            nested = payload.get(nested_key)
            text = _extract_text_deep(nested, depth + 1)
            if text.strip():
                return text

    if isinstance(payload, list):
        for item in reversed(payload):
            text = _extract_text_deep(item, depth + 1)
            if text.strip():
                return text

    return ""


def _render_prompt(prompt_template: str, input_text: str) -> str:
    return str(prompt_template or "").replace("{{file_content}}", str(input_text or ""))


def _contract_input_text(step: Dict[str, Any]) -> str:
    for key in ("input_text", "file_content", "source_text"):
        value = step.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _input_binding_for_step(step: Dict[str, Any]) -> str:
    explicit_binding = str(step.get("input_binding") or step.get("declared_input") or "").strip()
    if explicit_binding:
        return explicit_binding
    return ""


def _requires_contract_input(prompt_template: str, step: Dict[str, Any]) -> bool:
    if "{{file_content}}" in str(prompt_template or ""):
        return True
    template_fields = step.get("template_fields")
    required_features = step.get("required_runtime_features")
    return (
        isinstance(template_fields, list)
        and "prompt" in template_fields
        and isinstance(required_features, list)
        and "template_substitution" in required_features
    )


def _contract_step(step: Dict[str, Any], request: Dict[str, Any]) -> Dict[str, Any]:
    contract_step = copy.deepcopy(step)
    contract_step.update(
        {
            "prompt": request["prompt"],
            "prompt_template": request["prompt_template"],
            "input_text": request["input_text"],
            "input_binding": request["input_binding"],
            "declared_input": request["declared_input"],
            "llm_contract_version": request["llm_contract_version"],
            "runtime_contract_version": request["runtime_contract_version"],
            "llm_mode": request["llm_mode"],
        }
    )
    return contract_step


def _has_undeclared_deterministic_result(payload: Any, step: Dict[str, Any]) -> bool:
    declared_path = str(
        step.get("llm_execution_path")
        or step.get("execution_path")
        or step.get("declared_llm_path")
        or ""
    ).strip().lower()
    deterministic_declared = declared_path in {"deterministic", "deterministic_summary"}
    if deterministic_declared:
        return False

    if isinstance(payload, dict):
        if bool(payload.get("deterministic_summary_fast_path") or payload.get("llm_skipped")):
            return True
        for key in ("result", "raw", "data", "payload", "adapter_payload"):
            if _has_undeclared_deterministic_result(payload.get(key), step):
                return True
    return False


def _normalize_backend_failure(
    *,
    step: Dict[str, Any],
    mode: str,
    input_binding: str,
    backend_result: Dict[str, Any],
) -> Dict[str, Any]:
    error = backend_result.get("error") if isinstance(backend_result.get("error"), dict) else {}
    error_type = str(error.get("type") or backend_result.get("error_type") or "llm_contract_mismatch")
    message = str(
        error.get("message")
        or backend_result.get("message")
        or backend_result.get("final_answer")
        or "llm backend returned a failed result"
    )
    if error_type in {"llm_client_missing", "llm_client_method_missing", "llm_step_exception"}:
        error_type = "llm_contract_mismatch"
    return llm_contract_error(
        step=step,
        mode=mode,
        input_binding=input_binding,
        error_type=error_type,
        message=message,
    )


def _execute_llm_backend(
    *,
    scheduler: Any,
    task: Dict[str, Any],
    step: Dict[str, Any],
    request: Dict[str, Any],
    mode: str,
    input_binding: str,
    input_text: str,
) -> Dict[str, Any]:
    step_executor = getattr(scheduler, "step_executor", None)
    execute_step = getattr(step_executor, "execute_step", None) if step_executor is not None else None
    if not callable(execute_step):
        return llm_contract_error(
            step=step,
            mode=mode,
            input_binding=input_binding,
            error_type="llm_contract_mismatch",
            message="llm backend must expose execute_step with structured step, task, context, step_index, and step_count",
        )

    return execute_step(
        step=_contract_step(step, request),
        task=task,
        context={
            "llm_contract": copy.deepcopy(request),
            "file_content": input_text,
            "input_text": input_text,
        },
        step_index=int((task or {}).get("current_step_index", 0) or 0) if isinstance(task, dict) else 0,
        step_count=len((task or {}).get("steps", [])) if isinstance((task or {}).get("steps", []), list) else 1,
    )


def _validate_llm_backend_result(
    *,
    step: Dict[str, Any],
    mode: str,
    input_binding: str,
    backend_result: Any,
) -> Dict[str, Any]:
    if not isinstance(backend_result, dict):
        return llm_contract_error(
            step=step,
            mode=mode,
            input_binding=input_binding,
            error_type="llm_contract_mismatch",
            message="llm backend must return a structured result object",
        )

    if _has_undeclared_deterministic_result(backend_result, step):
        return llm_contract_error(
            step=step,
            mode=mode,
            input_binding=input_binding,
            error_type="llm_contract_mismatch",
            message="deterministic llm path must be explicitly declared by the step contract",
        )

    if not bool(backend_result.get("ok", False)):
        return _normalize_backend_failure(
            step=step,
            mode=mode,
            input_binding=input_binding,
            backend_result=backend_result,
        )

    final_text = _extract_text_deep(backend_result)
    if not final_text.strip():
        return llm_contract_error(
            step=step,
            mode=mode,
            input_binding=input_binding,
            error_type="llm_empty_output",
            message="llm backend returned empty output",
        )

    return {
        "ok": True,
        "final_text": final_text,
        "backend_result": backend_result,
    }


def _build_llm_success_payload(
    *,
    step: Dict[str, Any],
    step_type: str,
    mode: str,
    input_binding: str,
    prompt: str,
    prompt_template: str,
    input_text: str,
    final_text: str,
    backend_result: Dict[str, Any],
) -> Dict[str, Any]:
    result_payload = copy.deepcopy(backend_result)
    result_payload.update(llm_contract_metadata(step, mode=mode, input_binding=input_binding))

    return {
        "ok": True,
        "type": step_type,
        "action": "llm",
        "mode": mode,
        "llm_mode": mode,
        "prompt": prompt,
        "prompt_template": prompt_template,
        "input_text": input_text,
        "text": final_text,
        "content": final_text,
        "message": final_text,
        "final_answer": final_text,
        "result": result_payload,
        "error": None,
        **llm_contract_metadata(step, mode=mode, input_binding=input_binding),
    }


def execute_llm_step(
    scheduler: Any,
    task: Dict[str, Any],
    step: Dict[str, Any],
    step_type: str,
) -> Optional[Dict[str, Any]]:
    if step_type not in {"llm", "llm_generate"}:
        return None

    safe_step = step if isinstance(step, dict) else {}
    mode = normalize_llm_mode(safe_step.get("mode"))
    input_text = _contract_input_text(safe_step)
    input_binding = _input_binding_for_step(safe_step)
    prompt_template = str(safe_step.get("prompt_template") or safe_step.get("prompt") or "").strip()
    prompt = _render_prompt(prompt_template, input_text)

    if _requires_contract_input(prompt_template, safe_step) and not input_text.strip():
        return llm_contract_error(
            step=safe_step,
            mode=mode,
            input_binding=input_binding,
            error_type="llm_contract_mismatch",
            message="llm prompt requires contract input but no input text was provided",
        )

    if not prompt:
        return llm_contract_error(
            step=safe_step,
            mode=mode,
            input_binding=input_binding,
            error_type="llm_contract_mismatch",
            message="llm prompt is required",
        )

    request = build_llm_contract_request(
        step=safe_step,
        prompt=prompt,
        prompt_template=prompt_template,
        input_text=input_text,
        mode=mode,
        input_binding=input_binding,
    )

    backend_result = _execute_llm_backend(
        scheduler=scheduler,
        task=task,
        step=safe_step,
        request=request,
        mode=mode,
        input_binding=input_binding,
        input_text=input_text,
    )

    validation = _validate_llm_backend_result(
        step=safe_step,
        mode=mode,
        input_binding=input_binding,
        backend_result=backend_result,
    )
    if validation.get("ok") is not True:
        return validation

    return _build_llm_success_payload(
        step=safe_step,
        step_type=step_type,
        mode=mode,
        input_binding=input_binding,
        prompt=prompt,
        prompt_template=prompt_template,
        input_text=input_text,
        final_text=str(validation.get("final_text") or ""),
        backend_result=validation.get("backend_result") if isinstance(validation.get("backend_result"), dict) else {},
    )
