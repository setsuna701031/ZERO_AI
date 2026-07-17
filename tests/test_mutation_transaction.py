from __future__ import annotations

import pytest

from core.runtime.snapshot_loader.mutation_transaction import (
    approve_mutation_transaction,
    build_mutation_transaction,
    build_mutation_transaction_summary,
    commit_mutation_transaction,
    deny_mutation_transaction,
    review_mutation_transaction,
    rollback_mutation_transaction,
    verify_mutation_transaction,
)


def test_build_mutation_transaction_contract() -> None:
    transaction = build_mutation_transaction(
        action="mutation_runtime",
        payload={"target": "core/runtime/example.py"},
        transaction_id="tx-1",
    )

    assert transaction["transaction_id"] == "tx-1"
    assert transaction["transaction_runtime"] == "snapshot_loader_mutation_transaction"
    assert transaction["action"] == "mutation_runtime"
    assert transaction["payload"] == {"target": "core/runtime/example.py"}
    assert transaction["state"] == "prepared"
    assert transaction["approval"]["state"] == "pending_review"
    assert transaction["audit"]["policy_decision"] == "review_required"
    assert transaction["seal_verification"]["valid"] is True
    assert transaction["committed"] is False
    assert transaction["rolled_back"] is False
    assert transaction["verified"] is False


def test_build_patch_transaction_contract() -> None:
    transaction = build_mutation_transaction(
        action="patch_apply",
        payload={"patch": "diff --git ..."},
        transaction_id="tx-patch",
    )

    assert transaction["action"] == "patch_apply"
    assert transaction["state"] == "prepared"
    assert transaction["approval"]["state"] == "pending_review"
    assert transaction["audit"]["classification"] == "patch"


def test_build_transaction_rejects_non_mutation_action() -> None:
    with pytest.raises(ValueError):
        build_mutation_transaction(
            action="readonly_execution",
            transaction_id="bad",
        )


def test_review_mutation_transaction_moves_to_review_required() -> None:
    transaction = build_mutation_transaction(
        action="mutation_runtime",
        transaction_id="tx-review",
    )

    reviewed = review_mutation_transaction(transaction)

    assert reviewed["state"] == "review_required"
    assert reviewed["transition"] == "review_required"


def test_approve_mutation_transaction_moves_to_approved() -> None:
    transaction = build_mutation_transaction(
        action="mutation_runtime",
        transaction_id="tx-approve",
    )

    approved = approve_mutation_transaction(transaction)

    assert approved["state"] == "approved"
    assert approved["transition"] == "approved"
    assert approved["approval"]["state"] == "approved"


def test_deny_mutation_transaction_moves_to_denied() -> None:
    transaction = build_mutation_transaction(
        action="mutation_runtime",
        transaction_id="tx-deny",
    )

    denied = deny_mutation_transaction(transaction)

    assert denied["state"] == "denied"
    assert denied["transition"] == "denied"
    assert denied["approval"]["state"] == "denied"


def test_commit_blocks_when_not_approved() -> None:
    transaction = build_mutation_transaction(
        action="mutation_runtime",
        transaction_id="tx-block",
    )

    committed = commit_mutation_transaction(transaction)

    assert committed["state"] == "prepared"
    assert committed["transition"] == "commit_blocked"
    assert committed["committed"] is False


def test_commit_after_approval() -> None:
    transaction = build_mutation_transaction(
        action="mutation_runtime",
        transaction_id="tx-commit",
    )

    approved = approve_mutation_transaction(transaction)
    committed = commit_mutation_transaction(approved)

    assert committed["state"] == "committed"
    assert committed["transition"] == "committed"
    assert committed["committed"] is True
    assert committed["rolled_back"] is False


def test_commit_blocks_when_seal_invalid() -> None:
    transaction = build_mutation_transaction(
        action="mutation_runtime",
        transaction_id="tx-invalid-seal",
    )

    approved = approve_mutation_transaction(transaction)
    approved["seal_verification"]["valid"] = False

    committed = commit_mutation_transaction(approved)

    assert committed["state"] == "seal_invalid"
    assert committed["transition"] == "commit_blocked"
    assert committed["committed"] is False


def test_rollback_mutation_transaction() -> None:
    transaction = build_mutation_transaction(
        action="mutation_runtime",
        transaction_id="tx-rollback",
    )

    rolled_back = rollback_mutation_transaction(transaction)

    assert rolled_back["state"] == "rolled_back"
    assert rolled_back["transition"] == "rolled_back"
    assert rolled_back["committed"] is False
    assert rolled_back["rolled_back"] is True
    assert rolled_back["verified"] is False


def test_verify_blocks_when_not_committed() -> None:
    transaction = build_mutation_transaction(
        action="mutation_runtime",
        transaction_id="tx-verify-block",
    )

    verified = verify_mutation_transaction(transaction)

    assert verified["transition"] == "verification_blocked"
    assert verified["verified"] is False


def test_verify_after_commit() -> None:
    transaction = build_mutation_transaction(
        action="mutation_runtime",
        transaction_id="tx-verify",
    )

    approved = approve_mutation_transaction(transaction)
    committed = commit_mutation_transaction(approved)
    verified = verify_mutation_transaction(committed)

    assert verified["transition"] == "verified"
    assert verified["verified"] is True


def test_mutation_transaction_summary_contract() -> None:
    summary = build_mutation_transaction_summary()

    assert summary["mutation_transaction_layer"] == (
        "snapshot_loader_mutation_transaction"
    )
    assert summary["transaction_actions"] == [
        "mutation_runtime",
        "patch_apply",
    ]
    assert summary["transaction_states"] == [
        "prepared",
        "prepared",
    ]
    assert len(summary["transactions"]) == 2