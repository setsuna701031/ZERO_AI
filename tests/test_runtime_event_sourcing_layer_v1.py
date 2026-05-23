from core.runtime.runtime_event_sourcing_layer import (
    EVENT_EXECUTION,
    EVENT_MUTATION,
    EVENT_POLICY,
    EVENT_RECOVERY,
    EVENT_TRANSACTION,
    EVENT_ZONE,
    REBUILD_ALLOWED,
    REBUILD_BLOCKED,
    STREAM_REPLAYED,
    RuntimeEventSourcingLayer,
)


def test_event_sourcing_appends_execution_event():
    runtime = RuntimeEventSourcingLayer()

    event = runtime.append_event(
        event_type=EVENT_EXECUTION,
        runtime_zone="main_runtime",
        payload={"status": "running"},
    )

    assert event.sequence == 1
    assert event.event_type == EVENT_EXECUTION


def test_event_stream_can_be_replayed():
    runtime = RuntimeEventSourcingLayer()

    runtime.append_event(
        event_type=EVENT_EXECUTION,
        runtime_zone="main_runtime",
        payload={"status": "running"},
    )

    runtime.append_event(
        event_type=EVENT_RECOVERY,
        runtime_zone="repair_runtime",
        payload={"recovery": "started"},
    )

    result = runtime.replay_event_stream()

    payload = result.to_dict()

    assert payload["verified"] is True
    assert payload["rebuild_status"] == STREAM_REPLAYED
    assert payload["allowed"] is True
    assert payload["reconstructed_state"]["event_count"] == 2


def test_runtime_state_can_be_rebuilt_from_events():
    runtime = RuntimeEventSourcingLayer()

    runtime.append_event(
        event_type=EVENT_MUTATION,
        runtime_zone="mutation_runtime",
        payload={"patch": "abc"},
    )

    runtime.append_event(
        event_type=EVENT_POLICY,
        runtime_zone="authority_runtime",
        payload={"mode": "safe"},
    )

    result = runtime.rebuild_runtime_state(
        target_zone="mutation_runtime",
    )

    assert result.rebuild_status == REBUILD_ALLOWED
    assert result.allowed is True
    assert len(result.reconstructed_state["events"]) == 1


def test_empty_event_stream_blocks_rebuild():
    runtime = RuntimeEventSourcingLayer()

    result = runtime.rebuild_runtime_state(
        target_zone="main_runtime",
    )

    assert result.rebuild_status == REBUILD_BLOCKED
    assert result.allowed is False


def test_event_stream_preserves_sequence_order():
    runtime = RuntimeEventSourcingLayer()

    runtime.append_event(
        event_type=EVENT_TRANSACTION,
        runtime_zone="main_runtime",
        payload={"tx": 1},
    )

    runtime.append_event(
        event_type=EVENT_ZONE,
        runtime_zone="sandbox_runtime",
        payload={"zone": "isolated"},
    )

    result = runtime.replay_event_stream()

    stream = result.event_stream

    assert stream[0]["sequence"] == 1
    assert stream[1]["sequence"] == 2
