from core.runtime.runtime_state_replication_layer import (
    REPLICATION_FAILED,
    REPLICATION_OK,
    ROLLBACK_ALLOWED,
    SNAPSHOT_ACTIVE,
    SNAPSHOT_RESTORED,
    RuntimeStateReplicationLayer,
)


def test_runtime_state_snapshot_creation():
    runtime = RuntimeStateReplicationLayer()

    snapshot = runtime.create_snapshot(
        runtime_zone="main_runtime",
        runtime_state={"status": "running"},
    )

    assert snapshot.status == SNAPSHOT_ACTIVE
    assert snapshot.runtime_state["status"] == "running"


def test_runtime_state_replication_success():
    runtime = RuntimeStateReplicationLayer()

    snapshot = runtime.create_snapshot(
        runtime_zone="repair_runtime",
        runtime_state={"recovery": "pending"},
    )

    result = runtime.replicate_snapshot(
        snapshot_id=snapshot.snapshot_id,
        target_zone="replay_runtime",
    )

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["replication_status"] == REPLICATION_OK
    assert payload["allowed"] is True


def test_runtime_state_replication_missing_snapshot():
    runtime = RuntimeStateReplicationLayer()

    result = runtime.replicate_snapshot(
        snapshot_id="missing",
        target_zone="replay_runtime",
    )

    assert result.replication_status == REPLICATION_FAILED
    assert result.allowed is False


def test_runtime_state_rollback_restores_snapshot():
    runtime = RuntimeStateReplicationLayer()

    snapshot = runtime.create_snapshot(
        runtime_zone="main_runtime",
        runtime_state={"status": "stable"},
    )

    result = runtime.rollback_to_snapshot(
        snapshot_id=snapshot.snapshot_id,
    )

    assert result.rollback_status == ROLLBACK_ALLOWED
    assert result.snapshot["status"] == SNAPSHOT_RESTORED


def test_runtime_state_replication_log_accumulates():
    runtime = RuntimeStateReplicationLayer()

    snapshot = runtime.create_snapshot(
        runtime_zone="sandbox_runtime",
        runtime_state={"mode": "isolated"},
    )

    runtime.replicate_snapshot(
        snapshot_id=snapshot.snapshot_id,
        target_zone="main_runtime",
    )

    result = runtime.rollback_to_snapshot(
        snapshot_id=snapshot.snapshot_id,
    )

    assert len(result.replication_log) >= 3
