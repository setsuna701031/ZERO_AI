from __future__ import annotations

from core.tasks.runtime_repair_transaction import (
    commit_runtime_repair_transaction,
    create_runtime_repair_transaction,
    rollback_runtime_repair_transaction,
    stage_runtime_repair_mutation,
)

from core.tasks.runtime_repair_transaction_preview import (
    build_runtime_repair_audit_preview,
    build_runtime_repair_mutation_preview,
    build_runtime_repair_transaction_preview,
    classify_runtime_repair_preview_risk,
    is_runtime_repair_preview_commit_ready,
    is_runtime_repair_preview_rollback_ready,
)


def test_build_runtime_repair_transaction_preview() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-preview",
        proposal_id="proposal-preview",
        goal="preview demo",
        scope_gate={
            "scope_status": "allowed",
            "scope_allowed": True,
        },
    )

    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": "workspace/shared/demo.txt",
            "content": "hello",
        },
    )

    preview = build_runtime_repair_transaction_preview(tx)

    assert (
        preview["preview_type"]
        == "runtime_repair_transaction_preview"
    )

    assert (
        preview["preview_version"]
        == "runtime_repair_transaction_preview.v1"
    )

    assert preview["task_id"] == "task-preview"

    assert preview["risk_level"] == "medium"

    assert preview["commit_ready"] is True

    assert preview["rollback_ready"] is True

    assert (
        preview["mutation_counts"]["staged"]
        == 1
    )

    assert len(
        preview["mutation_preview"]
    ) == 1

    assert "Risk level: medium" in (
        preview["human_summary"]
    )


def test_build_runtime_repair_mutation_preview() -> None:
    preview = build_runtime_repair_mutation_preview(
        [
            {
                "mutation_id": "mutation-1",
                "action": "write_file",
                "target_path": "workspace/shared/demo.txt",
                "content_hash": "abcdef1234567890",
            }
        ]
    )

    assert len(preview) == 1

    assert (
        preview[0]["mutation_id"]
        == "mutation-1"
    )

    assert (
        preview[0]["action"]
        == "write_file"
    )

    assert (
        preview[0]["target_path"]
        == "workspace/shared/demo.txt"
    )

    assert (
        preview[0]["content_hash"]
        == "abcdef123456"
    )


def test_build_runtime_repair_audit_preview() -> None:
    preview = build_runtime_repair_audit_preview(
        [
            {
                "event_type": "transaction_created",
                "status": "created",
                "summary": "created",
            },
            {
                "event_type": "mutation_staged",
                "status": "staged",
                "summary": "staged",
            },
        ]
    )

    assert len(preview) == 2

    assert (
        preview[0]["event_type"]
        == "transaction_created"
    )

    assert (
        preview[1]["event_type"]
        == "mutation_staged"
    )


def test_classify_runtime_repair_preview_risk() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-risk",
        proposal_id="proposal-risk",
        scope_gate={
            "scope_allowed": True,
        },
    )

    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "delete_file",
            "target_path": "workspace/shared/demo.txt",
        },
    )

    risk = classify_runtime_repair_preview_risk(tx)

    assert risk == "high"


def test_classify_runtime_repair_preview_risk_critical() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-critical",
        proposal_id="proposal-critical",
        scope_gate={
            "scope_allowed": False,
            "blocked_reasons": [
                "blocked",
            ],
        },
    )

    risk = classify_runtime_repair_preview_risk(tx)

    assert risk == "critical"


def test_is_runtime_repair_preview_commit_ready() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-ready",
        proposal_id="proposal-ready",
        scope_gate={
            "scope_allowed": True,
        },
    )

    assert (
        is_runtime_repair_preview_commit_ready(tx)
        is False
    )

    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": "workspace/shared/demo.txt",
        },
    )

    assert (
        is_runtime_repair_preview_commit_ready(tx)
        is True
    )


def test_is_runtime_repair_preview_rollback_ready() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-rollback",
        proposal_id="proposal-rollback",
        scope_gate={
            "scope_allowed": True,
        },
    )

    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": "workspace/shared/demo.txt",
        },
    )

    assert (
        is_runtime_repair_preview_rollback_ready(tx)
        is True
    )

    committed = (
        commit_runtime_repair_transaction(tx)
    )

    assert (
        is_runtime_repair_preview_rollback_ready(
            committed
        )
        is True
    )

    rolled_back = (
        rollback_runtime_repair_transaction(
            committed,
            reason="verify_failed",
        )
    )

    assert (
        is_runtime_repair_preview_rollback_ready(
            rolled_back
        )
        is False
    )