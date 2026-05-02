from __future__ import annotations

import copy
from typing import Any, Dict, List


AUDIT_RECORD_KEYS = (
    "run_id",
    "step_index",
    "requested_tool",
    "final_decision",
    "risk_level",
    "risk_reason",
    "confirmation_required",
    "budget_remaining",
    "observation_summary",
    "why_call_tool",
    "why_not_call_tool",
    "why_stop_or_replan",
    "result_status",
)


def build_l5_audit_records(execution: Any, *, run_id: str = "") -> List[Dict[str, Any]]:
    """
    Convert existing L5 execution trace/log events into stable audit records.

    This module is formatting-only: it does not decide, execute, retry, replan,
    or mutate the input execution payload.
    """
    payload = execution if isinstance(execution, dict) else {}
    events = _events_from_execution(payload)
    records: List[Dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            continue
        records.append(format_l5_audit_record(event, run_id=run_id, step_index=index))
    return records


def format_l5_audit_record(event: Any, *, run_id: str = "", step_index: int = 0) -> Dict[str, Any]:
    payload = event if isinstance(event, dict) else {}
    decision_input = payload.get("decision_input") if isinstance(payload.get("decision_input"), dict) else {}
    result_summary = payload.get("result_summary") if isinstance(payload.get("result_summary"), dict) else {}

    record = {
        "run_id": str(run_id or ""),
        "step_index": int(step_index or 0),
        "requested_tool": str(
            payload.get("requested_tool")
            or payload.get("tool")
            or decision_input.get("requested_tool")
            or ""
        ),
        "final_decision": str(payload.get("final_decision") or ""),
        "risk_level": str(payload.get("risk_level") or ""),
        "risk_reason": str(payload.get("risk_reason") or ""),
        "confirmation_required": bool(payload.get("confirmation_required")),
        "budget_remaining": _copy_dict(decision_input.get("budget_remaining")),
        "observation_summary": str(decision_input.get("observation_summary") or ""),
        "why_call_tool": str(payload.get("why_call_tool") or ""),
        "why_not_call_tool": str(payload.get("why_not_call_tool") or ""),
        "why_stop_or_replan": str(payload.get("why_stop_or_replan") or ""),
        "result_status": str(payload.get("status") or result_summary.get("status") or ""),
    }
    return {key: record[key] for key in AUDIT_RECORD_KEYS}


def _events_from_execution(execution: Dict[str, Any]) -> List[Dict[str, Any]]:
    trace = execution.get("execution_trace") if isinstance(execution.get("execution_trace"), list) else []
    log = execution.get("execution_log") if isinstance(execution.get("execution_log"), list) else []
    trace_events = [copy.deepcopy(event) for event in trace if isinstance(event, dict)]
    if any(isinstance(event.get("decision_input"), dict) for event in trace_events):
        return trace_events
    return [copy.deepcopy(event) for event in log if isinstance(event, dict)]


def _copy_dict(value: Any) -> Dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}
