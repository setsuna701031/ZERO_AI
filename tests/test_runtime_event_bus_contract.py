from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEventBusContractTest(unittest.TestCase):
    def test_publish_creates_event(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus

        event = RuntimeEventBus().publish("runtime.event", "status")

        self.assertEqual(event.channel, "runtime.event")
        self.assertEqual(event.event_type, "status")
        self.assertEqual(event.sequence, 1)

    def test_sequence_increments_globally(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus

        bus = RuntimeEventBus()
        first = bus.publish("runtime.event", "status")
        second = bus.publish("runtime.incident", "failure")

        self.assertEqual(first.sequence, 1)
        self.assertEqual(second.sequence, 2)

    def test_subscriber_receives_matching_channel_event(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus

        received = []
        bus = RuntimeEventBus()
        bus.subscribe("runtime.event", received.append)
        event = bus.publish("runtime.event", "status")

        self.assertEqual(received, [event])

    def test_subscriber_does_not_receive_other_channel(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus

        received = []
        bus = RuntimeEventBus()
        bus.subscribe("runtime.event", received.append)
        bus.publish("runtime.incident", "failure")

        self.assertEqual(received, [])

    def test_unsubscribe_disables_subscription(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus

        bus = RuntimeEventBus()
        subscription = bus.subscribe("runtime.event", lambda event: None)
        bus.unsubscribe(subscription)

        self.assertFalse(subscription.active)

    def test_inactive_subscription_not_called(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus

        received = []
        bus = RuntimeEventBus()
        subscription = bus.subscribe("runtime.event", received.append)
        bus.unsubscribe(subscription)
        bus.publish("runtime.event", "status")

        self.assertEqual(received, [])

    def test_get_events_returns_all_events(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus

        bus = RuntimeEventBus()
        bus.publish("runtime.event", "status")
        bus.publish("runtime.incident", "failure")

        self.assertEqual(len(bus.get_events()), 2)

    def test_get_events_filters_channel(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus

        bus = RuntimeEventBus()
        bus.publish("runtime.event", "status")
        bus.publish("runtime.incident", "failure")

        events = bus.get_events("runtime.incident")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].channel, "runtime.incident")

    def test_get_events_returns_copy(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus

        bus = RuntimeEventBus()
        bus.publish("runtime.event", "status")
        events = bus.get_events()
        events.clear()

        self.assertEqual(len(bus.get_events()), 1)

    def test_replay_returns_events_in_sequence_order(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus

        bus = RuntimeEventBus()
        bus.publish("runtime.event", "first")
        bus.publish("runtime.event", "second")

        self.assertEqual(
            [event.sequence for event in bus.replay("runtime.event")],
            [1, 2],
        )

    def test_replay_handler_receives_events_in_sequence_order(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus

        received = []
        bus = RuntimeEventBus()
        bus.publish("runtime.event", "first")
        bus.publish("runtime.event", "second")
        bus.replay("runtime.event", lambda event: received.append(event.sequence))

        self.assertEqual(received, [1, 2])

    def test_handler_exception_raises_runtime_event_bus_error(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus, RuntimeEventBusError

        def fail(_event) -> None:
            raise ValueError("boom")

        bus = RuntimeEventBus()
        bus.subscribe("runtime.event", fail)

        with self.assertRaises(RuntimeEventBusError):
            bus.publish("runtime.event", "status")

    def test_error_keeps_event_and_original_exception(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus, RuntimeEventBusError

        original = ValueError("boom")

        def fail(_event) -> None:
            raise original

        bus = RuntimeEventBus()
        bus.subscribe("runtime.event", fail)

        with self.assertRaises(RuntimeEventBusError) as context:
            bus.publish("runtime.event", "status")

        self.assertIsNotNone(context.exception.event)
        self.assertIs(context.exception.original_exception, original)

    def test_clear_resets_bus_and_sequence(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus

        received = []
        bus = RuntimeEventBus()
        bus.subscribe("runtime.event", received.append)
        bus.publish("runtime.event", "first")
        bus.clear()
        event = bus.publish("runtime.event", "second")

        self.assertEqual(event.sequence, 1)
        self.assertEqual(bus.get_events(), [event])
        self.assertEqual(len(received), 1)

    def test_payload_preserved(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus

        payload = {"task_id": "task-1"}
        event = RuntimeEventBus().publish("runtime.event", "status", payload=payload)

        self.assertIs(event.payload, payload)

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus

        metadata = {"source": "contract"}
        event = RuntimeEventBus().publish(
            "runtime.event",
            "status",
            metadata=metadata,
        )

        self.assertIs(event.metadata, metadata)

    def test_empty_channel_rejected(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus, RuntimeEventBusError

        with self.assertRaises(RuntimeEventBusError):
            RuntimeEventBus().publish("", "status")

    def test_empty_event_type_rejected(self) -> None:
        from core.runtime.runtime_event_bus import RuntimeEventBus, RuntimeEventBusError

        with self.assertRaises(RuntimeEventBusError):
            RuntimeEventBus().publish("runtime.event", "")


if __name__ == "__main__":
    unittest.main()
