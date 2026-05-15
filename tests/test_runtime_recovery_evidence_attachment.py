from __future__ import annotations

from core.runtime.execution_audit import ExecutionAuditRecord
from core.runtime.execution_plan import ExecutionPlan
from core.runtime.execution_plan_snapshot import ExecutionPlanSnapshot
from core.runtime.execution_replay import ExecutionReplayVerifier
from core.runtime.rollback_verification import RollbackVerificationVerifier
from core.runtime.runtime_evidence_bundle import RuntimeEvidenceBundle
from core.runtime.runtime_execution_graph import RuntimeExecutionGraph
from core.runtime.runtime_operation import RuntimeOperation
from core.runtime.runtime_recovery_evidence_attachment import (
    RuntimeRecoveryEvidenceAttachment,
    attach_runtime_recovery_evidence,
)
from core.runtime.runtime_transaction import RuntimeTransaction


def _bundle() -> RuntimeEvidenceBundle:
    graph = RuntimeExecutionGraph()
    graph.add_node("op-1", "lifecycle.queue")

    transaction = RuntimeTransaction("tx-1")
    transaction.add_operation(
        RuntimeOperation(
            "op-1",
            "lifecycle.queue",
            runtime_args={"operation_arg": "op-1"},
            metadata={"operation": "lifecycle.queue"},
        )
    )

    plan = ExecutionPlan(
        "plan-1",
        graph,
        transaction,
        runtime_args={"scope": {"name": "runtime"}},
        metadata={"source": {"name": "recovery-evidence-test"}},
    )

    snapshot = ExecutionPlanSnapshot.from_plan(
        "snapshot-1",
        plan,
        created_at="snapshot-time",
    )

    replay = ExecutionReplayVerifier("replay-1").verify_snapshot(snapshot)

    audit = ExecutionAuditRecord.from_replay_record(
        "audit-1",
        replay,
        metadata={"audit": {"source": "recovery-evidence-test"}},
        runtime_args={"audit_runtime": {"mode": "verify"}},
        created_at="audit-time",
    )

    rollback = RollbackVerificationVerifier("rollback-1").verify_snapshot_rollback(
        snapshot,
        created_at="rollback-time",
    )

    return RuntimeEvidenceBundle(
        "bundle-1",
        snapshot,
        replay,
        audit,
        rollback,
        metadata={"bundle": {"source": "recovery-evidence-test"}},
        runtime_args={"bundle_runtime": {"mode": "portable"}},
        created_at="bundle-time",
    )


def test_attach_runtime_recovery_evidence() -> None:
    attachment = attach_runtime_recovery_evidence(
        bundle=_bundle(),
        source={
            "operator_summary": {
                "ok": True,
                "status": "ready",
                "readiness": "ready",
                "summary": "Recovery gate passed.",
                "blockers": [],
            }
        },
        audit_id="audit-x",
        recovery_id="recovery-x",
    )

    assert attachment["schema"] == RuntimeRecoveryEvidenceAttachment.SCHEMA
    assert attachment["bundle_id"] == "bundle-1"
    assert attachment["plan_id"] == "plan-1"
    assert attachment["snapshot_id"] == "snapshot-1"
    assert attachment["recovery_artifact"]["audit_id"] == "audit-x"
    assert attachment["recovery_artifact"]["readiness"] == "ready"


def test_attach_runtime_recovery_evidence_blocked() -> None:
    attachment = attach_runtime_recovery_evidence(
        bundle=_bundle(),
        source={
            "operator_summary": {
                "ok": False,
                "status": "blocked",
                "readiness": "blocked",
                "summary": "Blocked.",
                "blockers": ["missing confirmation"],
            }
        },
    )

    artifact = attachment["recovery_artifact"]

    assert artifact["readiness"] == "blocked"
    assert artifact["blockers"] == ["missing confirmation"]
