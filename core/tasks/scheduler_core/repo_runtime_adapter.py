from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional


def repo_runtime_adapter_ok(payload: Dict[str, Any]) -> bool:
    if "ok" in payload:
        return bool(payload.get("ok"))

    status = str(payload.get("status") or "").strip().lower()
    if status in {"failed", "error", "cancelled"}:
        return False

    if payload.get("last_error") or payload.get("failure_message"):
        return False

    return True


def repo_runtime_adapter_error_text(payload: Dict[str, Any]) -> str:
    for key in ("last_error", "failure_message", "error_text", "error"):
        value = payload.get(key)
        if isinstance(value, dict):
            message = value.get("message") or value.get("error") or value.get("text")
            if message is not None and str(message).strip():
                return str(message).strip()
        elif value is not None and str(value).strip():
            return str(value).strip()
    return ""


def repo_runtime_adapter_message(payload: Dict[str, Any], *, ok: bool) -> str:
    for key in ("message", "summary", "final_answer"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    if not ok:
        return repo_runtime_adapter_error_text(payload) or "runtime state failed"

    return "runtime state ok"


def repo_runtime_adapter_final_answer(payload: Dict[str, Any], *, message: str) -> str:
    value = payload.get("final_answer")
    if value is not None and str(value).strip():
        return str(value).strip()
    return message


def repo_runtime_adapter_error_type(payload: Dict[str, Any]) -> str:
    for key in ("failure_type", "error_type"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    error = payload.get("error")
    if isinstance(error, dict):
        for key in ("type", "error_type", "code"):
            value = error.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()

    return "runtime_state_failed" if repo_runtime_adapter_error_text(payload) else ""


def repo_runtime_adapter_runtime_mode(payload: Dict[str, Any]) -> str:
    for key in ("runtime_mode", "mode", "execution_mode"):
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return "repo_state"


def repo_runtime_adapter_last_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("last_result", "last_step_result", "runner_result"):
        value = payload.get(key)
        if isinstance(value, dict):
            return copy.deepcopy(value)
    return {}


def repo_runtime_adapter_execution_trace(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    trace = payload.get("execution_trace")
    if isinstance(trace, list):
        return copy.deepcopy(trace)

    for key in ("last_result", "last_step_result", "runner_result"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            nested_trace = nested.get("execution_trace")
            if isinstance(nested_trace, list):
                return copy.deepcopy(nested_trace)

    return []


def attach_repo_runtime_state_adapter_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    if isinstance(payload.get("adapter_payload"), dict):
        return payload

    ok = repo_runtime_adapter_ok(payload)
    message = repo_runtime_adapter_message(payload, ok=ok)
    final_answer = repo_runtime_adapter_final_answer(payload, message=message)

    adapter_payload = {
        "ok": ok,
        "message": message,
        "final_answer": final_answer,
        "text": final_answer or message,
        "error_text": "" if ok else repo_runtime_adapter_error_text(payload),
        "error_type": "" if ok else repo_runtime_adapter_error_type(payload),
        "runtime_mode": repo_runtime_adapter_runtime_mode(payload),
        "last_result": repo_runtime_adapter_last_result(payload),
        "execution_trace": repo_runtime_adapter_execution_trace(payload),
        "raw": copy.deepcopy(payload),
    }

    payload["adapter_payload"] = adapter_payload
    return payload


def build_repo_runtime_state_adapter_payload(
    *,
    merged: Dict[str, Any],
    runner_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    merged_payload = copy.deepcopy(merged) if isinstance(merged, dict) else {}
    runner_payload = copy.deepcopy(runner_result) if isinstance(runner_result, dict) else {}

    if isinstance(runner_payload.get("adapter_payload"), dict):
        adapter = copy.deepcopy(runner_payload["adapter_payload"])
        merged_payload["adapter_payload"] = adapter
        return merged_payload

    status = str(merged_payload.get("status") or "").strip().lower()
    runner_ok = runner_payload.get("ok") if isinstance(runner_payload, dict) else None

    if runner_ok is not None:
        ok = bool(runner_ok)
    elif status in {"failed", "error", "cancelled"}:
        ok = False
    else:
        ok = True

    message = str(
        merged_payload.get("message")
        or runner_payload.get("message")
        or merged_payload.get("final_answer")
        or runner_payload.get("final_answer")
        or ("runtime state ok" if ok else "runtime state failed")
    )

    final_answer = str(
        merged_payload.get("final_answer")
        or runner_payload.get("final_answer")
        or message
    )

    error_text = str(
        merged_payload.get("last_error")
        or merged_payload.get("failure_message")
        or runner_payload.get("error")
        or ""
    )

    error_type = str(
        merged_payload.get("failure_type")
        or runner_payload.get("error_type")
        or ""
    )

    execution_trace = []
    for source in (runner_payload, merged_payload):
        trace = source.get("execution_trace") if isinstance(source, dict) else None
        if isinstance(trace, list):
            execution_trace = copy.deepcopy(trace)
            break

    last_result = {}
    for source in (runner_payload, merged_payload):
        candidate = source.get("last_result") if isinstance(source, dict) else None
        if isinstance(candidate, dict):
            last_result = copy.deepcopy(candidate)
            break
        candidate = source.get("last_step_result") if isinstance(source, dict) else None
        if isinstance(candidate, dict):
            last_result = copy.deepcopy(candidate)
            break

    merged_payload["adapter_payload"] = {
        "ok": ok,
        "message": message,
        "final_answer": final_answer,
        "text": final_answer or message,
        "error_text": "" if ok else error_text,
        "error_type": "" if ok else (error_type or "runtime_state_failed"),
        "runtime_mode": str(merged_payload.get("runtime_mode") or runner_payload.get("runtime_mode") or "repo_state"),
        "last_result": last_result,
        "execution_trace": execution_trace,
        "raw": copy.deepcopy(merged_payload),
    }
    return merged_payload
