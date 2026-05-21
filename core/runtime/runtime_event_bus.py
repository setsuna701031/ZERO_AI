from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from core.runtime.runtime_events import RUNTIME_EVENT_CHANNEL, RuntimeEvent
from core.runtime.runtime_execution_result_fields import normalize_runtime_execution_fields
from core.runtime.runtime_status import (
    canonical_runtime_status_payload,
    status_from_execution_result,
)


EventHandler = Callable[["RuntimeBusEvent"], None]


@dataclass(frozen=True)
class RuntimeBusEvent:
    channel: str
    event_type: str
    payload: Any
    metadata: Any
    sequence: int
    timestamp: str


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

        payload = _normalize_execution_payload(event_type, payload, metadata)
        self._sequence += 1
        event = RuntimeBusEvent(
            channel=channel,
            event_type=event_type,
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
            timestamp=self._now_iso(),
        )
        self._events.append(event)

        for subscription in list(self._subscriptions):
            if not subscription.active or subscription.channel != channel:
                continue

            self._call_handler(subscription.handler, event)

        return event

    def publish_event(
        self,
        event: RuntimeEvent,
        *,
        channel: str = RUNTIME_EVENT_CHANNEL,
        metadata: Any = None,
    ) -> RuntimeBusEvent:
        self._validate_channel(channel)

        self._sequence += 1
        sequenced = event.with_sequence(self._sequence)
        normalized_payload = _normalize_execution_payload(
            sequenced.event_type,
            sequenced.payload,
            metadata if metadata is not None else sequenced.metadata,
        )
        if normalized_payload is not sequenced.payload:
            sequenced = RuntimeEvent(
                event_type=sequenced.event_type,
                payload=normalized_payload,
                metadata=sequenced.metadata,
                sequence=sequenced.sequence,
                timestamp=sequenced.timestamp,
            )
        bus_event = RuntimeBusEvent(
            channel=channel,
            event_type=sequenced.event_type,
            payload=sequenced,
            metadata=metadata if metadata is not None else sequenced.metadata,
            sequence=self._sequence,
            timestamp=sequenced.timestamp,
        )
        self._events.append(bus_event)

        for subscription in list(self._subscriptions):
            if not subscription.active or subscription.channel != channel:
                continue

            self._call_handler(subscription.handler, bus_event)

        return bus_event

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

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()


def _looks_like_execution_payload(event_type: str, payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False

    if "execution" in str(event_type or "").lower():
        return True

    return any(
        key in payload
        for key in (
            "ok",
            "executed",
            "blocked",
            "failed",
            "verification",
            "verification_passed",
            "changed_files",
            "impacted_files",
            "runtime_execution_result",
            "execution_result",
            "status",
            "phase",
            "result",
        )
    )


def _normalize_execution_payload(event_type: str, payload: Any, metadata: Any) -> Any:
    if not _looks_like_execution_payload(event_type, payload):
        return payload

    if not isinstance(payload, dict):
        return payload

    if isinstance(payload.get("runtime_execution_result"), dict):
        normalized = canonical_runtime_status_payload(
            payload,
            status=status_from_execution_result(payload.get("runtime_execution_result")),
        )
    elif any(
        key in payload
        for key in (
            "ok",
            "executed",
            "blocked",
            "failed",
            "verification",
            "verification_passed",
            "changed_files",
            "impacted_files",
        )
    ):
        normalized = normalize_runtime_execution_fields(payload, metadata=metadata)
    else:
        normalized = canonical_runtime_status_payload(payload)

    for key in (
        "runtime_execution_result",
        "execution_result",
    ):
        if isinstance(payload.get(key), dict):
            normalized[key] = normalize_runtime_execution_fields(
                payload.get(key),
                metadata=payload.get(key, {}).get("metadata"),
                evidence=payload.get(key, {}).get("evidence"),
            )

    return canonical_runtime_status_payload(normalized)
