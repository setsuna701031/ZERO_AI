from __future__ import annotations

from datetime import datetime, timezone

import pytest

import core.runtime.runtime_event_bus as module
from core.runtime.runtime_event_bus import RuntimeBusEvent, RuntimeEventBus, RuntimeEventBusError

NOW = datetime(2026, 7, 12, tzinfo=timezone.utc)


def test_exported_compatibility_api():
    assert {"RuntimeEventBus", "RuntimeBusEvent", "RuntimeEventBusError"} <= set(module.__all__)


def test_default_constructor_and_in_memory_publish():
    bus = RuntimeEventBus(now_provider=lambda: NOW)
    payload = {"value": 1}
    event = bus.publish("runtime.test", "created", payload=payload)
    assert isinstance(event, RuntimeBusEvent)
    assert event.payload is payload and event.sequence == 1


def test_path_constructor_creates_and_autosaves(tmp_path):
    path = tmp_path / "bus.json"
    RuntimeEventBus(path, now_provider=lambda: NOW).publish("runtime.test", "created")
    assert path.exists()
    assert RuntimeEventBus(state_path=path).get_events()[0].event_type == "created"


def test_existing_state_constructor():
    state = module.create_event_bus_state(state_path="bus.json", now=NOW)
    assert RuntimeEventBus(state=state).state["contract"] == module.CONTRACT


def test_duplicate_idempotency_returns_same_event(tmp_path):
    bus = RuntimeEventBus(tmp_path / "bus.json", now_provider=lambda: NOW)
    first = bus.publish("runtime.test", "created", idempotency_key="one")
    second = bus.publish("runtime.test", "changed", idempotency_key="one")
    assert second is first
    assert len(bus.get_events()) == 1


def test_replay_filter_and_handler():
    bus = RuntimeEventBus(now_provider=lambda: NOW)
    bus.publish("a", "one"); bus.publish("b", "two"); received = []
    events = bus.replay("a", received.append)
    assert received == events and [item.sequence for item in events] == [1]


def test_subscription_delivery_and_unsubscribe():
    bus = RuntimeEventBus(now_provider=lambda: NOW); received = []
    subscription = bus.subscribe("a", received.append)
    event = bus.publish("a", "one")
    bus.unsubscribe(subscription); bus.publish("a", "two")
    assert received == [event] and subscription.active is False


def test_function_delivery_bridge():
    bus = RuntimeEventBus(now_provider=lambda: NOW)
    subscription = bus.subscribe("a", lambda event: None)
    bus.publish("a", "one")
    result = bus.deliver({subscription.subscription_id: lambda event: event["event_id"]})
    assert result["successful_deliveries"] == 1


def test_auto_save_can_be_disabled(tmp_path):
    path = tmp_path / "bus.json"
    RuntimeEventBus(path, auto_save=False, now_provider=lambda: NOW).publish("a", "one")
    assert not path.exists()


def test_invalid_state_rejected():
    with pytest.raises(RuntimeEventBusError):
        RuntimeEventBus(state={"contract": "wrong"})


def test_handler_failure_preserves_event_and_exception():
    failure = ValueError("boom"); bus = RuntimeEventBus(now_provider=lambda: NOW)
    def fail(event): raise failure
    bus.subscribe("a", fail)
    with pytest.raises(RuntimeEventBusError) as captured:
        bus.publish("a", "one")
    assert captured.value.event is not None and captured.value.original_exception is failure


def test_function_api_remains_available():
    for name in ("create_event_bus_state", "load_event_bus_state", "save_event_bus_state",
                 "publish", "replay", "deliver", "subscribe", "unsubscribe"):
        assert callable(getattr(module, name))
