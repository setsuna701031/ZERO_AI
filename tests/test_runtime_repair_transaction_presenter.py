from __future__ import annotations

from core.display.runtime_repair_transaction_presenter import (
    classify_runtime_repair_transaction_risk,
    format_runtime_repair_transaction,
    is_runtime_repair_transaction_commit_ready,
    is_runtime_repair_transaction_rollback_ready,
)
from core.tasks.runtime_repair_transaction import (
    commit_runtime_repair_transaction,
    create_runtime_repair_transaction,
    rollback_runtime_repair_transaction,
    stage_runtime_repair_mutation,
)


def test_format_runtime_repair_transaction_renders_deterministic_output() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-demo",
        proposal_id="proposal-demo",
        goal="repair transaction presenter demo",
        scope_gate={
            "scope_status": "allowed",
            "scope_allowed": True,
            "allowed_next_action": "build_patch_preview",
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

    rendered = format_runtime_repair_transaction(tx)

    assert "Runtime Repair Transaction:" in rendered
    assert "task-demo" in rendered
    assert "proposal-demo" in rendered
    assert "staged_mutations" in rendered
    assert "workspace/shared/demo.txt" in rendered
    assert "risk_level: medium" in rendered
    assert "commit_ready: true" in rendered


def test_classify_runtime_repair_transaction_risk_detects_high_risk_paths() -> None:
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
            "action": "write_file",
            "target_path": "core/tasks/scheduler.py",
            "content": "danger",
        },
    )

    risk = classify_runtime_repair_transaction_risk(tx)

    assert risk == "high"


def test_classify_runtime_repair_transaction_risk_detects_critical_scope_block() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-critical",
        proposal_id="proposal-critical",
        scope_gate={
            "scope_allowed": False,
            "blocked_reasons": [
                "path_blocked:core/tasks/scheduler.py:blocked_path_pattern"
            ],
        },
    )

    risk = classify_runtime_repair_transaction_risk(tx)

    assert risk == "critical"


def test_is_runtime_repair_transaction_commit_ready_requires_scope_and_staged_mutations() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-ready",
        proposal_id="proposal-ready",
        scope_gate={
            "scope_allowed": True,
        },
    )

    assert is_runtime_repair_transaction_commit_ready(tx) is False

    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": "workspace/shared/demo.txt",
            "content": "hello",
        },
    )

    assert is_runtime_repair_transaction_commit_ready(tx) is True


def test_is_runtime_repair_transaction_commit_ready_blocks_scope_failure() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-blocked",
        proposal_id="proposal-blocked",
        scope_gate={
            "scope_allowed": False,
        },
    )

    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": "core/tasks/scheduler.py",
            "content": "blocked",
        },
    )

    assert is_runtime_repair_transaction_commit_ready(tx) is False


def test_is_runtime_repair_transaction_rollback_ready_tracks_runtime_states() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-rollback",
        proposal_id="proposal-rollback",
        scope_gate={
            "scope_allowed": True,
        },
    )

    assert is_runtime_repair_transaction_rollback_ready(tx) is False

    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": "workspace/shared/demo.txt",
            "content": "hello",
        },
    )

    assert is_runtime_repair_transaction_rollback_ready(tx) is True

    committed = commit_runtime_repair_transaction(tx)

    assert is_runtime_repair_transaction_rollback_ready(committed) is True

    rolled_back = rollback_runtime_repair_transaction(
        committed,
        reason="verify_failed",
    )

    assert is_runtime_repair_transaction_rollback_ready(rolled_back) is False


def test_format_runtime_repair_transaction_renders_audit_events() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-audit",
        proposal_id="proposal-audit",
        scope_gate={
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

    rendered = format_runtime_repair_transaction(tx)

    assert "audit_events" in rendered
    assert "transaction_created" in rendered
    assert "mutation_staged" in rendered