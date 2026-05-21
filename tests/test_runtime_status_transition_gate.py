from __future__ import annotations


def test_runtime_status_transition_graph_core_edges() -> None:
    from core.runtime.runtime_status_transition import can_transition_runtime_status

    assert can_transition_runtime_status("queued", "running") is True
    assert can_transition_runtime_status("running", "executed") is True
    assert can_transition_runtime_status("executed", "verified") is True
    assert can_transition_runtime_status("verified", "running") is False
    assert can_transition_runtime_status("failed", "verifying") is False
    assert can_transition_runtime_status("blocked", "executed") is False
    assert can_transition_runtime_status("rolled_back", "committed") is False
    assert can_transition_runtime_status("sealed", "running") is False
    assert can_transition_runtime_status("sealed", "sealed") is True


def test_validate_runtime_status_transition_payload_shape() -> None:
    from core.runtime.runtime_status_transition import (
        runtime_status_transition_payload,
        validate_runtime_status_transition,
    )

    validation = validate_runtime_status_transition("verified", "running")

    assert validation["from_status"] == "verified"
    assert validation["to_status"] == "running"
    assert validation["allowed"] is False
    assert validation["regression"] is True
    assert validation["terminal_from"] is True

    payload = runtime_status_transition_payload(
        "queued",
        "running",
        source="test",
        metadata={"keep": True},
    )

    assert payload["allowed"] is True
    assert payload["regression"] is False
    assert payload["source"] == "test"
    assert payload["metadata"] == {"keep": True}
    assert payload["transition_evidence"]


def test_runtime_lifecycle_coordinator_exposes_transition_gate() -> None:
    from core.runtime.runtime_lifecycle_coordinator import RuntimeLifecycleCoordinator

    coordinator = RuntimeLifecycleCoordinator()
    coordinator.create_record(
        lifecycle_id="life-gate",
        artifact_id="artifact-gate",
        artifact_type="execution",
    )
    result = coordinator.mark_active("life-gate")
    report = result.to_metadata()

    assert report["transition_allowed"] is True
    assert report["transition_regression"] is False
    assert report["decision"]["transition_allowed"] is True


def test_runtime_kernel_state_transition_report_exposes_gate() -> None:
    from core.runtime.runtime_kernel_state import RuntimeKernelStateMachine

    machine = RuntimeKernelStateMachine()
    transition = machine.transition("SCANNING", reason="scan").to_dict()

    assert transition["transition_allowed"] is True
    assert transition["transition_regression"] is False
    assert transition["canonical_from_status"] == "pending"
    assert transition["canonical_to_status"] == "running"


def test_runtime_transaction_coordinator_summary_exposes_transition_gate() -> None:
    from core.runtime.runtime_transaction_coordinator import RuntimeTransactionCoordinator

    coordinator = RuntimeTransactionCoordinator()
    coordinator.begin_transaction(transaction_id="tx-gate")
    result = coordinator.commit("tx-gate").to_metadata()

    assert result["status"] == "committed"
    assert result["transition_allowed"] is True
    assert result["transition_regression"] is False
    assert result["transaction"]["transition_allowed"] is True


def test_recovery_summary_exposes_transition_gate() -> None:
    from core.runtime.runtime_recovery_reconstruction import (
        build_runtime_recovery_reconstruction_contract,
        validate_runtime_recovery_reconstruction,
    )

    payload = build_runtime_recovery_reconstruction_contract(
        source_transaction_id="tx-recovery-gate",
        source_evidence_chain=[{"evidence_id": "ev-1"}],
        reconstruction_state="consistent",
    )
    report = validate_runtime_recovery_reconstruction(payload)

    assert payload["transition_allowed"] is True
    assert payload["transition_regression"] is False
    assert report["transition_allowed"] is True
    assert report["transition_regression"] is False


def test_replay_summary_exposes_transition_gate() -> None:
    from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
    from core.runtime.runtime_replay_engine import RuntimeReplayEngine

    manager = RuntimeExecutionSessionManager()
    manager.create_session("session-gate", "life-gate", replay_group="group-gate")
    manager.start_session("session-gate")
    manager.complete_session("session-gate")

    replay = RuntimeReplayEngine(manager).replay_session("replay-gate", "session-gate")

    assert replay.transition_allowed is True
    assert replay.transition_regression is False
    assert replay.records
    assert all(hasattr(record, "transition_allowed") for record in replay.records)
