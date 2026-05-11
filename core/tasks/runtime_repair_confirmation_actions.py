from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from core.tasks.runtime_state_hygiene import freeze_runtime_export


VALID_CONFIRMATION_ACTIONS = {"approve", "reject"}

TERMINAL_CONFIRMATION_STATUSES = {"approved", "rejected"}


def build_runtime_repair_confirmation_action(
    confirmation: Any,
    *,
    action: str,
    operator: str = "",
    reason: str = "",
) -> Dict[str, Any]:
    """Apply a read-only confirmation decision to a confirmation payload.

    This layer only returns a new confirmation state. It does not execute tools,
    schedule tasks, patch files, call planners, or mutate the supplied payload.
    """
    safe_confirmation = confirmation if isinstance(confirmation, Mapping) else {}
    normalized_action = str(action or "").strip().lower()
    operator_text = str(operator or "").strip()
    reason_text = str(reason or "").strip()

    if normalized_action not in VALID_CONFIRMATION_ACTIONS:
        return _build_invalid_action(
            safe_confirmation,
            action=normalized_action,
            operator=operator_text,
            reason=reason_text,
        )

    current_status = _first_nonempty(
        safe_confirmation.get("confirmation_status"),
        safe_confirmation.get("status"),
        "pending",
    ).lower()

    if current_status in TERMINAL_CONFIRMATION_STATUSES:
        return _build_terminal_noop(
            safe_confirmation,
            action=normalized_action,
            operator=operator_text,
            reason=reason_text,
            current_status=current_status,
        )

    if normalized_action == "approve":
        return _build_approved(
            safe_confirmation,
            operator=operator_text,
            reason=reason_text,
        )

    return _build_rejected(
        safe_confirmation,
        operator=operator_text,
        reason=reason_text,
    )


def approve_runtime_repair_confirmation(
    confirmation: Any,
    *,
    operator: str = "",
    reason: str = "",
) -> Dict[str, Any]:
    return build_runtime_repair_confirmation_action(
        confirmation,
        action="approve",
        operator=operator,
        reason=reason,
    )


def reject_runtime_repair_confirmation(
    confirmation: Any,
    *,
    operator: str = "",
    reason: str = "",
) -> Dict[str, Any]:
    return build_runtime_repair_confirmation_action(
        confirmation,
        action="reject",
        operator=operator,
        reason=reason,
    )


def build_runtime_repair_confirmation_action_result(
    confirmation: Any,
    *,
    approved: Optional[bool] = None,
    operator: str = "",
    reason: str = "",
) -> Dict[str, Any]:
    """Compatibility helper for form-style confirmation input."""
    if approved is True:
        return approve_runtime_repair_confirmation(
            confirmation,
            operator=operator,
            reason=reason,
        )
    if approved is False:
        return reject_runtime_repair_confirmation(
            confirmation,
            operator=operator,
            reason=reason,
        )
    return build_runtime_repair_confirmation_action(
        confirmation,
        action="",
        operator=operator,
        reason=reason,
    )


def _build_invalid_action(
    confirmation: Mapping[str, Any],
    *,
    action: str,
    operator: str,
    reason: str,
) -> Dict[str, Any]:
    return {
        "ok": False,
        "action_ok": False,
        "error": "invalid confirmation action",
        "error_type": "invalid_confirmation_action",
        "requested_action": action,
        "valid_actions": sorted(VALID_CONFIRMATION_ACTIONS),
        "confirmation_status": _first_nonempty(
            confirmation.get("confirmation_status"),
            confirmation.get("status"),
            "pending",
        ),
        "operator": operator,
        "reason": reason,
        "mutation_allowed": False,
        "execution_allowed": False,
        "schedule_allowed": False,
        "raw_confirmation": freeze_runtime_export(confirmation),
    }


def _build_terminal_noop(
    confirmation: Mapping[str, Any],
    *,
    action: str,
    operator: str,
    reason: str,
    current_status: str,
) -> Dict[str, Any]:
    return {
        "ok": False,
        "action_ok": False,
        "error": "confirmation is already terminal",
        "error_type": "terminal_confirmation_state",
        "requested_action": action,
        "confirmation_status": current_status,
        "operator": operator,
        "reason": reason,
        "mutation_allowed": False,
        "execution_allowed": False,
        "schedule_allowed": False,
        "raw_confirmation": freeze_runtime_export(confirmation),
    }


def _build_approved(
    confirmation: Mapping[str, Any],
    *,
    operator: str,
    reason: str,
) -> Dict[str, Any]:
    task_id = _first_nonempty(confirmation.get("task_id"))
    proposal_id = _first_nonempty(confirmation.get("proposal_id"))

    return {
        "ok": True,
        "action_ok": True,
        "confirmation_action": "approve",
        "confirmation_status": "approved",
        "task_id": task_id,
        "proposal_id": proposal_id,
        "operator": operator,
        "reason": reason or "approved by operator",
        "planner_allowed_after_confirmation": bool(
            confirmation.get("planner_allowed_after_confirmation", False)
        ),
        "mutation_allowed_after_confirmation": bool(
            confirmation.get("mutation_allowed_after_confirmation", False)
        ),
        "execution_allowed_after_confirmation": bool(
            confirmation.get("execution_allowed_after_confirmation", False)
        ),
        "mutation_allowed": False,
        "execution_allowed": False,
        "schedule_allowed": False,
        "allowed_next_action": "build_planner_route_preview",
        "human_summary": (
            "Repair confirmation approved. Mutation, execution, and scheduling remain disabled; "
            "only planner route preview may be built next."
        ),
        "required_next_gate": "mutation_authorization",
        "history": _append_history(
            confirmation,
            status="approved",
            action="approve",
            operator=operator,
            reason=reason or "approved by operator",
        ),
        "raw_confirmation": freeze_runtime_export(confirmation),
    }


def _build_rejected(
    confirmation: Mapping[str, Any],
    *,
    operator: str,
    reason: str,
) -> Dict[str, Any]:
    task_id = _first_nonempty(confirmation.get("task_id"))
    proposal_id = _first_nonempty(confirmation.get("proposal_id"))

    return {
        "ok": True,
        "action_ok": True,
        "confirmation_action": "reject",
        "confirmation_status": "rejected",
        "task_id": task_id,
        "proposal_id": proposal_id,
        "operator": operator,
        "reason": reason or "rejected by operator",
        "planner_allowed_after_confirmation": False,
        "mutation_allowed_after_confirmation": False,
        "execution_allowed_after_confirmation": False,
        "mutation_allowed": False,
        "execution_allowed": False,
        "schedule_allowed": False,
        "allowed_next_action": "inspect_bridge_reason",
        "human_summary": (
            "Repair confirmation rejected. Planner routing, mutation, execution, and scheduling remain disabled."
        ),
        "required_next_gate": "none",
        "history": _append_history(
            confirmation,
            status="rejected",
            action="reject",
            operator=operator,
            reason=reason or "rejected by operator",
        ),
        "raw_confirmation": freeze_runtime_export(confirmation),
    }


def _append_history(
    confirmation: Mapping[str, Any],
    *,
    status: str,
    action: str,
    operator: str,
    reason: str,
) -> List[Dict[str, Any]]:
    raw_history = confirmation.get("history")
    history: List[Dict[str, Any]] = []

    if isinstance(raw_history, list):
        for item in raw_history:
            if isinstance(item, Mapping):
                history.append(dict(item))

    history.append(
        {
            "status": status,
            "action": action,
            "operator": operator,
            "reason": reason,
        }
    )
    return history


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
