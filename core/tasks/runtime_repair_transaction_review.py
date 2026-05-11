from __future__ import annotations

from typing import Any, Dict, List, Mapping

from core.tasks.runtime_repair_confirmation import (
    build_runtime_repair_confirmation_gate,
)
from core.tasks.runtime_repair_confirmation_actions import (
    approve_runtime_repair_confirmation,
    reject_runtime_repair_confirmation,
)
from core.tasks.runtime_repair_transaction_preview import (
    build_runtime_repair_transaction_preview,
)
from core.tasks.runtime_state_hygiene import (
    freeze_runtime_export,
)


RUNTIME_REPAIR_TRANSACTION_REVIEW_TYPE = (
    "runtime_repair_transaction_review"
)

RUNTIME_REPAIR_TRANSACTION_REVIEW_VERSION = (
    "runtime_repair_transaction_review.v1"
)


def build_runtime_repair_transaction_review(
    transaction: Any,
    *,
    confirmation: Any = None,
) -> Dict[str, Any]:
    """Build a deterministic review contract for a repair transaction.

    This layer is review-only and side-effect free.
    It does not execute tools, apply mutations, schedule tasks,
    call planners, or mutate runtime state.
    """
    tx = transaction if isinstance(transaction, Mapping) else {}
    safe_confirmation = (
        confirmation if isinstance(confirmation, Mapping) else {}
    )

    preview = build_runtime_repair_transaction_preview(tx)

    proposal = {
        "task_id": tx.get("task_id"),
        "proposal_id": tx.get("proposal_id"),
        "proposal_type": (
            "runtime_repair_transaction"
        ),
        "proposal_allowed": bool(
            preview.get("commit_ready")
        ),
        "planner_allowed": bool(
            preview.get("commit_ready")
        ),
        "mutation_allowed": False,
        "execution_allowed": False,
        "requires_confirmation": True,
        "reason": preview.get("human_summary"),
    }

    confirmation_gate = (
        build_runtime_repair_confirmation_gate(
            proposal,
            confirmation=safe_confirmation,
        )
    )

    review_state = classify_runtime_repair_review_state(
        preview=preview,
        confirmation_gate=confirmation_gate,
    )

    review = {
        "review_type": (
            RUNTIME_REPAIR_TRANSACTION_REVIEW_TYPE
        ),
        "review_version": (
            RUNTIME_REPAIR_TRANSACTION_REVIEW_VERSION
        ),
        "transaction_id": _safe_text(
            tx.get("transaction_id")
        ),
        "task_id": _safe_text(
            tx.get("task_id")
        ),
        "proposal_id": _safe_text(
            tx.get("proposal_id")
        ),
        "review_state": review_state,
        "review_allowed": bool(
            preview.get("commit_ready")
        ),
        "risk_level": _safe_text(
            preview.get("risk_level")
        ),
        "requires_confirmation": True,
        "preview": freeze_runtime_export(
            preview
        ),
        "confirmation_gate": (
            freeze_runtime_export(
                confirmation_gate
            )
        ),
        "allowed_next_action": (
            classify_runtime_repair_review_next_action(
                review_state
            )
        ),
        "human_summary": (
            build_runtime_repair_review_summary(
                review_state=review_state,
                risk_level=_safe_text(
                    preview.get("risk_level")
                ),
                confirmation_status=_safe_text(
                    confirmation_gate.get(
                        "confirmation_status"
                    )
                ),
            )
        ),
    }

    return freeze_runtime_export(review)


def approve_runtime_repair_transaction_review(
    review: Any,
    *,
    operator: str = "",
    reason: str = "",
) -> Dict[str, Any]:
    safe_review = (
        review if isinstance(review, Mapping) else {}
    )

    gate = (
        safe_review.get("confirmation_gate")
        if isinstance(
            safe_review.get(
                "confirmation_gate"
            ),
            Mapping,
        )
        else {}
    )

    approval = (
        approve_runtime_repair_confirmation(
            gate,
            operator=operator,
            reason=reason,
        )
    )

    return freeze_runtime_export(
        {
            "review_action": "approve",
            "review_state": "approved",
            "review_ok": bool(
                approval.get("ok")
            ),
            "transaction_id": _safe_text(
                safe_review.get(
                    "transaction_id"
                )
            ),
            "task_id": _safe_text(
                safe_review.get(
                    "task_id"
                )
            ),
            "proposal_id": _safe_text(
                safe_review.get(
                    "proposal_id"
                )
            ),
            "approval": freeze_runtime_export(
                approval
            ),
            "allowed_next_action": (
                "build_mutation_authorization"
            ),
            "human_summary": (
                "Runtime repair transaction review approved."
            ),
        }
    )


def reject_runtime_repair_transaction_review(
    review: Any,
    *,
    operator: str = "",
    reason: str = "",
) -> Dict[str, Any]:
    safe_review = (
        review if isinstance(review, Mapping) else {}
    )

    gate = (
        safe_review.get("confirmation_gate")
        if isinstance(
            safe_review.get(
                "confirmation_gate"
            ),
            Mapping,
        )
        else {}
    )

    rejection = (
        reject_runtime_repair_confirmation(
            gate,
            operator=operator,
            reason=reason,
        )
    )

    return freeze_runtime_export(
        {
            "review_action": "reject",
            "review_state": "rejected",
            "review_ok": bool(
                rejection.get("ok")
            ),
            "transaction_id": _safe_text(
                safe_review.get(
                    "transaction_id"
                )
            ),
            "task_id": _safe_text(
                safe_review.get(
                    "task_id"
                )
            ),
            "proposal_id": _safe_text(
                safe_review.get(
                    "proposal_id"
                )
            ),
            "rejection": freeze_runtime_export(
                rejection
            ),
            "allowed_next_action": (
                "archive_or_revise_transaction"
            ),
            "human_summary": (
                "Runtime repair transaction review rejected."
            ),
        }
    )


def classify_runtime_repair_review_state(
    *,
    preview: Any,
    confirmation_gate: Any,
) -> str:
    safe_preview = (
        preview if isinstance(preview, Mapping) else {}
    )

    safe_gate = (
        confirmation_gate
        if isinstance(confirmation_gate, Mapping)
        else {}
    )

    risk_level = _safe_text(
        safe_preview.get("risk_level")
    ).lower()

    confirmation_status = _safe_text(
        safe_gate.get(
            "confirmation_status"
        )
    ).lower()

    if risk_level == "critical":
        return "blocked"

    if confirmation_status == "approved":
        return "approved"

    if confirmation_status == "rejected":
        return "rejected"

    if confirmation_status == "pending_confirmation":
        return "awaiting_confirmation"

    return "review_pending"


def classify_runtime_repair_review_next_action(
    review_state: str,
) -> str:
    state = _safe_text(review_state).lower()

    if state == "blocked":
        return "inspect_scope_gate"

    if state == "approved":
        return "build_mutation_authorization"

    if state == "rejected":
        return "archive_or_revise_transaction"

    if state == "awaiting_confirmation":
        return "request_operator_confirmation"

    return "review_transaction_preview"


def build_runtime_repair_review_summary(
    *,
    review_state: str,
    risk_level: str,
    confirmation_status: str,
) -> str:
    return (
        f"Runtime repair review is "
        f"{review_state or 'unknown'} "
        f"(risk={risk_level or 'unknown'}, "
        f"confirmation={confirmation_status or 'unknown'})."
    )


def _safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()