from __future__ import annotations

import pytest

from core.runtime.runtime_recovery_orchestrator import RuntimeRecoveryOrchestrator
from core.runtime.runtime_transaction_fabric import (
    BOUNDARY_STATUS_ROLLED_BACK,
    CONSISTENCY_STATUS_MISMATCH,
    CONSISTENCY_STATUS_VERIFIED,
    TRANSACTION_STATUS_COMMITTED,
    TRANSACTION_STATUS_FAILED,
    TRANSACTION_STATUS_RECOVERED,
    TRANSACTION_STATUS_RECOVERY_QUEUED,
    TRANSACTION_STATUS_ROLLED_BACK,
    RuntimeTransactionFabric,
    RuntimeTransactionFabricRejected,
)


def test_transaction_fabric_commit_success(tmp_path):
    fabric = RuntimeTransactionFabric.with_workspace(tmp_path)

    tx = fabric.begin_transaction(
        source_session_id="session-1",
        execution_id="execution-1",
        task_id="task-1",
        before_snapshot={"value": 1},
        steps=[
            {"type": "write", "path": "a.txt"},
            {"type": "verify", "path": "a.txt"},
        ],
    )

    executed = fabric.execute_transaction(tx.transaction_id)

    assert executed.status == "prepared"
    assert all(step.status == "completed" for step in executed.steps)

    committed = fabric.commit_transaction(tx.transaction_id)

    assert committed.status == TRANSACTION_STATUS_COMMITTED
    assert committed.boundary.status == "sealed"


def test_transaction_fabric_failure_and_rollback(tmp_path):
    fabric = RuntimeTransactionFabric.with_workspace(tmp_path)

    tx = fabric.begin_transaction(
        source_session_id="session-2",
        execution_id="execution-2",
        task_id="task-2",
        before_snapshot={"files": {"a.txt": "old"}},
        steps=[
            {"type": "write", "path": "a.txt"},
            {"type": "verify", "path": "a.txt"},
        ],
    )

    def runner(step, context):
        if step.step_index == 2:
            return {"ok": False, "failed": True, "message": "verify failed"}
        return {"ok": True}

    failed = fabric.execute_transaction(tx.transaction_id, runner=runner)

    assert failed.status == TRANSACTION_STATUS_FAILED
    assert failed.boundary.status == "broken"

    rolled = fabric.rollback_transaction(
        tx.transaction_id,
        reason="verify failed",
    )

    assert rolled.status == TRANSACTION_STATUS_ROLLED_BACK
    assert rolled.boundary.status == BOUNDARY_STATUS_ROLLED_BACK
    assert rolled.boundary.after_snapshot == {"files": {"a.txt": "old"}}


def test_transaction_fabric_consistency_report(tmp_path):
    fabric = RuntimeTransactionFabric.with_workspace(tmp_path)

    tx = fabric.begin_transaction(
        source_session_id="session-3",
        before_snapshot={"state": "a"},
        steps=[],
    )

    ok_report = fabric.verify_consistency(
        tx.transaction_id,
        expected_state={"state": "a"},
        actual_state={"state": "a"},
    )

    assert ok_report.status == CONSISTENCY_STATUS_VERIFIED
    assert ok_report.verified is True

    bad_report = fabric.verify_consistency(
        tx.transaction_id,
        expected_state={"state": "a"},
        actual_state={"state": "b"},
    )

    assert bad_report.status == CONSISTENCY_STATUS_MISMATCH
    assert bad_report.verified is False


def test_transaction_fabric_commit_requires_consistency(tmp_path):
    fabric = RuntimeTransactionFabric.with_workspace(tmp_path)

    tx = fabric.begin_transaction(
        source_session_id="session-4",
        before_snapshot={"state": "a"},
        steps=[],
    )
    fabric.execute_transaction(tx.transaction_id)

    with pytest.raises(RuntimeTransactionFabricRejected):
        fabric.commit_transaction(
            tx.transaction_id,
            expected_state={"state": "a"},
            actual_state={"state": "b"},
            require_consistency=True,
        )


def test_transaction_fabric_recovery_continuation(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {
            "ok": True,
            "status": "completed",
            "execution_id": "tx-recovery-exec",
            "replay_id": "tx-replay",
        },
    )
    fabric = RuntimeTransactionFabric.with_workspace(
        tmp_path / "tx",
        recovery_orchestrator=orchestrator,
    )

    tx = fabric.begin_transaction(
        source_session_id="session-5",
        execution_id="execution-5",
        task_id="task-5",
        before_snapshot={"value": "before"},
        steps=[{"type": "write"}, {"type": "verify"}],
    )

    failed = fabric.execute_transaction(
        tx.transaction_id,
        runner=lambda step, context: {"ok": False, "failed": True} if step.step_index == 1 else {"ok": True},
    )

    assert failed.status == TRANSACTION_STATUS_FAILED

    queued = fabric.queue_recovery(
        tx.transaction_id,
        current_tick=1,
        reason="transaction failed",
    )

    assert queued.status == TRANSACTION_STATUS_RECOVERY_QUEUED
    assert queued.recovery_ticket["source_session_id"] == "session-5"

    recovered = fabric.consume_recovery_and_continue(
        tx.transaction_id,
        current_tick=1,
    )

    assert recovered.status == TRANSACTION_STATUS_RECOVERED
    assert recovered.recovery_result["recovery_result"]["replay_id"] == "tx-replay"
    assert recovered.continuation_ref["status"] == "ready"


def test_transaction_fabric_persistence_reload(tmp_path):
    fabric = RuntimeTransactionFabric.with_workspace(tmp_path)

    tx = fabric.begin_transaction(
        source_session_id="session-6",
        execution_id="execution-6",
        task_id="task-6",
        before_snapshot={"x": 1},
        steps=[{"type": "noop"}],
    )
    fabric.execute_transaction(tx.transaction_id)

    reloaded = RuntimeTransactionFabric.with_workspace(tmp_path)
    loaded = reloaded.get_transaction(tx.transaction_id)

    assert loaded.transaction_id == tx.transaction_id
    assert len(loaded.steps) == 1
