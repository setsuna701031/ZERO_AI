from __future__ import annotations

from typing import Any, Dict, List, Mapping

from core.tasks.runtime_state_hygiene import freeze_runtime_export


APPROVED_VALUES = {"approved", "approve", "yes", "y", "true", "confirmed", "confirm"}
REJECTED_VALUES = {"rejected", "reject", "no", "n", "false", "denied", "deny"}


def build_runtime_repair_confirmation_gate(
    proposal: Any,
    confirmation: Any = None,
) -> Dict[str, Any]:
    """Build a deterministic confirmation gate for a repair planner proposal.

    This layer is intentionally side-effect free. It does not enqueue tasks,
    call the planner, execute tools, write files, or mutate the supplied
    proposal/confirmation payloads. It only decides whether a planner proposal
    is blocked, pending, rejected, approved, or does not require confirmation.
    """
    safe_proposal = proposal if isinstance(proposal, Mapping) else {}
    safe_confirmation = confirmation if isinstance(confirmation, Mapping) else {}

    task_id = _first_nonempty(safe_proposal.get("task_id"))
    proposal_id = _first_nonempty(
        safe_proposal.get("proposal_id"),
        safe_proposal.get("id"),
        _build_fallback_proposal_id(safe_proposal),
    )
    proposal_type = _first_nonempty(
        safe_proposal.get("proposal_type"),
        safe_proposal.get("type"),
        "runtime_repair_planner_proposal",
    )

    proposal_allowed = _as_bool(safe_proposal.get("proposal_allowed"), default=False)
    planner_allowed = _as_bool(safe_proposal.get("planner_allowed"), default=False)
    mutation_allowed = _as_bool(safe_proposal.get("mutation_allowed"), default=False)
    execution_allowed = _as_bool(safe_proposal.get("execution_allowed"), default=False)
    requires_confirmation = _as_bool(safe_proposal.get("requires_confirmation"), default=True)

    requested_status = _confirmation_status(safe_confirmation)
    operator = _first_nonempty(safe_confirmation.get("operator"), safe_confirmation.get("user"))
    confirmation_reason = _first_nonempty(safe_confirmation.get("reason"), safe_confirmation.get("message"))

    if not proposal_allowed:
        status = "blocked"
        allowed_after_confirmation = False
        reason = _first_nonempty(
            safe_proposal.get("reason"),
            "proposal is not allowed by planner bridge gate",
        )
    elif requested_status == "rejected":
        status = "rejected"
        allowed_after_confirmation = False
        reason = confirmation_reason or "operator rejected repair proposal"
    elif requires_confirmation and requested_status != "approved":
        status = "pending_confirmation"
        allowed_after_confirmation = False
        reason = "repair proposal requires confirmation before planner routing"
    elif requested_status == "approved" or not requires_confirmation:
        status = "approved" if requires_confirmation else "not_required"
        allowed_after_confirmation = bool(planner_allowed or proposal_allowed)
        reason = confirmation_reason or _first_nonempty(
            safe_proposal.get("reason"),
            "repair proposal passed confirmation gate",
        )
    else:
        status = "pending_confirmation"
        allowed_after_confirmation = False
        reason = "repair proposal requires confirmation before planner routing"

    planner_allowed_after_confirmation = bool(allowed_after_confirmation and (planner_allowed or proposal_allowed))
    mutation_allowed_after_confirmation = bool(planner_allowed_after_confirmation and mutation_allowed)
    execution_allowed_after_confirmation = bool(planner_allowed_after_confirmation and execution_allowed)

    return {
        "ok": True,
        "task_id": task_id,
        "proposal_id": proposal_id,
        "proposal_type": proposal_type,
        "confirmation_status": status,
        "requires_confirmation": requires_confirmation,
        "proposal_allowed": proposal_allowed,
        "planner_allowed_before_confirmation": planner_allowed,
        "planner_allowed_after_confirmation": planner_allowed_after_confirmation,
        "mutation_allowed_after_confirmation": mutation_allowed_after_confirmation,
        "execution_allowed_after_confirmation": execution_allowed_after_confirmation,
        "operator": operator,
        "reason": reason,
        "allowed_next_action": _allowed_next_action(
            status=status,
            planner_allowed_after_confirmation=planner_allowed_after_confirmation,
            mutation_allowed_after_confirmation=mutation_allowed_after_confirmation,
            execution_allowed_after_confirmation=execution_allowed_after_confirmation,
        ),
        "confirmation_required_fields": _confirmation_required_fields(requires_confirmation),
        "raw_proposal": freeze_runtime_export(proposal),
        "raw_confirmation": freeze_runtime_export(confirmation),
    }


def build_runtime_repair_confirmation_gates(
    proposals: Any,
    confirmation: Any = None,
) -> List[Dict[str, Any]]:
    """Build confirmation gates for a single proposal or a list of proposals."""
    if isinstance(proposals, list):
        return [build_runtime_repair_confirmation_gate(item, confirmation=confirmation) for item in proposals]
    return [build_runtime_repair_confirmation_gate(proposals, confirmation=confirmation)]


def _confirmation_status(confirmation: Mapping[str, Any]) -> str:
    if not isinstance(confirmation, Mapping) or not confirmation:
        return "none"

    for key in ("approved", "approve", "confirmed", "confirm"):
        value = confirmation.get(key)
        if isinstance(value, bool):
            return "approved" if value else "rejected"

    for key in ("status", "decision", "confirmation", "action"):
        text = _safe_lower(confirmation.get(key))
        if text in APPROVED_VALUES:
            return "approved"
        if text in REJECTED_VALUES:
            return "rejected"

    return "none"


def _allowed_next_action(
    *,
    status: str,
    planner_allowed_after_confirmation: bool,
    mutation_allowed_after_confirmation: bool,
    execution_allowed_after_confirmation: bool,
) -> str:
    if status == "blocked":
        return "inspect_bridge_reason"
    if status == "rejected":
        return "archive_or_revise_proposal"
    if status == "pending_confirmation":
        return "request_operator_confirmation"
    if not planner_allowed_after_confirmation:
        return "inspect_proposal_gate"
    if execution_allowed_after_confirmation:
        return "planner_execution_route_available"
    if mutation_allowed_after_confirmation:
        return "planner_mutation_route_available"
    return "planner_proposal_route_available"


def _confirmation_required_fields(requires_confirmation: bool) -> List[str]:
    if not requires_confirmation:
        return []
    return ["approved", "operator", "reason"]


def _build_fallback_proposal_id(proposal: Mapping[str, Any]) -> str:
    task_id = _first_nonempty(proposal.get("task_id"), "task")
    proposal_type = _first_nonempty(proposal.get("proposal_type"), "runtime_repair_planner_proposal")
    return f"{task_id}:{proposal_type}"


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1", "allowed", "approved"}:
            return True
        if lowered in {"false", "no", "n", "0", "blocked", "denied"}:
            return False
    if value is None:
        return default
    return bool(value)


def _safe_lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
