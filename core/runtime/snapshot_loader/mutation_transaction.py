from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from core.runtime.snapshot_loader.approval_runtime import (
    build_approval_request,
    is_execution_approved,
    transition_approval_state,
)
from core.runtime.snapshot_loader.audit_runtime import build_audit_record
from core.runtime.snapshot_loader.runtime_seal import (
    build_runtime_seal,
    verify_runtime_seal,
)


_MUTATION_ACTIONS = {
    "mutation_runtime",
    "patch_apply",
}


def build_mutation_transaction(
    action: str,
    payload: Optional[Mapping[str, Any]] = None,
    transaction_id: str = "mutation-transaction",
) -> Dict[str, Any]:
    if action not in _MUTATION_ACTIONS:
        raise ValueError("action must be mutation_runtime or patch_apply")

    approval = build_approval_request(
        action=action,
        request_id=f"{transaction_id}:approval",
    )

    audit = build_audit_record(
        action=action,
        payload=payload,
        audit_id=f"{transaction_id}:audit",
        source="mutation_transaction",
    )

    seal = build_runtime_seal(
        seal_id=f"{transaction_id}:seal",
    )

    return {
        "transaction_id": transaction_id,
        "transaction_runtime": "snapshot_loader_mutation_transaction",
        "action": action,
        "payload": dict(payload or {}),
        "state": "prepared",
        "approval": approval,
        "audit": audit,
        "seal": seal,
        "seal_verification": verify_runtime_seal(seal),
        "committed": False,
        "rolled_back": False,
        "verified": False,
    }


def review_mutation_transaction(
    transaction: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(transaction, Mapping):
        raise TypeError("transaction must be a mapping")

    current_state = transaction.get("state")

    if current_state != "prepared":
        return {
            **dict(transaction),
            "state": current_state,
            "transition": "review_skipped",
        }

    return {
        **dict(transaction),
        "state": "review_required",
        "transition": "review_required",
    }


def approve_mutation_transaction(
    transaction: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(transaction, Mapping):
        raise TypeError("transaction must be a mapping")

    approval = transaction.get("approval")
    if not isinstance(approval, dict):
        raise TypeError("transaction.approval must be a dict")

    approved = transition_approval_state(
        approval_request=approval,
        decision="approve",
    )

    next_state = "approved" if is_execution_approved(approved) else "blocked"

    return {
        **dict(transaction),
        "state": next_state,
        "transition": "approved" if next_state == "approved" else "blocked",
        "approval": approved,
    }


def deny_mutation_transaction(
    transaction: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(transaction, Mapping):
        raise TypeError("transaction must be a mapping")

    approval = transaction.get("approval")
    if not isinstance(approval, dict):
        raise TypeError("transaction.approval must be a dict")

    denied = transition_approval_state(
        approval_request=approval,
        decision="deny",
    )

    return {
        **dict(transaction),
        "state": "denied",
        "transition": "denied",
        "approval": denied,
    }


def commit_mutation_transaction(
    transaction: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(transaction, Mapping):
        raise TypeError("transaction must be a mapping")

    if transaction.get("state") != "approved":
        return {
            **dict(transaction),
            "state": transaction.get("state"),
            "transition": "commit_blocked",
            "committed": False,
        }

    seal_verification = transaction.get("seal_verification", {})
    if not isinstance(seal_verification, Mapping):
        raise TypeError("transaction.seal_verification must be a mapping")

    if seal_verification.get("valid") is not True:
        return {
            **dict(transaction),
            "state": "seal_invalid",
            "transition": "commit_blocked",
            "committed": False,
        }

    return {
        **dict(transaction),
        "state": "committed",
        "transition": "committed",
        "committed": True,
        "rolled_back": False,
    }


def rollback_mutation_transaction(
    transaction: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(transaction, Mapping):
        raise TypeError("transaction must be a mapping")

    return {
        **dict(transaction),
        "state": "rolled_back",
        "transition": "rolled_back",
        "committed": False,
        "rolled_back": True,
        "verified": False,
    }


def verify_mutation_transaction(
    transaction: Mapping[str, Any],
) -> Dict[str, Any]:
    if not isinstance(transaction, Mapping):
        raise TypeError("transaction must be a mapping")

    if transaction.get("state") != "committed":
        return {
            **dict(transaction),
            "transition": "verification_blocked",
            "verified": False,
        }

    return {
        **dict(transaction),
        "transition": "verified",
        "verified": True,
    }


def build_mutation_transaction_summary() -> Dict[str, Any]:
    mutation = build_mutation_transaction(
        action="mutation_runtime",
        payload={"target": "core/runtime/example.py"},
        transaction_id="summary-mutation",
    )

    patch = build_mutation_transaction(
        action="patch_apply",
        payload={"patch": "diff --git ..."},
        transaction_id="summary-patch",
    )

    return {
        "mutation_transaction_layer": "snapshot_loader_mutation_transaction",
        "transactions": [mutation, patch],
        "transaction_actions": [
            mutation["action"],
            patch["action"],
        ],
        "transaction_states": [
            mutation["state"],
            patch["state"],
        ],
    }