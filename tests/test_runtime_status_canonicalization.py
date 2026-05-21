from __future__ import annotations


def test_normalize_runtime_status_legacy_vocabulary() -> None:
    from core.runtime.runtime_status import (
        normalize_runtime_status,
        status_from_recovery_state,
        status_from_replay_state,
    )

    assert normalize_runtime_status("success") == "executed"
    assert normalize_runtime_status("finished") == "executed"
    assert normalize_runtime_status("exception") == "failed"
    assert normalize_runtime_status("policy_blocked") == "blocked"
    assert normalize_runtime_status("rollback_required") == "rolling_back"
    assert normalize_runtime_status("sealed") == "sealed"
    assert normalize_runtime_status(None) == "unknown"
    assert status_from_recovery_state("consistent") == "recovered"
    assert status_from_recovery_state("failed") == "failed"
    assert status_from_replay_state("replaying") == "replaying"
    assert status_from_replay_state("finished") == "replayed"


def test_status_from_execution_result() -> None:
    from core.runtime.runtime_status import status_from_execution_result

    assert status_from_execution_result({"ok": True}) == "executed"
    assert status_from_execution_result({"executed": True}) == "executed"
    assert status_from_execution_result({"blocked": True, "ok": False}) == "blocked"
    assert status_from_execution_result({"failed": True, "ok": False}) == "failed"
    assert (
        status_from_execution_result(
            {"ok": True, "executed": True, "verification_passed": True}
        )
        == "verified"
    )


def test_canonical_runtime_status_payload_preserves_original_keys() -> None:
    from core.runtime.runtime_status import canonical_runtime_status_payload

    payload = {"status": "finished", "custom": "keep"}
    normalized = canonical_runtime_status_payload(payload)

    assert normalized is not payload
    assert normalized["status"] == "finished"
    assert normalized["custom"] == "keep"
    assert normalized["canonical_status"] == "executed"


def test_runtime_event_bus_adds_canonical_status_without_dropping_status() -> None:
    from core.runtime.runtime_event_bus import RuntimeEventBus

    event = RuntimeEventBus().publish(
        "runtime.kernel",
        "execution_result_recorded",
        payload={
            "status": "finished",
            "runtime_execution_result": {"ok": True, "verification_passed": True},
        },
    )

    assert event.payload["status"] == "finished"
    assert event.payload["canonical_status"] == "verified"
    assert event.payload["runtime_execution_result"]["canonical_status"] == "verified"


def test_runtime_kernel_state_checkpoint_adds_canonical_status() -> None:
    from core.runtime.runtime_kernel_state import RuntimeKernelStateMachine

    checkpoint = RuntimeKernelStateMachine().checkpoint({"status": "finished"})

    assert checkpoint.payload["status"] == "finished"
    assert checkpoint.payload["canonical_status"] == "executed"
    assert checkpoint.to_dict()["canonical_status"] == "pending"


def test_runtime_transaction_coordinator_summary_adds_canonical_status() -> None:
    from core.runtime.runtime_transaction_coordinator import RuntimeTransactionCoordinator

    coordinator = RuntimeTransactionCoordinator()
    result = coordinator.begin_transaction(transaction_id="tx-status")
    metadata = result.to_metadata()

    assert metadata["status"] == "active"
    assert metadata["canonical_status"] == "running"
    assert metadata["transaction"]["canonical_status"] == "running"


def test_lifecycle_phase_to_canonical_status() -> None:
    from core.runtime.runtime_lifecycle_coordinator import RuntimeLifecycleCoordinator
    from core.runtime.runtime_status import status_from_lifecycle_phase

    assert status_from_lifecycle_phase("active") == "running"
    assert status_from_lifecycle_phase("verified") == "verified"

    coordinator = RuntimeLifecycleCoordinator()
    created = coordinator.create_record(
        lifecycle_id="life-status",
        artifact_id="artifact-status",
        artifact_type="execution",
    )
    active = coordinator.mark_active("life-status")

    assert created.to_metadata()["canonical_status"] == "pending"
    assert active.to_metadata()["canonical_status"] == "running"
    assert active.record.to_metadata()["canonical_status"] == "running"


def test_recovery_states_add_canonical_status() -> None:
    from core.runtime.runtime_recovery_reconstruction import (
        build_runtime_recovery_reconstruction_contract,
        validate_runtime_recovery_reconstruction,
    )

    recovered = build_runtime_recovery_reconstruction_contract(
        source_transaction_id="tx-recovery",
        source_evidence_chain=[{"evidence_id": "ev-1"}],
        reconstruction_state="consistent",
    )
    failed = build_runtime_recovery_reconstruction_contract(
        source_transaction_id="tx-recovery",
        source_evidence_chain=[],
        reconstruction_state="failed",
        reconstruction_consistent=False,
    )

    assert recovered["canonical_status"] == "recovered"
    assert failed["canonical_status"] == "failed"
    assert validate_runtime_recovery_reconstruction(failed)["canonical_status"] == "failed"


def test_replay_states_add_canonical_status() -> None:
    from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
    from core.runtime.runtime_replay_engine import RuntimeReplayEngine

    manager = RuntimeExecutionSessionManager()
    manager.create_session("session-status", "life-status", replay_group="group-status")
    manager.start_session("session-status")
    manager.complete_session("session-status")

    replay = RuntimeReplayEngine(manager).replay_session(
        "replay-status",
        "session-status",
    )

    assert replay.canonical_status == "replayed"
    assert replay.records
    assert {record.canonical_status for record in replay.records}
