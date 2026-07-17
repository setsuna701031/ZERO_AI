from __future__ import annotations

from core.runtime.runtime_lifecycle_coordinator import RuntimeLifecycleCoordinator


def test_lifecycle_transition_persists_runtime_transition_result() -> None:
    coordinator = RuntimeLifecycleCoordinator()
    created = coordinator.create_record(
        lifecycle_id="life-transition-constitution-1",
        artifact_id="artifact-transition-constitution-1",
        artifact_type="session",
    )

    active = coordinator.mark_active(created.record.lifecycle_id, metadata={"phase": "activate"})

    assert active.status == "transitioned"
    assert "runtime_transition_result" in active.metadata
    assert "runtime_transition_record" in active.metadata
    assert "runtime_transition_evidence" in active.metadata

    transition_result = active.metadata["runtime_transition_result"]
    transition_record = active.metadata["runtime_transition_record"]
    transition_evidence = active.metadata["runtime_transition_evidence"]

    assert transition_result["schema"] == "runtime_transition_result.v1"
    assert transition_record["schema"] == "runtime_transition_record.v1"
    assert transition_evidence["schema"] == "runtime_transition_evidence.v1"
    assert transition_record["lifecycle_id"] == created.record.lifecycle_id
    assert transition_record["artifact_id"] == created.record.artifact_id
    assert transition_record["artifact_type"] == "session"
    assert transition_record["from_state"] == "created"
    assert transition_record["to_state"] == "active"
    assert transition_result["record"]["transition_id"] == transition_record["transition_id"]
    assert transition_evidence["transition_id"] == transition_record["transition_id"]


def test_lifecycle_blocked_transition_persists_constitution_without_guard_execution() -> None:
    coordinator = RuntimeLifecycleCoordinator()
    created = coordinator.create_record(
        lifecycle_id="life-transition-constitution-2",
        artifact_id="artifact-transition-constitution-2",
        artifact_type="session",
    )

    blocked = coordinator.seal(created.record.lifecycle_id, metadata={"phase": "invalid_seal"})

    assert blocked.status == "blocked"
    assert blocked.transitioned is False
    assert blocked.metadata["runtime_transition_guard"]["reason"] == "guard_not_evaluated"

    transition_result = blocked.metadata["runtime_transition_result"]
    transition_record = blocked.metadata["runtime_transition_record"]
    transition_evidence = blocked.metadata["runtime_transition_evidence"]

    assert transition_result["schema"] == "runtime_transition_result.v1"
    assert transition_result["ok"] is False
    assert transition_record["allowed"] is False
    assert transition_record["status"] == "blocked"
    assert transition_record["from_state"] == "created"
    assert transition_record["to_state"] == "sealed"
    assert transition_evidence["transition_id"] == transition_record["transition_id"]


def test_lifecycle_transition_history_carries_runtime_transition_result() -> None:
    coordinator = RuntimeLifecycleCoordinator()
    created = coordinator.create_record(
        lifecycle_id="life-transition-constitution-3",
        artifact_id="artifact-transition-constitution-3",
        artifact_type="session",
    )

    active = coordinator.mark_active(created.record.lifecycle_id)
    record = coordinator.get_record(active.record.lifecycle_id)

    assert len(record.transition_history) == 1
    event = record.transition_history[0]

    assert "runtime_transition_result" in event
    assert "runtime_transition_result" in event["metadata"]
    assert event["runtime_transition_result"]["schema"] == "runtime_transition_result.v1"
    assert event["metadata"]["runtime_transition_record"]["schema"] == "runtime_transition_record.v1"
    assert record.metadata["last_runtime_transition_result"]["schema"] == "runtime_transition_result.v1"
