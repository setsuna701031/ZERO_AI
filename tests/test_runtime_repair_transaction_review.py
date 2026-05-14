from __future__ import annotations

from core.tasks.runtime_repair_transaction import (
    commit_runtime_repair_transaction,
    create_runtime_repair_transaction,
    stage_runtime_repair_mutation,
)

from core.tasks.runtime_repair_transaction_review import (
    approve_runtime_repair_transaction_review,
    build_runtime_repair_transaction_review,
    classify_runtime_repair_review_next_action,
    classify_runtime_repair_review_state,
    reject_runtime_repair_transaction_review,
)


def test_build_runtime_repair_transaction_review() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-review",
        proposal_id="proposal-review",
        goal="review demo",
        scope_gate={
            "scope_status": "allowed",
            "scope_allowed": True,
        },
    )

    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": (
                "workspace/shared/demo.txt"
            ),
            "content": "hello",
        },
    )

    review = (
        build_runtime_repair_transaction_review(
            tx
        )
    )

    assert (
        review["review_type"]
        == "runtime_repair_transaction_review"
    )

    assert (
        review["review_version"]
        == "runtime_repair_transaction_review.v1"
    )

    assert (
        review["review_state"]
        == "awaiting_confirmation"
    )

    assert (
        review["risk_level"]
        == "medium"
    )

    assert (
        review["allowed_next_action"]
        == "request_operator_confirmation"
    )

    assert (
        review["confirmation_gate"][
            "confirmation_status"
        ]
        == "pending_confirmation"
    )


def test_build_runtime_repair_transaction_review_blocked() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-blocked",
        proposal_id="proposal-blocked",
        scope_gate={
            "scope_allowed": False,
            "blocked_reasons": [
                "blocked",
            ],
        },
    )

    review = (
        build_runtime_repair_transaction_review(
            tx
        )
    )

    assert (
        review["review_state"]
        == "blocked"
    )

    assert (
        review["allowed_next_action"]
        == "inspect_scope_gate"
    )


def test_approve_runtime_repair_transaction_review() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-approve",
        proposal_id="proposal-approve",
        scope_gate={
            "scope_allowed": True,
        },
    )

    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": (
                "workspace/shared/demo.txt"
            ),
        },
    )

    review = (
        build_runtime_repair_transaction_review(
            tx
        )
    )

    approved = (
        approve_runtime_repair_transaction_review(
            review,
            operator="operator",
            reason="looks safe",
        )
    )

    assert (
        approved["review_state"]
        == "approved"
    )

    assert (
        approved["approval"][
            "confirmation_status"
        ]
        == "approved"
    )

    assert (
        approved["allowed_next_action"]
        == "build_mutation_authorization"
    )


def test_approve_runtime_repair_transaction_review_authorizes_awaiting_transaction() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-approve-lifecycle",
        proposal_id="proposal-approve-lifecycle",
        authorization={
            "requires_approval": True,
        },
        scope_gate={
            "scope_allowed": True,
        },
    )

    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": (
                "workspace/shared/demo.txt"
            ),
        },
    )

    awaiting = commit_runtime_repair_transaction(
        tx
    )
    review = build_runtime_repair_transaction_review(
        awaiting
    )
    approved = approve_runtime_repair_transaction_review(
        review,
        operator="operator",
        reason="looks safe",
    )

    lifecycle = approved["transaction"]

    assert awaiting["state"] == "awaiting_review"
    assert review["review_state"] == "awaiting_confirmation"
    assert lifecycle["state"] == "authorized"
    assert lifecycle["committed_mutations"] == []
    assert [
        event["event_type"]
        for event in lifecycle["audit_events"][-2:]
    ] == [
        "transaction_review_approved",
        "transaction_authorized",
    ]


def test_reject_runtime_repair_transaction_review() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-reject",
        proposal_id="proposal-reject",
        scope_gate={
            "scope_allowed": True,
        },
    )

    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": (
                "workspace/shared/demo.txt"
            ),
        },
    )

    review = (
        build_runtime_repair_transaction_review(
            tx
        )
    )

    rejected = (
        reject_runtime_repair_transaction_review(
            review,
            operator="operator",
            reason="unsafe",
        )
    )

    assert (
        rejected["review_state"]
        == "rejected"
    )

    assert (
        rejected["rejection"][
            "confirmation_status"
        ]
        == "rejected"
    )

    assert (
        rejected["allowed_next_action"]
        == "archive_or_revise_transaction"
    )


def test_reject_runtime_repair_transaction_review_blocks_awaiting_transaction() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-reject-lifecycle",
        proposal_id="proposal-reject-lifecycle",
        authorization={
            "requires_approval": True,
        },
        scope_gate={
            "scope_allowed": True,
        },
    )

    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": (
                "workspace/shared/demo.txt"
            ),
        },
    )

    awaiting = commit_runtime_repair_transaction(
        tx
    )
    review = build_runtime_repair_transaction_review(
        awaiting
    )
    rejected = reject_runtime_repair_transaction_review(
        review,
        operator="operator",
        reason="unsafe",
    )

    lifecycle = rejected["transaction"]

    assert awaiting["state"] == "awaiting_review"
    assert lifecycle["state"] == "blocked"
    assert lifecycle["blocked_reason"] == "unsafe"
    assert lifecycle["committed_mutations"] == []
    assert lifecycle["audit_events"][-1]["event_type"] == "transaction_review_rejected"


def test_classify_runtime_repair_review_state() -> None:
    state = (
        classify_runtime_repair_review_state(
            preview={
                "risk_level": "medium",
            },
            confirmation_gate={
                "confirmation_status": (
                    "pending_confirmation"
                ),
            },
        )
    )

    assert (
        state
        == "awaiting_confirmation"
    )


def test_classify_runtime_repair_review_next_action() -> None:
    action = (
        classify_runtime_repair_review_next_action(
            "approved"
        )
    )

    assert (
        action
        == "build_mutation_authorization"
    )
