from __future__ import annotations

from core.tasks.runtime_audit_registry import (
    RuntimeAuditRegistry,
)

from core.tasks.runtime_repair_transaction import (
    create_runtime_repair_transaction,
    stage_runtime_repair_mutation,
)

from core.tasks.runtime_repair_transaction_review import (
    approve_runtime_repair_transaction_review,
    build_runtime_repair_transaction_review,
)

from core.tasks.runtime_repair_review_artifact import (
    build_runtime_repair_review_artifact,
    build_runtime_repair_review_timeline,
    register_runtime_repair_review_artifact,
    summarize_runtime_repair_review_artifact,
)


def test_build_runtime_repair_review_artifact() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-review-artifact",
        proposal_id="proposal-review-artifact",
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

    artifact = (
        build_runtime_repair_review_artifact(
            review
        )
    )

    assert (
        artifact["artifact_type"]
        == "runtime_repair_review_artifact"
    )

    assert (
        artifact["artifact_version"]
        == "runtime_repair_review_artifact.v1"
    )

    assert (
        artifact["transaction_id"]
        == tx["transaction_id"]
    )

    assert (
        artifact["review_state"]
        == "awaiting_confirmation"
    )

    assert (
        len(
            artifact["review_timeline"]
        )
        == 1
    )


def test_build_runtime_repair_review_artifact_with_action() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-review-action",
        proposal_id="proposal-review-action",
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
            reason="safe",
        )
    )

    artifact = (
        build_runtime_repair_review_artifact(
            review,
            review_action=approved,
        )
    )

    assert (
        len(
            artifact["review_timeline"]
        )
        == 2
    )

    assert (
        artifact["review_timeline"][1][
            "event_type"
        ]
        == "review_action"
    )


def test_register_runtime_repair_review_artifact() -> None:
    registry = RuntimeAuditRegistry()

    tx = create_runtime_repair_transaction(
        task_id="task-register-review",
        proposal_id="proposal-register-review",
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

    artifact = (
        register_runtime_repair_review_artifact(
            review,
            audit_registry=registry,
        )
    )

    assert (
        artifact["artifact_type"]
        == "runtime_audit_artifact"
    )

    listed = (
        registry
        .list_runtime_audit_artifacts(
            task_id=(
                "task-register-review"
            )
        )
    )

    assert len(listed) == 1


def test_build_runtime_repair_review_timeline() -> None:
    review = {
        "review_state": (
            "awaiting_confirmation"
        ),
        "risk_level": "medium",
        "human_summary": (
            "review summary"
        ),
    }

    timeline = (
        build_runtime_repair_review_timeline(
            review
        )
    )

    assert len(timeline) == 1

    assert (
        timeline[0]["event_type"]
        == "review_created"
    )


def test_summarize_runtime_repair_review_artifact() -> None:
    artifact = {
        "artifact_id": "artifact-1",
        "transaction_id": (
            "transaction-1"
        ),
        "task_id": "task-1",
        "proposal_id": (
            "proposal-1"
        ),
        "review_state": (
            "approved"
        ),
        "risk_level": "medium",
        "review_timeline": [
            {
                "event_type": (
                    "review_created"
                )
            },
            {
                "event_type": (
                    "review_action"
                )
            },
        ],
        "human_summary": (
            "artifact summary"
        ),
    }

    summary = (
        summarize_runtime_repair_review_artifact(
            artifact
        )
    )

    assert (
        summary["artifact_id"]
        == "artifact-1"
    )

    assert (
        summary[
            "timeline_event_count"
        ]
        == 2
    )

    assert (
        summary["review_state"]
        == "approved"
    )