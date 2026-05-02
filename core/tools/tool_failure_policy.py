from __future__ import annotations

from typing import Any, Dict


CAN_RETRY = "CAN_RETRY"
CANNOT_RETRY = "CANNOT_RETRY"
MUST_STOP = "MUST_STOP"
NEED_REPLAN = "NEED_REPLAN"


RAW_STATUS_TO_DECISION_CLASS = {
    "invalid_args": CAN_RETRY,
    "tool_not_found": MUST_STOP,
    "invalid_tool": MUST_STOP,
    "permission_denied": MUST_STOP,
    "denied": MUST_STOP,
    "guard_blocked": MUST_STOP,
    "blocked": MUST_STOP,
    "failed": NEED_REPLAN,
    "retryable": CAN_RETRY,
    "non_retryable": CANNOT_RETRY,
}


def classify_tool_failure(raw_status: Any, *, error: Any = None) -> Dict[str, Any]:
    status = str(raw_status or "").strip().lower()
    error_text = str(error or "").strip().lower()

    if status in RAW_STATUS_TO_DECISION_CLASS:
        decision_class = RAW_STATUS_TO_DECISION_CLASS[status]
    elif "not found" in error_text:
        decision_class = MUST_STOP
        status = status or "tool_not_found"
    elif "permission" in error_text or "denied" in error_text:
        decision_class = MUST_STOP
        status = status or "permission_denied"
    elif "invalid" in error_text and "arg" in error_text:
        decision_class = CAN_RETRY
        status = status or "invalid_args"
    elif status:
        decision_class = NEED_REPLAN
    else:
        decision_class = CANNOT_RETRY
        status = "unknown_failure"

    return {
        "ok": True,
        "raw_status": status,
        "decision_class": decision_class,
        "reason": f"failure_policy:{status}:{decision_class}",
        "error": str(error or ""),
    }


def recommend_for_previous_failures(previous_failures: Any) -> Dict[str, Any]:
    failures = previous_failures if isinstance(previous_failures, list) else []
    if not failures:
        return {
            "ok": True,
            "recommendation": "ALLOW",
            "reason": "no_previous_failures",
            "failure_class": "",
        }

    latest = failures[-1] if isinstance(failures[-1], dict) else {"status": failures[-1]}
    classified = classify_tool_failure(latest.get("status"), error=latest.get("error"))
    decision_class = classified.get("decision_class")
    if decision_class == MUST_STOP:
        recommendation = "STOP"
    elif decision_class == NEED_REPLAN:
        recommendation = "REPLAN"
    elif decision_class == CAN_RETRY:
        recommendation = "ALLOW"
    else:
        recommendation = "STOP"

    return {
        "ok": recommendation == "ALLOW",
        "recommendation": recommendation,
        "reason": classified.get("reason"),
        "failure_class": decision_class,
        "latest_failure": latest,
    }
