from __future__ import annotations


def test_build_transition_evidence_shape() -> None:
    from core.runtime.runtime_transition_evidence import build_transition_evidence

    evidence = build_transition_evidence(
        "queued",
        "running",
        trigger="dispatch",
        source="unit-test",
        reason="executor accepted task",
        metadata={"task_id": "task-1"},
    )

    assert evidence["from_status"] == "queued"
    assert evidence["to_status"] == "running"
    assert evidence["trigger"] == "dispatch"
    assert evidence["source"] == "unit-test"
    assert evidence["reason"] == "executor accepted task"
    assert "evidence_timestamp" in evidence
    assert evidence["transition_evidence_id"].startswith("transition-evidence-")


def test_transition_evidence_reasons_from_execution_result() -> None:
    from core.runtime.runtime_transition_evidence import build_transition_evidence

    assert "execution completed" in build_transition_evidence(
        "running",
        "executed",
        runtime_execution_result={"ok": True},
    )["reason"]
    assert "verification completed" in build_transition_evidence(
        "verifying",
        "verified",
        runtime_execution_result={"ok": True, "verification_passed": True},
    )["reason"]
    assert "execution failure" in build_transition_evidence(
        "running",
        "failed",
        runtime_execution_result={"failed": True},
    )["reason"]
    assert "policy" in build_transition_evidence(
        "running",
        "blocked",
        runtime_execution_result={"blocked": True},
    )["reason"]
    assert "rollback" in build_transition_evidence("verifying", "rolling_back")["reason"]
    assert "replay" in build_transition_evidence("replaying", "replayed")["reason"]
    assert "recovery" in build_transition_evidence("recovering", "recovered")["reason"]
    assert "seal" in build_transition_evidence("verified", "sealed")["reason"]


def test_transition_lineage_summary_and_merge() -> None:
    from core.runtime.runtime_transition_evidence import (
        merge_transition_evidence,
        transition_lineage_summary,
    )

    summary = transition_lineage_summary(
        {
            "canonical_status": "verified",
            "canonical_from_status": "verifying",
            "canonical_to_status": "verified",
            "runtime_execution_result": {"ok": True, "verification_passed": True},
        }
    )
    merged = merge_transition_evidence(
        {"transition_evidence_id": "old", "reason": "old reason"},
        summary["transition_evidence"],
    )

    assert summary["canonical_status"] == "verified"
    assert "verification completed" in summary["transition_reason"]
    assert summary["transition_trigger"] == "verification"
    assert summary["transition_source"]
    assert summary["transition_evidence"]
    assert len(merged["history"]) == 2


def test_status_transition_summary_contains_evidence() -> None:
    from core.runtime.runtime_status_transition import canonical_transition_summary

    summary = canonical_transition_summary(
        "running",
        "executed",
        runtime_execution_result={"ok": True},
    )

    assert summary["allowed"] is True
    assert summary["canonical_transition"] == "running->executed"
    assert "execution completed" in summary["transition_reason"]
    assert summary["transition_evidence"]


def test_lifecycle_and_kernel_transition_payloads_expose_evidence() -> None:
    from core.runtime.runtime_kernel_state import RuntimeKernelStateMachine
    from core.runtime.runtime_lifecycle_coordinator import RuntimeLifecycleCoordinator

    coordinator = RuntimeLifecycleCoordinator()
    coordinator.create_record(
        lifecycle_id="life-evidence",
        artifact_id="artifact-evidence",
        artifact_type="execution",
    )
    lifecycle_report = coordinator.mark_active("life-evidence").to_metadata()
    kernel_report = RuntimeKernelStateMachine().transition("SCANNING", reason="scan").to_dict()

    assert lifecycle_report["transition_evidence"]
    assert lifecycle_report["transition_reason"]
    assert kernel_report["transition_evidence"]
    assert kernel_report["transition_source"]


def test_recovery_replay_transaction_payloads_expose_evidence() -> None:
    from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
    from core.runtime.runtime_recovery_reconstruction import (
        build_runtime_recovery_reconstruction_contract,
    )
    from core.runtime.runtime_replay_engine import RuntimeReplayEngine
    from core.runtime.runtime_transaction_coordinator import RuntimeTransactionCoordinator

    transaction = RuntimeTransactionCoordinator()
    transaction.begin_transaction(transaction_id="tx-evidence")
    transaction_report = transaction.commit("tx-evidence").to_metadata()
    recovery_report = build_runtime_recovery_reconstruction_contract(
        source_transaction_id="tx-evidence",
        source_evidence_chain=[{"evidence_id": "ev-1"}],
        reconstruction_state="consistent",
    )

    manager = RuntimeExecutionSessionManager()
    manager.create_session("session-evidence", "life-evidence", replay_group="group-evidence")
    replay = RuntimeReplayEngine(manager).replay_session(
        "replay-evidence",
        "session-evidence",
    )

    assert transaction_report["transition_evidence"]
    assert recovery_report["transition_evidence"]
    assert replay.transition_evidence
    assert replay.records[0].transition_evidence
