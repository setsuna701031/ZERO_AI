from __future__ import annotations

import copy
from typing import Any, Dict, List


def active_runtime_gate_blockers(blockers: Any) -> List[Dict[str, Any]]:
    if not isinstance(blockers, list):
        return []

    resolved_statuses = {"resolved", "applied", "rejected", "cancelled", "canceled", "done", "cleared"}
    active: List[Dict[str, Any]] = []
    for item in blockers:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "pending").strip().lower()
        if status not in resolved_statuses:
            active.append(copy.deepcopy(item))
    return active


def runtime_dispatch_gate_decision(
    scheduler: Any,
    task: Dict[str, Any],
    *,
    terminal_statuses: set[str],
    status_review_required: str,
) -> Dict[str, Any]:
    if not isinstance(task, dict):
        return {"allow": False, "reason": "invalid_task"}

    status = str(task.get("status") or "").strip().lower()
    next_action = str(task.get("next_action") or "").strip().lower()
    review_status = str(task.get("review_status") or "").strip().lower()
    waiting_reason = str(task.get("waiting_reason") or task.get("blocked_reason") or "").strip()

    requires_review = bool(task.get("requires_review", False))
    review_id = str(task.get("review_id") or "").strip()
    review_payload = task.get("review_payload")
    has_review_payload = isinstance(review_payload, dict) and bool(review_payload)

    active_blocker_count = scheduler._safe_int_for_runtime_gate(task.get("active_blocker_count"), 0)
    active_blockers = scheduler._active_runtime_gate_blockers(task.get("blockers"))
    if active_blockers and active_blocker_count <= 0:
        active_blocker_count = len(active_blockers)

    if not review_status and (requires_review or review_id or has_review_payload or status == status_review_required):
        review_status = "pending"

    approved_review_statuses = {"approved", "accepted", "allowed", "cleared", "resolved"}
    rejected_review_statuses = {"rejected", "denied", "declined", "cancelled", "canceled"}
    pending_review_statuses = {"", "pending", "required", "requested", "waiting", "waiting_review", "review_required"}

    review_approved = review_status in approved_review_statuses
    review_rejected = review_status in rejected_review_statuses
    review_pending = bool(requires_review or review_id or has_review_payload or status == status_review_required) and not review_approved and not review_rejected
    if review_status in pending_review_statuses and (requires_review or review_id or has_review_payload or status == status_review_required):
        review_pending = True

    if status in terminal_statuses:
        return {
            "allow": False,
            "reason": "terminal_status",
            "status": status,
            "next_action": next_action,
            "active_blocker_count": active_blocker_count,
        }

    if review_rejected:
        return {
            "allow": False,
            "reason": "review_rejected",
            "status": status or status_review_required,
            "next_action": next_action or "finish",
            "active_blocker_count": active_blocker_count,
        }

    if review_pending:
        return {
            "allow": False,
            "reason": waiting_reason or "review_required",
            "status": status_review_required,
            "next_action": "wait_for_external_event",
            "active_blocker_count": max(1, active_blocker_count),
        }

    if status in {"waiting", "waiting_review", "waiting_blocker", "blocked", "paused", status_review_required}:
        if next_action != "run_next_tick" or active_blocker_count > 0 or active_blockers:
            return {
                "allow": False,
                "reason": waiting_reason or "waiting_for_external_event",
                "status": status,
                "next_action": next_action or "wait_for_external_event",
                "active_blocker_count": active_blocker_count,
            }

    if next_action == "wait_for_external_event":
        return {
            "allow": False,
            "reason": waiting_reason or "next_action_wait_for_external_event",
            "status": status,
            "next_action": next_action,
            "active_blocker_count": active_blocker_count,
        }

    if active_blocker_count > 0 or active_blockers:
        return {
            "allow": False,
            "reason": waiting_reason or "active_blockers_present",
            "status": status,
            "next_action": next_action,
            "active_blocker_count": active_blocker_count,
        }

    return {
        "allow": True,
        "reason": "dispatch_allowed",
        "status": status,
        "next_action": next_action,
        "active_blocker_count": 0,
    }
