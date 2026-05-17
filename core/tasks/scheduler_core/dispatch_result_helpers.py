from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def extract_effective_status_and_answer(
    original_task: Optional[Dict[str, Any]],
    refreshed_task: Optional[Dict[str, Any]],
    runner_result: Optional[Dict[str, Any]],
) -> Tuple[str, Any]:
    candidates: List[Dict[str, Any]] = []

    if isinstance(runner_result, dict):
        candidates.append(runner_result)
    if isinstance(refreshed_task, dict):
        candidates.append(refreshed_task)
    if isinstance(original_task, dict):
        candidates.append(original_task)

    status = ""
    final_answer: Any = ""

    for source in candidates:
        source_status = str(source.get("status") or "").strip().lower()
        if source_status:
            status = source_status
            break

    for source in candidates:
        if "final_answer" in source:
            value = source.get("final_answer")
            if value not in (None, ""):
                final_answer = value
                break

    return status, final_answer


def build_finalize_decision(
    original_task: Optional[Dict[str, Any]],
    refreshed_task: Optional[Dict[str, Any]],
    runner_result: Optional[Dict[str, Any]],
    *,
    status_blocked: str,
    status_finished: str,
    status_failed: str,
) -> Dict[str, Any]:
    result = runner_result if isinstance(runner_result, dict) else {}
    effective_status, effective_final_answer = extract_effective_status_and_answer(
        original_task=original_task,
        refreshed_task=refreshed_task,
        runner_result=result,
    )

    status = str(effective_status or "").strip().lower()
    normalized_finished = str(status_finished or "").strip().lower()
    normalized_failed = str(status_failed or "").strip().lower()
    normalized_blocked = str(status_blocked or "").strip().lower()

    finished_statuses = {"done", "finished", normalized_finished, "success", "completed"}
    failed_statuses = {"failed", normalized_failed, "error"}
    queued_statuses = {"queued", "retry", "ready", "running"}
    blocked_statuses = {normalized_blocked} if normalized_blocked else set()

    action = "release"
    fail_error = ""
    blocked_reason = ""

    if status in finished_statuses:
        action = "finish"
    elif status in failed_statuses:
        action = "fail"
        fail_error = str(result.get("error") or effective_final_answer or "task failed")
    elif status in blocked_statuses:
        action = "block"
        blocked_reason = str(result.get("blocked_reason") or "")
    elif status in queued_statuses:
        action = "requeue_if_ready"

    return {
        "action": action,
        "status": status,
        "final_answer": effective_final_answer,
        "fail_error": fail_error,
        "blocked_reason": blocked_reason,
        "ok": bool(result.get("ok", True)),
    }
