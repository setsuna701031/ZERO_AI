from __future__ import annotations

from typing import Any, Dict, List


BLOCKED_ACTIONS = {
    "execute_repair",
    "apply_patch",
    "write_file",
    "delete_file",
    "run_shell_command",
}


def build_runtime_repair_mutation_authorization(
    confirmation: Dict[str, Any] | None,
) -> Dict[str, Any]:
    confirmation = confirmation or {}

    approved = bool(confirmation.get("approved"))
    proposal_allowed = bool(confirmation.get("proposal_allowed"))
    mutation_allowed_after_confirmation = bool(
        confirmation.get("mutation_allowed_after_confirmation")
    )

    allowed_actions = list(confirmation.get("allowed_next_actions") or [])
    blocked_actions = sorted(BLOCKED_ACTIONS)

    authorized = (
        approved
        and proposal_allowed
        and mutation_allowed_after_confirmation
    )

    status = "authorized" if authorized else "blocked"

    reasons: List[str] = []

    if not approved:
        reasons.append("confirmation_not_approved")

    if not proposal_allowed:
        reasons.append("proposal_not_allowed")

    if not mutation_allowed_after_confirmation:
        reasons.append("mutation_not_allowed_after_confirmation")

    summary = (
        "Mutation authorization approved."
        if authorized
        else "Mutation authorization blocked: "
        + ", ".join(reasons)
    )

    return {
        "task_id": confirmation.get("task_id"),
        "proposal_id": confirmation.get("proposal_id"),
        "authorization_status": status,
        "authorized": authorized,
        "approved": approved,
        "proposal_allowed": proposal_allowed,
        "mutation_allowed_after_confirmation": (
            mutation_allowed_after_confirmation
        ),
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions,
        "reasons": reasons,
        "summary": summary,
    }
