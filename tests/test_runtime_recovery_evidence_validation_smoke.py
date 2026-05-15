from __future__ import annotations

from core.runtime.execution_audit import ExecutionAuditRecord
from core.runtime.execution_plan import ExecutionPlan
from core.runtime.execution_plan_snapshot import ExecutionPlanSnapshot
from core.runtime.execution_replay import ExecutionReplayVerifier
from core.runtime.rollback_verification import RollbackVerificationVerifier
from core.runtime.runtime_evidence_bundle import RuntimeEvidenceBundle
from core.runtime.runtime_evidence_replay_validation import RuntimeEvidenceReplayValidator
from core.runtime.runtime_execution_graph import RuntimeExecutionGraph
from core.runtime.runtime_mainline_evidence_seal import build_runtime_mainline_evidence_seal
from core.runtime.runtime_operation import RuntimeOperation
from core.runtime.runtime_recovery_evidence_attachment import attach_runtime_recovery_evidence
from core.runtime.runtime_recovery_evidence_replay_validation_attachment import (
    attach_recovery_evidence_to_replay_validation,
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
        metadata={"source": {"name": "recovery-validation-smoke"}},
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
        metadata={"audit": {"source": "recovery-validation-smoke"}},
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
        metadata={"bundle": {"source": "recovery-validation-smoke"}},
        runtime_args={"bundle_runtime": {"mode": "portable"}},
        created_at="bundle-time",
    )


def test_runtime_recovery_evidence_validation_smoke_chain_ready() -> None:
    recovery_source = {
        "operator_summary": {
            "ok": True,
            "status": "ready",
            "readiness": "ready",
            "summary": "Recovery gate passed.",
            "blockers": [],
        }
    }

    evidence_attachment = attach_runtime_recovery_evidence(
        bundle=_bundle(),
        source=recovery_source,
        audit_id="audit-smoke",
        recovery_id="recovery-smoke",
    )

    validation_report = RuntimeEvidenceReplayValidator().validate(
        build_runtime_mainline_evidence_seal(
            workspace_root="workspace",
            seal_id="recovery-evidence-validation-smoke",
        )
    )

    validation_attachment = attach_recovery_evidence_to_replay_validation(
        validation_report=validation_report,
        evidence_attachment=evidence_attachment,
    )

    assert validation_attachment["validation_ok"] is True
    assert validation_attachment["validation_issue_count"] == 0
    assert validation_attachment["recovery_readiness"] == "ready"
    assert validation_attachment["evidence_attachment"]["bundle_id"] == "bundle-1"


def test_runtime_recovery_evidence_validation_smoke_chain_blocked() -> None:
    recovery_source = {
        "operator_summary": {
            "ok": False,
            "status": "blocked",
            "readiness": "blocked",
            "summary": "Blocked.",
            "blockers": ["missing confirmation"],
        }
    }

    evidence_attachment = attach_runtime_recovery_evidence(
        bundle=_bundle(),
        source=recovery_source,
    )

    validation_report = RuntimeEvidenceReplayValidator().validate(None)

    validation_attachment = attach_recovery_evidence_to_replay_validation(
        validation_report=validation_report,
        evidence_attachment=evidence_attachment,
    )

    assert validation_attachment["validation_ok"] is False
    assert validation_attachment["validation_issue_count"] > 0
    assert validation_attachment["recovery_readiness"] == "blocked"
