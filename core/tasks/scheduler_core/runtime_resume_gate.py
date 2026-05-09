from __future__ import annotations

import copy
from typing import Any, Dict, List


APPROVED_REVIEW_STATUSES = {"approved", "accepted", "allowed", "cleared", "resolved"}
REJECTED_REVIEW_STATUSES = {"rejected", "denied", "declined", "cancelled", "canceled"}
RESOLVED_BLOCKER_STATUSES = {"resolved", "applied", "rejected", "cancelled", "canceled", "done", "cleared"}
RESUMABLE_PERSISTED_STATUSES = {
    "running",
    "queued",
    "ready",
    "retry",
    "waiting",
    "waiting_blocker",
    "waiting_review",
    "blocked",
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def active_runtime_gate_blockers(blockers: Any) -> List[Dict[str, Any]]:
    if not isinstance(blockers, list):
        return []

    active: List[Dict[str, Any]] = []
    for item in blockers:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "pending").strip().lower()
        if status not in RESOLVED_BLOCKER_STATUSES:
            active.append(copy.deepcopy(item))
    return active


def apply_runtime_resume_gate(
    *,
    task: Dict[str, Any],
    status_review_required: str,
) -> Dict[str, Any]:
    """Apply deterministic resume policy to a hydrated task payload.

    Hydration reconstructs persisted task state.  This helper owns only the
    resume policy: if a persisted task requests `run_next_tick` and has no
    active blockers or pending review, normalize it back into a runnable state.
    """
    if not isinstance(task, dict):
        return task

    persisted_status = str(task.get("status") or "").strip().lower()
    persisted_next_action = str(task.get("next_action") or "").strip().lower()
    review_status = str(task.get("review_status") or "").strip().lower()
    requires_review = bool(task.get("requires_review", False))

    active_blockers = active_runtime_gate_blockers(task.get("blockers"))
    active_blocker_count = _safe_int(task.get("active_blocker_count"), 0)

    review_pending = bool(
        requires_review
        or task.get("review_id")
        or task.get("review_payload")
        or persisted_status == status_review_required
    )
    if review_status in APPROVED_REVIEW_STATUSES:
        review_pending = False
    if review_status in REJECTED_REVIEW_STATUSES:
        review_pending = True

    resumable_statuses = set(RESUMABLE_PERSISTED_STATUSES)
    resumable_statuses.add(str(status_review_required))

    if (
        persisted_next_action == "run_next_tick"
        and persisted_status in resumable_statuses
        and not active_blockers
        and active_blocker_count <= 0
        and not review_pending
    ):
        task["status"] = "running"
        task["blocked_reason"] = ""
        task["waiting_reason"] = ""
        task["active_blocker_count"] = 0
        task["agent_action"] = str(task.get("agent_action") or "resume_execution")

    return task
