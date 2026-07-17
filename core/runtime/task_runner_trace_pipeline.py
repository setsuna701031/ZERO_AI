from __future__ import annotations

import copy
import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


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


def sync_repair_chain_summary_from_execution_log(
    *,
    task: Any,
    runtime_state: Dict[str, Any],
) -> Dict[str, Any]:
    """
    v2.2 Repair Chain Summary Persistence.

    v2.1 already attaches repair_chain_consistency to each execution_log
    entry.  TaskRuntime normalization may rebuild/trim repair_context, so the
    chain summary must be restored from execution_log before public return
    and before any final state save.

    Source of truth:
        runtime_state.execution_log[*].result.repair_chain_consistency

    Destination:
        runtime_state.repair_context.last_repair_chain_consistency
        runtime_state.repair_context.repair_chain_consistency_history
        runtime_state.repair_context.engineering_execution.*
    """
    if not isinstance(runtime_state, dict):
        return runtime_state

    execution_log = runtime_state.get("execution_log")
    if not isinstance(execution_log, list) or not execution_log:
        return runtime_state

    latest_summary: Dict[str, Any] = {}
    history: List[Dict[str, Any]] = []

    for entry in execution_log:
        if not isinstance(entry, dict):
            continue
        result_payload = entry.get("result")
        if not isinstance(result_payload, dict):
            continue
        summary = result_payload.get("repair_chain_consistency")
        if not isinstance(summary, dict):
            continue

        latest_step = summary.get("latest_step")
        if isinstance(latest_step, dict):
            history.append(copy.deepcopy(latest_step))

        latest_summary = copy.deepcopy(summary)

    if not latest_summary:
        return runtime_state

    # Prefer summary history if present; otherwise rebuild from latest_step
    # entries collected from execution_log.
    summary_history = latest_summary.get("history")
    if isinstance(summary_history, list) and summary_history:
        resolved_history = [copy.deepcopy(item) for item in summary_history if isinstance(item, dict)]
    else:
        resolved_history = history

    repair_context = runtime_state.setdefault("repair_context", {})
    if not isinstance(repair_context, dict):
        repair_context = {}
        runtime_state["repair_context"] = repair_context

    repair_context["last_repair_chain_consistency"] = copy.deepcopy(latest_summary)
    repair_context["repair_chain_consistency_history"] = copy.deepcopy(resolved_history[-100:])

    engineering_execution = repair_context.setdefault("engineering_execution", {})
    if isinstance(engineering_execution, dict):
        engineering_execution["last_repair_chain_consistency"] = copy.deepcopy(latest_summary)
        engineering_execution["repair_chain_consistency_status"] = str(latest_summary.get("status") or "")
        engineering_execution["repair_chain_id"] = str(latest_summary.get("chain_id") or "")
        engineering_execution["repair_chain_total_steps"] = latest_summary.get("total_steps")
        engineering_execution["repair_chain_replay_verified_steps"] = latest_summary.get("replay_verified_steps")

    if isinstance(task, dict):
        task_repair_context = task.setdefault("repair_context", {})
        if isinstance(task_repair_context, dict):
            task_repair_context["last_repair_chain_consistency"] = copy.deepcopy(latest_summary)
            task_repair_context["repair_chain_consistency_history"] = copy.deepcopy(resolved_history[-100:])

    return runtime_state


def append_step_result_trace_json(
    *,
    task: Dict[str, Any],
    step: Optional[Dict[str, Any]],
    step_result: Dict[str, Any],
    step_index: int,
    current_tick: int,
    extract_error_type: Callable[[Dict[str, Any]], str],
    append_trace_json_event: Callable[[Dict[str, Any], str, Any], None],
) -> None:
    safe_step = copy.deepcopy(step) if isinstance(step, dict) else {}
    safe_result = copy.deepcopy(step_result) if isinstance(step_result, dict) else {}
    trace_items = extract_trace_from_step_result(safe_result)

    if not trace_items:
        trace_items = [
            {
                "step_index": step_index,
                "step_type": str(safe_step.get("type") or safe_result.get("step_type") or "").strip().lower(),
                "ok": bool(safe_result.get("ok", False)),
                "message": str(safe_result.get("message") or ""),
                "final_answer": str(safe_result.get("final_answer") or ""),
                "error_type": extract_error_type(safe_result),
                "attempts": 1,
                "max_attempts": 1,
                "retry_used": False,
            }
        ]

    for item in trace_items:
        if not isinstance(item, dict):
            continue

        data = copy.deepcopy(item)
        data.setdefault("task_id", task.get("task_id") or task.get("id"))
        data.setdefault("tick", current_tick)
        data.setdefault("step_index", step_index)
        data.setdefault("step_type", str(safe_step.get("type") or "").strip().lower())
        data.setdefault("step_id", str(safe_step.get("id") or "").strip())

        if "ok" not in data:
            data["ok"] = bool(safe_result.get("ok", False))

        if "error" not in data and safe_result.get("error"):
            data["error"] = copy.deepcopy(safe_result.get("error"))

        append_trace_json_event(task, "step_result", data)


def append_trace_json_event(
    *,
    task: Dict[str, Any],
    event_type: str,
    data: Any,
    persistence_service: Any,
    resolve_task_dir_for_trace: Callable[[Dict[str, Any]], str],
    read_trace_json: Callable[[str], Dict[str, Any]],
    make_json_safe: Callable[[Any], Any],
) -> None:
    try:
        task_dir = resolve_task_dir_for_trace(task)
        if not task_dir:
            return

        os.makedirs(task_dir, exist_ok=True)
        trace_path = os.path.join(task_dir, "trace.json")

        trace_payload = read_trace_json(trace_path)
        events = trace_payload.setdefault("events", [])
        if not isinstance(events, list):
            events = []
            trace_payload["events"] = events

        events.append(
            {
                "ts": datetime.now().timestamp(),
                "event_type": str(event_type or "event"),
                "data": make_json_safe(data),
            }
        )
        trace_payload["trace_version"] = int(trace_payload.get("trace_version") or 1)
        trace_payload["event_count"] = len(events)

        persistence_service.write_json(
            trace_path,
            trace_payload,
            reason="task_runner_event_trace_write",
            lineage={"source": "task_runner", "trace_type": "event_trace"},
            provenance={"source": "task_runner", "trace_path": trace_path},
            metadata={"operation": "write_trace_json"},
        )
    except Exception:
        pass


__all__ = [
    "append_step_result_trace_json",
    "append_trace_json_event",
    "ensure_step_execution_trace",
    "extract_trace_from_step_result",
    "sync_repair_chain_summary_from_execution_log",
    "trace_tick_for_step",
]
