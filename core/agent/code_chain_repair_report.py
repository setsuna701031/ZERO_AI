from __future__ import annotations

import copy
from typing import Any


def normalize_code_chain_repair_report(
    *,
    ok: bool,
    execution: dict[str, Any] | None,
    reviewable_result: dict[str, Any] | None,
) -> dict[str, Any]:
    execution_payload = execution if isinstance(execution, dict) else {}
    review_payload = reviewable_result if isinstance(reviewable_result, dict) else {}

    original_failure = copy.deepcopy(execution_payload.get("original_failure") or {})
    attempt_history = _dict_list(execution_payload.get("attempt_history"))
    verification_history = _dict_list(
        execution_payload.get("verification_history")
        or review_payload.get("verification_history")
    )
    status = _text(review_payload.get("status")) or ("ok" if ok else "failed")
    failure_reason = _text(review_payload.get("failure_reason"))
    if not failure_reason and isinstance(original_failure, dict):
        failure_reason = _text(
            original_failure.get("message")
            or original_failure.get("final_answer")
            or original_failure.get("error")
        )

    final_result = _text(review_payload.get("final_result"))
    if not final_result:
        final_result = "passed" if ok else "terminal_failure"

    repair_attempt_executed = any(
        _text(attempt.get("attempt_kind")).lower() == "repair"
        for attempt in attempt_history
    )
    first_attempt_failed = bool(
        attempt_history
        and isinstance(attempt_history[0], dict)
        and attempt_history[0].get("ok") is False
    )
    verification_passed = bool(ok) and (
        not verification_history
        or bool(verification_history[-1].get("ok"))
    )

    return {
        "ok": bool(ok),
        "status": status,
        "final_result": final_result,
        "attempt_count": int(
            review_payload.get("attempt_count")
            or execution_payload.get("attempt_count")
            or len(attempt_history)
            or 1
        ),
        "first_attempt_failed": first_attempt_failed,
        "failure_reason": failure_reason,
        "original_failure": original_failure,
        "repair_attempt_executed": repair_attempt_executed,
        "attempt_history": attempt_history,
        "verification_history": verification_history,
        "verification_passed": verification_passed,
    }


def build_code_chain_repair_export_payload(
    repair_result_report: dict[str, Any],
) -> dict[str, Any]:
    report = repair_result_report if isinstance(repair_result_report, dict) else {}
    attempt_history = _dict_list(report.get("attempt_history"))
    verification_history = _dict_list(report.get("verification_history"))
    repair_attempted = bool(report.get("repair_attempt_executed"))

    return {
        "schema": "code_chain_repair_result_report_v1",
        "final_status": _text(report.get("status")) or ("ok" if report.get("ok") else "failed"),
        "original_failure": copy.deepcopy(report.get("original_failure") or {}),
        "attempt_count": int(report.get("attempt_count") or len(attempt_history) or 0),
        "attempt_history": [
            _attempt_export_summary(attempt) for attempt in attempt_history
        ],
        "verification_history": [
            _verification_export_summary(item) for item in verification_history
        ],
        "repair_attempted": repair_attempted,
        "repair_succeeded": bool(report.get("ok")) and repair_attempted,
    }


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [copy.deepcopy(item) for item in value if isinstance(item, dict)]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _attempt_export_summary(attempt: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_index": attempt.get("attempt_index"),
        "attempt_kind": _text(attempt.get("attempt_kind")),
        "ok": bool(attempt.get("ok")),
        "failure_reason": _text(attempt.get("failure_reason")),
        "changed_files": list(attempt.get("changed_files") or []),
        "message": _text(attempt.get("message")),
    }


def _verification_export_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_index": item.get("attempt_index"),
        "attempt_kind": _text(item.get("attempt_kind")),
        "ok": bool(item.get("ok")),
        "verification_command": _text(item.get("verification_command")),
        "verification_output_summary": _text(item.get("verification_output_summary")),
        "failure_reason": _text(item.get("failure_reason")),
    }
