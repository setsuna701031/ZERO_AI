from __future__ import annotations

from core.runtime.runtime_execution_fabric import RuntimeExecutionFabric
from core.runtime.runtime_recovery_orchestrator import RuntimeRecoveryOrchestrator
from core.runtime.runtime_transaction_fabric import RuntimeTransactionFabric


def test_runtime_transaction_fabric_full_execution_recovery_consistency_mainline(tmp_path):
    orchestrator = RuntimeRecoveryOrchestrator.with_workspace(
        tmp_path / "recovery",
        runner=lambda payload: {
            "ok": True,
            "status": "completed",
            "execution_id": "transaction-recovery-execution",
            "replay_id": "transaction-replay",
        },
    )
    execution_fabric = RuntimeExecutionFabric.with_workspace(
        tmp_path / "execution_fabric",
        recovery_orchestrator=orchestrator,
    )
    transaction_fabric = RuntimeTransactionFabric.with_workspace(
        tmp_path / "transaction_fabric",
        recovery_orchestrator=orchestrator,
        execution_fabric=execution_fabric,
    )

    execution = execution_fabric.start_execution(
        source_session_id="seal-session",
        task_id="seal-task",
        steps=[
            {"type": "transaction", "name": "atomic-edit"},
            {"type": "work", "name": "after-transaction"},
        ],
    )

    tx = transaction_fabric.begin_transaction(
        source_session_id="seal-session",
        execution_id=execution.execution_id,
        task_id="seal-task",
        before_snapshot={"files": {"target.py": "before"}},
        steps=[
            {"type": "write", "path": "target.py"},
            {"type": "verify", "path": "target.py"},
        ],
    )

    failed = transaction_fabric.execute_transaction(
        tx.transaction_id,
        runner=lambda step, context: {"ok": False, "failed": True, "message": "verify failed"} if step.action_type == "verify" else {"ok": True},
    )

    assert failed.status == "failed"
    assert failed.boundary.status == "broken"

    rolled = transaction_fabric.rollback_transaction(
        tx.transaction_id,
        reason="verification failed",
    )

    assert rolled.status == "rolled_back"
    assert rolled.boundary.after_snapshot == {"files": {"target.py": "before"}}

    queued = transaction_fabric.queue_recovery(
        tx.transaction_id,
        current_tick=5,
        reason="transaction rollback requires recovery continuation",
    )

    assert queued.status == "recovery_queued"

    recovered = transaction_fabric.consume_recovery_and_continue(
        tx.transaction_id,
        current_tick=5,
    )

    assert recovered.status == "recovered"
    assert recovered.continuation_ref["status"] == "ready"
    assert recovered.recovery_result["recovery_result"]["replay_id"] == "transaction-replay"

    execution_fabric.record_step_result(
        execution.execution_id,
        step_index=1,
        step={"type": "transaction", "name": "atomic-edit"},
        result={
            "ok": True,
            "transaction_id": tx.transaction_id,
            "transaction_status": recovered.status,
        },
    )
    completed = execution_fabric.complete_execution(
        execution.execution_id,
        result={"ok": True, "final_answer": "transactional execution completed"},
    )

    assert completed.status == "completed"

    lineage = orchestrator.lineage.lineage_for_ref("seal-session")
    node_types = {node["node_type"] for node in lineage["nodes"]}
    assert "source_session" in node_types
    assert "incident" in node_types
    assert "recovery_ticket" in node_types
    assert "recovery" in node_types
    assert "runtime_replay" in node_types
