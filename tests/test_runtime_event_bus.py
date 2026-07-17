from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from core.runtime.runtime_event_bus import (
    CONTRACT,
    EVENT_CONTRACT,
    create_event_bus_state,
    deliver,
    load_event_bus_state,
    publish,
    replay,
    save_event_bus_state,
    subscribe,
    unsubscribe,
    validate_event,
    validate_event_bus_state,
)


NOW = datetime(2026, 7, 12, 6, 0, 0, tzinfo=timezone.utc)


def _create_state(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    state_path = tmp_path / "runtime-event-bus.json"
    state = create_event_bus_state(
        state_path=state_path,
        bus_name="primary",
        now=NOW,
    )
    return state_path, state


def test_create_save_and_load_event_bus_state(
    tmp_path: Path,
) -> None:
    state_path, state = _create_state(tmp_path)

    assert state["contract"] == CONTRACT
    assert state["bus_name"] == "primary"
    assert state["bus_status"] == "created"
    assert state["events"] == {}
    assert state["event_order"] == []
    assert state["next_sequence"] == 1
    assert state["subscriptions"] == {}
    assert validate_event_bus_state(state) == []

    saved = save_event_bus_state(
        state,
        state_path,
    )
    loaded = load_event_bus_state(state_path)

    assert state_path.exists()
    assert loaded == saved
    assert loaded["bus_fingerprint"] == (
        saved["bus_fingerprint"]
    )


def test_publish_creates_valid_event(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)

    updated, event = publish(
        state,
        event_type="mission",
        topic="mission.created",
        source="test-suite",
        payload={
            "mission_id": "mission-1",
            "mission_status": "created",
        },
        correlation_id="correlation-1",
        causation_id="cause-1",
        now=NOW,
    )

    assert event["contract"] == EVENT_CONTRACT
    assert event["sequence"] == 1
    assert event["event_type"] == "mission"
    assert event["topic"] == "mission.created"
    assert event["source"] == "test-suite"
    assert event["payload"]["mission_id"] == "mission-1"
    assert event["correlation_id"] == "correlation-1"
    assert event["causation_id"] == "cause-1"
    assert validate_event(event) == []

    assert updated["bus_status"] == "running"
    assert updated["published_count"] == 1
    assert updated["duplicate_publish_count"] == 0
    assert updated["next_sequence"] == 2
    assert updated["event_order"] == [event["event_id"]]
    assert updated["events"][event["event_id"]] == event
    assert validate_event_bus_state(updated) == []


def test_publish_increments_sequence(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)

    state, first = publish(
        state,
        event_type="mission",
        topic="mission.created",
        source="test-suite",
        payload={"mission_id": "mission-1"},
        now=NOW,
    )
    state, second = publish(
        state,
        event_type="scheduler",
        topic="scheduler.dispatched",
        source="test-suite",
        payload={"mission_id": "mission-1"},
        now=NOW,
    )

    assert first["sequence"] == 1
    assert second["sequence"] == 2
    assert first["event_id"] != second["event_id"]
    assert state["published_count"] == 2
    assert state["next_sequence"] == 3
    assert len(state["event_order"]) == 2


def test_publish_is_idempotent_with_key(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)

    first_state, first = publish(
        state,
        event_type="worker",
        topic="worker.completed",
        source="worker-1",
        payload={
            "session_id": "session-1",
            "status": "completed",
        },
        idempotency_key="worker-session-1-completed",
        now=NOW,
    )
    second_state, second = publish(
        first_state,
        event_type="worker",
        topic="worker.completed",
        source="worker-1",
        payload={
            "session_id": "session-1",
            "status": "completed",
        },
        idempotency_key="worker-session-1-completed",
        now=NOW,
    )

    assert second == first
    assert second_state["published_count"] == 1
    assert second_state["duplicate_publish_count"] == 1
    assert second_state["next_sequence"] == 2
    assert len(second_state["event_order"]) == 1


@pytest.mark.parametrize(
    "event_type",
    [
        "audit",
        "daemon",
        "memory",
        "mission",
        "scheduler",
        "worker",
    ],
)
def test_all_supported_event_types_can_publish(
    tmp_path: Path,
    event_type: str,
) -> None:
    _, state = _create_state(tmp_path)

    updated, event = publish(
        state,
        event_type=event_type,
        topic=f"{event_type}.test",
        source="test-suite",
        payload={"ok": True},
        now=NOW,
    )

    assert event["event_type"] == event_type
    assert updated["published_count"] == 1


def test_invalid_event_type_is_blocked(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)

    with pytest.raises(
        ValueError,
        match="invalid_event_type",
    ):
        publish(
            state,
            event_type="unknown",
            topic="unknown.test",
            source="test-suite",
            payload={"ok": True},
            now=NOW,
        )


def test_subscribe_is_idempotent(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)

    first = subscribe(
        state,
        topic="mission.created",
        subscriber="mission-audit",
        now=NOW,
    )
    second = subscribe(
        first,
        topic="mission.created",
        subscriber="mission-audit",
        now=NOW,
    )

    assert second == first
    assert len(second["subscriptions"]) == 1
    subscription = next(
        iter(second["subscriptions"].values())
    )
    assert subscription["topic"] == "mission.created"
    assert subscription["subscriber"] == "mission-audit"
    assert subscription["active"] is True


def test_unsubscribe_removes_subscription(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)
    state = subscribe(
        state,
        topic="mission.created",
        subscriber="mission-audit",
        now=NOW,
    )
    subscription_id = next(
        iter(state["subscriptions"])
    )

    result = unsubscribe(
        state,
        subscription_id=subscription_id,
        now=NOW,
    )

    assert result["subscriptions"] == {}
    assert validate_event_bus_state(result) == []


def test_unsubscribe_unknown_is_idempotent(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)

    result = unsubscribe(
        state,
        subscription_id="missing-subscription",
        now=NOW,
    )

    assert result == state


def test_replay_returns_ordered_events(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)

    state, first = publish(
        state,
        event_type="mission",
        topic="mission.created",
        source="test-suite",
        payload={"mission_id": "mission-1"},
        now=NOW,
    )
    state, second = publish(
        state,
        event_type="worker",
        topic="worker.started",
        source="test-suite",
        payload={"worker_id": "worker-1"},
        now=NOW,
    )
    state, third = publish(
        state,
        event_type="mission",
        topic="mission.completed",
        source="test-suite",
        payload={"mission_id": "mission-1"},
        now=NOW,
    )

    result = replay(state)

    assert [item["event_id"] for item in result] == [
        first["event_id"],
        second["event_id"],
        third["event_id"],
    ]


def test_replay_filters_topic_event_type_and_sequence(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)

    state, _ = publish(
        state,
        event_type="mission",
        topic="mission.created",
        source="test-suite",
        payload={"mission_id": "mission-1"},
        now=NOW,
    )
    state, second = publish(
        state,
        event_type="mission",
        topic="mission.completed",
        source="test-suite",
        payload={"mission_id": "mission-1"},
        now=NOW,
    )
    state, third = publish(
        state,
        event_type="worker",
        topic="worker.completed",
        source="test-suite",
        payload={"worker_id": "worker-1"},
        now=NOW,
    )

    topic_result = replay(
        state,
        topic="mission.completed",
    )
    type_result = replay(
        state,
        event_type="worker",
    )
    sequence_result = replay(
        state,
        after_sequence=1,
    )
    limited_result = replay(
        state,
        after_sequence=0,
        limit=1,
    )

    assert [item["event_id"] for item in topic_result] == [
        second["event_id"]
    ]
    assert [item["event_id"] for item in type_result] == [
        third["event_id"]
    ]
    assert [item["event_id"] for item in sequence_result] == [
        second["event_id"],
        third["event_id"],
    ]
    assert len(limited_result) == 1


def test_deliver_calls_matching_handler(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)
    state = subscribe(
        state,
        topic="mission.created",
        subscriber="mission-audit",
        now=NOW,
    )
    state, event = publish(
        state,
        event_type="mission",
        topic="mission.created",
        source="test-suite",
        payload={"mission_id": "mission-1"},
        now=NOW,
    )

    received: list[dict[str, Any]] = []

    def handler(
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        received.append(incoming)
        return {
            "accepted": True,
            "event_id": incoming["event_id"],
        }

    result = deliver(
        state,
        handlers={
            "mission-audit": handler,
        },
    )

    assert len(received) == 1
    assert received[0]["event_id"] == event["event_id"]
    assert result["event_count"] == 1
    assert result["delivery_count"] == 1
    assert result["successful_deliveries"] == 1
    assert result["failed_deliveries"] == 0
    assert result["deliveries"][0]["delivered"] is True
    assert result["state"]["replayed_count"] == 1


def test_deliver_ignores_nonmatching_topic(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)
    state = subscribe(
        state,
        topic="mission.created",
        subscriber="mission-audit",
        now=NOW,
    )
    state, _ = publish(
        state,
        event_type="worker",
        topic="worker.completed",
        source="test-suite",
        payload={"worker_id": "worker-1"},
        now=NOW,
    )

    result = deliver(
        state,
        handlers={
            "mission-audit": lambda event: event,
        },
    )

    assert result["event_count"] == 1
    assert result["delivery_count"] == 0
    assert result["successful_deliveries"] == 0


def test_deliver_reports_missing_handler(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)
    state = subscribe(
        state,
        topic="mission.created",
        subscriber="missing-handler",
        now=NOW,
    )
    state, _ = publish(
        state,
        event_type="mission",
        topic="mission.created",
        source="test-suite",
        payload={"mission_id": "mission-1"},
        now=NOW,
    )

    result = deliver(
        state,
        handlers={},
    )

    assert result["delivery_count"] == 1
    assert result["successful_deliveries"] == 0
    assert result["failed_deliveries"] == 1
    assert result["deliveries"][0]["delivered"] is False
    assert result["deliveries"][0]["reason"] == (
        "handler_not_available"
    )


def test_deliver_isolates_handler_failure(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)
    state = subscribe(
        state,
        topic="mission.created",
        subscriber="failing-handler",
        now=NOW,
    )
    state, _ = publish(
        state,
        event_type="mission",
        topic="mission.created",
        source="test-suite",
        payload={"mission_id": "mission-1"},
        now=NOW,
    )

    def fail(_: dict[str, Any]) -> None:
        raise ValueError("handler_failure")

    result = deliver(
        state,
        handlers={
            "failing-handler": fail,
        },
    )

    assert result["delivery_count"] == 1
    assert result["successful_deliveries"] == 0
    assert result["failed_deliveries"] == 1
    assert result["deliveries"][0]["delivered"] is False
    assert result["deliveries"][0]["reason"] == (
        "ValueError:handler_failure"
    )


def test_persisted_events_survive_reload(
    tmp_path: Path,
) -> None:
    state_path, state = _create_state(tmp_path)
    state, event = publish(
        state,
        event_type="audit",
        topic="audit.recorded",
        source="test-suite",
        payload={"record_id": "audit-1"},
        now=NOW,
    )
    save_event_bus_state(
        state,
        state_path,
    )

    loaded = load_event_bus_state(state_path)
    replayed = replay(loaded)

    assert len(replayed) == 1
    assert replayed[0] == event
    assert loaded["published_count"] == 1


def test_tampered_event_is_rejected(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)
    state, event = publish(
        state,
        event_type="mission",
        topic="mission.created",
        source="test-suite",
        payload={"mission_id": "mission-1"},
        now=NOW,
    )

    tampered = dict(event)
    tampered["payload"] = {
        "mission_id": "mission-tampered"
    }

    reasons = validate_event(tampered)

    assert "event_fingerprint_mismatch" in reasons


def test_tampered_bus_state_is_rejected(
    tmp_path: Path,
) -> None:
    _, state = _create_state(tmp_path)
    state["published_count"] = 999

    reasons = validate_event_bus_state(state)

    assert "event_bus_fingerprint_mismatch" in reasons
