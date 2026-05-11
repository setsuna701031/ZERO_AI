from __future__ import annotations

from core.tasks.runtime_audit_registry import RuntimeAuditRegistry
from core.tasks.runtime_repair_transaction import (
    commit_runtime_repair_transaction,
    create_runtime_repair_transaction,
    register_runtime_repair_transaction_snapshot,
    rollback_runtime_repair_transaction,
    stage_runtime_repair_mutation,
    summarize_runtime_repair_transaction,
)


def test_create_runtime_repair_transaction_is_deterministic_and_created() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-1",
        proposal_id="proposal-1",
        goal="repair demo",
        authorization={
            "task_id": "task-1",
            "proposal_id": "proposal-1",
            "authorized": True,
        },
        scope_gate={
            "task_id": "task-1",
            "proposal_id": "proposal-1",
            "scope_allowed": True,
        },
    )

    assert tx["transaction_type"] == "runtime_repair_transaction"
    assert tx["transaction_version"] == "runtime_repair_transaction.v1"
    assert tx["transaction_id"].startswith("runtime_repair_tx:task-1:proposal-1:")
    assert tx["state"] == "created"
    assert tx["staged_mutations"] == []
    assert tx["committed_mutations"] == []
    assert tx["rolled_back_mutations"] == []
    assert tx["audit_events"][0]["event_type"] == "transaction_created"


def test_stage_runtime_repair_mutation_records_mutation_without_side_effects() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-2",
        proposal_id="proposal-2",
        scope_gate={"scope_allowed": True},
    )

    staged = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": "workspace/shared/demo.txt",
            "content": "hello",
        },
    )

    assert staged["state"] == "staged"
    assert len(staged["staged_mutations"]) == 1
    assert staged["staged_mutations"][0]["action"] == "write_file"
    assert staged["staged_mutations"][0]["target_path"] == "workspace/shared/demo.txt"
    assert staged["staged_mutations"][0]["mutation_id"].startswith("repair_mutation:")
    assert staged["audit_events"][-1]["event_type"] == "mutation_staged"


def test_commit_runtime_repair_transaction_commits_staged_mutations() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-3",
        proposal_id="proposal-3",
        scope_gate={"scope_allowed": True},
    )
    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": "workspace/shared/demo.txt",
            "content": "hello",
        },
    )

    committed = commit_runtime_repair_transaction(tx)

    assert committed["state"] == "committed"
    assert len(committed["committed_mutations"]) == 1
    assert committed["committed_mutations"][0]["target_path"] == "workspace/shared/demo.txt"
    assert committed["audit_events"][-1]["event_type"] == "transaction_committed"


def test_commit_runtime_repair_transaction_blocks_when_scope_gate_blocks() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-4",
        proposal_id="proposal-4",
        scope_gate={
            "scope_allowed": False,
            "blocked_reasons": ["path_blocked:core/tasks/scheduler.py:blocked_path_pattern"],
        },
    )
    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": "core/tasks/scheduler.py",
            "content": "bad",
        },
    )

    blocked = commit_runtime_repair_transaction(tx)

    assert blocked["state"] == "blocked"
    assert blocked["blocked_reason"] == "scope_gate_not_allowed"
    assert blocked["committed_mutations"] == []
    assert blocked["audit_events"][-1]["event_type"] == "transaction_blocked"


def test_commit_runtime_repair_transaction_blocks_without_staged_mutations() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-5",
        proposal_id="proposal-5",
        scope_gate={"scope_allowed": True},
    )

    blocked = commit_runtime_repair_transaction(tx)

    assert blocked["state"] == "blocked"
    assert blocked["blocked_reason"] == "no_staged_mutations"
    assert blocked["audit_events"][-1]["event_type"] == "transaction_blocked"


def test_rollback_runtime_repair_transaction_rolls_back_staged_mutations() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-6",
        proposal_id="proposal-6",
        scope_gate={"scope_allowed": True},
    )
    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": "workspace/shared/demo.txt",
            "content": "hello",
        },
    )

    rolled_back = rollback_runtime_repair_transaction(
        tx,
        reason="verify_failed",
        rollback_result={
            "ok": True,
            "restored_files": ["workspace/shared/demo.txt"],
        },
    )

    assert rolled_back["state"] == "rolled_back"
    assert rolled_back["rollback_reason"] == "verify_failed"
    assert len(rolled_back["rolled_back_mutations"]) == 1
    assert rolled_back["rollback_result"]["ok"] is True
    assert rolled_back["audit_events"][-1]["event_type"] == "transaction_rolled_back"


def test_register_runtime_repair_transaction_snapshot_can_use_audit_registry() -> None:
    registry = RuntimeAuditRegistry()
    tx = create_runtime_repair_transaction(
        task_id="task-7",
        proposal_id="proposal-7",
        scope_gate={"scope_allowed": True},
    )

    artifact = register_runtime_repair_transaction_snapshot(
        tx,
        task_snapshot={
            "task_id": "task-7",
            "status": "running",
            "goal": "snapshot demo",
            "repair_events": [
                {
                    "event": "repair_context",
                    "repair_action": "transaction snapshot",
                }
            ],
        },
        audit_registry=registry,
    )

    assert artifact["artifact_type"] == "runtime_audit_artifact"
    assert artifact["task_id"] == "task-7"
    assert artifact["artifact_id"].startswith("runtime_audit:task-7:")

    listed = registry.list_runtime_audit_artifacts(task_id="task-7")
    assert len(listed) == 1
    assert listed[0]["artifact_id"] == artifact["artifact_id"]


def test_commit_runtime_repair_transaction_can_register_snapshot_artifact() -> None:
    registry = RuntimeAuditRegistry()
    tx = create_runtime_repair_transaction(
        task_id="task-8",
        proposal_id="proposal-8",
        scope_gate={"scope_allowed": True},
    )
    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": "workspace/shared/demo.txt",
            "content": "hello",
        },
    )

    committed = commit_runtime_repair_transaction(
        tx,
        audit_registry=registry,
        task_snapshot={
            "task_id": "task-8",
            "status": "running",
            "goal": "commit snapshot demo",
        },
    )

    assert committed["state"] == "committed"
    assert len(committed["snapshot_artifacts"]) == 1
    assert committed["snapshot_artifacts"][0]["artifact_type"] == "runtime_audit_artifact"
    assert len(registry.list_runtime_audit_artifacts(task_id="task-8")) == 1


def test_summarize_runtime_repair_transaction_reports_counts() -> None:
    tx = create_runtime_repair_transaction(
        task_id="task-9",
        proposal_id="proposal-9",
        scope_gate={"scope_allowed": True},
    )
    tx = stage_runtime_repair_mutation(
        tx,
        {
            "action": "write_file",
            "target_path": "workspace/shared/demo.txt",
            "content": "hello",
        },
    )

    summary = summarize_runtime_repair_transaction(tx)

    assert summary["transaction_id"].startswith("runtime_repair_tx:task-9:proposal-9:")
    assert summary["task_id"] == "task-9"
    assert summary["proposal_id"] == "proposal-9"
    assert summary["state"] == "staged"
    assert summary["staged_mutation_count"] == 1
    assert summary["committed_mutation_count"] == 0
    assert summary["rolled_back_mutation_count"] == 0
    assert summary["audit_event_count"] == 2