from __future__ import annotations

import copy
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from core.runtime.task_runner_engineering_action_runtime_helpers import stringify_failure_message


def ensure_step_execution_trace(
    *,
    step: Optional[Dict[str, Any]],
    step_result: Dict[str, Any],
    step_index: int,
    safe_int: Callable[[Any, int], int],
) -> Dict[str, Any]:
    normalized = copy.deepcopy(step_result)

    existing_trace = normalized.get("execution_trace")
    if isinstance(existing_trace, list):
        normalized["execution_trace"] = [copy.deepcopy(item) for item in existing_trace if isinstance(item, dict)]
        return normalized

    safe_step = copy.deepcopy(step) if isinstance(step, dict) else {}
    error_payload = normalized.get("error") if isinstance(normalized.get("error"), dict) else {}
    error_details = error_payload.get("details") if isinstance(error_payload.get("details"), dict) else {}
    retry_payload = normalized.get("retry") if isinstance(normalized.get("retry"), dict) else {}

    event: Dict[str, Any] = {
        "step_index": safe_int(normalized.get("step_index", step_index), step_index),
        "step_type": str(
            normalized.get("step_type")
            or safe_step.get("type")
            or ""
        ).strip().lower(),
        "ok": bool(normalized.get("ok", False)),
        "message": str(normalized.get("message") or ""),
        "final_answer": str(normalized.get("final_answer") or ""),
        "error_type": str(error_payload.get("type") or ""),
        "classification": error_details.get("classification"),
        "attempts": safe_int(retry_payload.get("attempts", 1), 1),
        "max_attempts": safe_int(retry_payload.get("max_attempts", 1), 1),
        "retry_used": bool(retry_payload.get("used", False)),
    }

    step_payload = normalized.get("step") if isinstance(normalized.get("step"), dict) else safe_step
    if isinstance(step_payload, dict):
        step_id = str(step_payload.get("id") or "").strip()
        if step_id:
            event["step_id"] = step_id

    normalized["execution_trace"] = [event]

    if isinstance(normalized.get("result"), dict):
        normalized["result"]["execution_trace"] = copy.deepcopy(normalized["execution_trace"])

    return normalized


def extract_trace_from_step_result(step_result: Any) -> List[Dict[str, Any]]:
    if not isinstance(step_result, dict):
        return []

    trace = step_result.get("execution_trace")
    if isinstance(trace, list):
        return [copy.deepcopy(item) for item in trace if isinstance(item, dict)]

    result_payload = step_result.get("result")
    if isinstance(result_payload, dict):
        nested_trace = result_payload.get("execution_trace")
        if isinstance(nested_trace, list):
            return [copy.deepcopy(item) for item in nested_trace if isinstance(item, dict)]

    return []


def persist_step_result_to_runtime_state(
    *,
    runtime: Any,
    task: Dict[str, Any],
    state: Dict[str, Any],
    step: Optional[Dict[str, Any]],
    step_result: Dict[str, Any],
    current_tick: int,
    safe_int: Callable[[Any, int], int],
    ensure_execution_trace_defaults: Callable[[Dict[str, Any], Dict[str, Any]], None],
    sync_runtime_state_back_to_task: Callable[[Dict[str, Any], Dict[str, Any]], None],
) -> Dict[str, Any]:
    ensure_execution_trace_defaults(task, state)

    results = state.setdefault("results", [])
    if not isinstance(results, list):
        results = []
        state["results"] = results

    step_results = state.setdefault("step_results", [])
    if not isinstance(step_results, list):
        step_results = []
        state["step_results"] = step_results

    execution_log = state.setdefault("execution_log", [])
    if not isinstance(execution_log, list):
        execution_log = []
        state["execution_log"] = execution_log

    execution_trace = state.setdefault("execution_trace", [])
    if not isinstance(execution_trace, list):
        execution_trace = []
        state["execution_trace"] = execution_trace

    record = {
        "step_index": safe_int(
            step_result.get("step_index", state.get("current_step_index", 0)),
            safe_int(state.get("current_step_index", 0), 0),
        ),
        "step": copy.deepcopy(step) if isinstance(step, dict) else None,
        "result": copy.deepcopy(step_result),
        "tick": current_tick,
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    results.append(copy.deepcopy(record))
    step_results.append(copy.deepcopy(record))
    execution_log.append(copy.deepcopy(record))

    incoming_trace = extract_trace_from_step_result(step_result)
    if incoming_trace:
        execution_trace.extend(copy.deepcopy(incoming_trace))

    state["last_step_result"] = copy.deepcopy(step_result)
    state["last_error"] = stringify_failure_message(step_result.get("error"))

    result_payload = step_result.get("result")
    if isinstance(result_payload, dict):
        for key in ("message", "content", "text", "final_answer", "stdout"):
            value = result_payload.get(key)
            if isinstance(value, str) and value.strip():
                state["last_output"] = value.strip()
                break

    if not state.get("last_output"):
        for key in ("message", "content", "text", "final_answer", "stdout"):
            value = step_result.get(key)
            if isinstance(value, str) and value.strip():
                state["last_output"] = value.strip()
                break

    state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state = runtime.save_runtime_state(task, state)
    sync_runtime_state_back_to_task(task, state)
    return state


def trace_tick_for_step(
    *,
    state: Optional[Dict[str, Any]],
    step_index: int,
    current_tick: int,
    safe_int: Callable[[Any, int], int],
) -> int:
    """Return a stable task-local tick for trace.json events."""
    _ = safe_int
    try:
        idx = int(step_index)
        if idx >= 0:
            return idx + 1
    except Exception:
        pass

    if isinstance(state, dict):
        try:
            idx = int(state.get("current_step_index", 0) or 0)
            if idx >= 0:
                return idx + 1
        except Exception:
            pass

    try:
        tick = int(current_tick)
        return tick if tick > 0 else 1
    except Exception:
        return 1


def extract_final_answer_from_step_result(step_result: Optional[Dict[str, Any]]) -> str:
    if not isinstance(step_result, dict):
        return ""

    for key in ("final_answer", "message", "content", "text", "stdout"):
        value = step_result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    result_block = step_result.get("result")
    if isinstance(result_block, dict):
        for key in ("final_answer", "message", "content", "text", "stdout"):
            value = result_block.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return ""


__all__ = [
    "trace_tick_for_step",
    "ensure_step_execution_trace",
    "extract_trace_from_step_result",
    "persist_step_result_to_runtime_state",
    "extract_final_answer_from_step_result",
]
