from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


EventHandler = Callable[["RuntimeBusEvent"], None]


@dataclass(frozen=True)
class RuntimeBusEvent:
    channel: str
    event_type: str
    payload: Any
    metadata: Any
    sequence: int


@dataclass
class RuntimeBusSubscription:
    channel: str
    handler: EventHandler
    active: bool = True


class RuntimeEventBusError(RuntimeError):
    def __init__(
        self,
        message: str,
        event: RuntimeBusEvent | None = None,
        original_exception: BaseException | None = None,
    ) -> None:
        self.event = event
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeEventBus:
    def __init__(self) -> None:
        self._events: list[RuntimeBusEvent] = []
        self._subscriptions: list[RuntimeBusSubscription] = []
        self._sequence = 0

    def subscribe(
        self,
        channel: str,
        handler: EventHandler,
    ) -> RuntimeBusSubscription:
        self._validate_channel(channel)
        subscription = RuntimeBusSubscription(channel=channel, handler=handler)
        self._subscriptions.append(subscription)
        return subscription

    def unsubscribe(self, subscription: RuntimeBusSubscription) -> None:
        subscription.active = False

    def publish(
        self,
        channel: str,
        event_type: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeBusEvent:
        self._validate_channel(channel)
        self._validate_event_type(event_type)

        self._sequence += 1
        event = RuntimeBusEvent(
            channel=channel,
            event_type=event_type,
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
        )
        self._events.append(event)

        for subscription in list(self._subscriptions):
            if not subscription.active or subscription.channel != channel:
                continue

            self._call_handler(subscription.handler, event)

        return event

    def get_events(self, channel: str | None = None) -> list[RuntimeBusEvent]:
        if channel is None:
            return list(self._events)

        self._validate_channel(channel)
        return [event for event in self._events if event.channel == channel]

    def replay(
        self,
        channel: str | None = None,
        handler: EventHandler | None = None,
    ) -> list[RuntimeBusEvent]:
        events = self.get_events(channel=channel)

        if handler is None:
            return events

        for event in events:
            self._call_handler(handler, event)

        return events

    def clear(self) -> None:
        self._events.clear()
        self._subscriptions.clear()
        self._sequence = 0

    def _call_handler(self, handler: EventHandler, event: RuntimeBusEvent) -> None:
        try:
            handler(event)
        except Exception as exc:
            raise RuntimeEventBusError(
                "runtime event bus handler failed",
                event=event,
                original_exception=exc,
            ) from exc

    def _validate_channel(self, channel: str) -> None:
        if not str(channel or "").strip():
            raise RuntimeEventBusError("runtime event bus channel is required")

    def _validate_event_type(self, event_type: str) -> None:
        if not str(event_type or "").strip():
            raise RuntimeEventBusError("runtime event bus event_type is required")
