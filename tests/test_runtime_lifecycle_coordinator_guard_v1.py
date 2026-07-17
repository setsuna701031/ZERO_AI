from __future__ import annotations

from core.runtime.runtime_lifecycle_coordinator import RuntimeLifecycleCoordinator


def test_lifecycle_coordinator_records_transition_guard_on_seal_path() -> None:
    coordinator = RuntimeLifecycleCoordinator()

    coordinator.create_record(
        lifecycle_id="life-001",
        artifact_id="artifact-001",
        artifact_type="execution",
    )
    coordinator.mark_active("life-001")
    coordinator.mark_verifying("life-001")
    coordinator.mark_verified("life-001")

    result = coordinator.seal("life-001")

    assert result.ok is True
    assert result.transitioned is True

    guard = result.metadata["runtime_transition_guard"]
    assert guard["transition_guarded"] is True
    assert guard["sovereign_to_state"] == "SESSION_SEALED"

    record = coordinator.get_record("life-001")
    last = record.transition_history[-1]
    assert last["metadata"]["runtime_transition_guard"]["sovereign_to_state"] == "SESSION_SEALED"


def test_lifecycle_coordinator_blocks_invalid_policy_before_guard() -> None:
    coordinator = RuntimeLifecycleCoordinator()

    coordinator.create_record(
        lifecycle_id="life-002",
        artifact_id="artifact-002",
        artifact_type="execution",
    )

    result = coordinator.seal("life-002")

    assert result.ok is False
    assert result.status == "blocked"
    assert result.decision.allowed is False
