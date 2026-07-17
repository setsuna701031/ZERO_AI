from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
from typing import Any, Callable, Mapping

from core.runtime.runtime_operator_session import (
    fingerprint,
    time_text,
)
from core.runtime.runtime_execution_result_fields import normalize_runtime_execution_fields

CONTRACT = "zero.runtime.event_bus.v1"
EVENT_CONTRACT = "zero.runtime.event.v1"

VALID_EVENT_TYPES = {
    "audit",
    "daemon",
    "memory",
    "mission",
    "scheduler",
    "worker",
}

VALID_BUS_STATUSES = {
    "created",
    "running",
    "paused",
    "stopped",
    "blocked",
    "failed",
}


def _mapping(value: Any) -> dict[str, Any]:
    return (
        deepcopy(dict(value))
        if isinstance(value, Mapping)
        else {}
    )


def _unsafe(path: Path) -> bool:
    try:
        attributes = getattr(
            path.lstat(),
            "st_file_attributes",
            0,
        )
        reparse = getattr(
            stat,
            "FILE_ATTRIBUTE_REPARSE_POINT",
            0x400,
        )
        return path.is_symlink() or bool(
            attributes & reparse
        )
    except OSError:
        return False


def _atomic_write_json(
    value: Mapping[str, Any],
    destination: Path,
) -> None:
    if destination.exists() and _unsafe(destination):
        raise ValueError("unsafe_event_bus_state_path")

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    if _unsafe(destination.parent):
        raise ValueError(
            "unsafe_event_bus_state_directory"
        )

    temporary = destination.with_name(
        f".{destination.name}.tmp"
    )
    with temporary.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())

    os.replace(temporary, destination)


def _unsigned_event(
    event: Mapping[str, Any],
) -> dict[str, Any]:
    value = _mapping(event)
    value.pop("event_fingerprint", None)
    return value


def seal_event(
    event: Mapping[str, Any],
) -> dict[str, Any]:
    value = _unsigned_event(event)
    value["event_fingerprint"] = fingerprint(value)
    return value


def validate_event(
    event: Mapping[str, Any],
) -> list[str]:
    value = _mapping(event)
    reasons: list[str] = []

    if value.get("contract") != EVENT_CONTRACT:
        reasons.append("invalid_event_contract")

    if value.get("event_fingerprint") != fingerprint(
        _unsigned_event(value)
    ):
        reasons.append("event_fingerprint_mismatch")

    for field in (
        "event_id",
        "event_type",
        "topic",
        "source",
        "created_at",
    ):
        if not str(value.get(field) or "").strip():
            reasons.append(f"{field}_required")

    if value.get("event_type") not in VALID_EVENT_TYPES:
        reasons.append("invalid_event_type")

    sequence = value.get("sequence")
    if (
        isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or sequence < 1
    ):
        reasons.append("invalid_event_sequence")

    if not isinstance(value.get("payload"), Mapping):
        reasons.append("event_payload_required")

    return reasons


def _unsigned_bus(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    value = _mapping(state)
    value.pop("bus_fingerprint", None)
    return value


def seal_event_bus_state(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    value = _unsigned_bus(state)
    value["bus_fingerprint"] = fingerprint(value)
    return value


def validate_event_bus_state(
    state: Mapping[str, Any],
) -> list[str]:
    value = _mapping(state)
    reasons: list[str] = []

    if value.get("contract") != CONTRACT:
        reasons.append("invalid_event_bus_contract")

    if value.get("bus_fingerprint") != fingerprint(
        _unsigned_bus(value)
    ):
        reasons.append("event_bus_fingerprint_mismatch")

    if not str(value.get("bus_id") or "").strip():
        reasons.append("event_bus_id_required")
    if not str(value.get("bus_name") or "").strip():
        reasons.append("event_bus_name_required")

    if value.get("bus_status") not in VALID_BUS_STATUSES:
        reasons.append("invalid_event_bus_status")

    events = value.get("events")
    order = value.get("event_order")
    subscriptions = value.get("subscriptions")

    if not isinstance(events, Mapping):
        reasons.append("event_bus_events_required")
        events = {}
    if not isinstance(order, list):
        reasons.append("event_bus_event_order_required")
        order = []
    if not isinstance(subscriptions, Mapping):
        reasons.append("event_bus_subscriptions_required")
        subscriptions = {}

    if set(order) != set(events):
        reasons.append("event_bus_event_order_mismatch")

    expected_next_sequence = len(order) + 1
    if value.get("next_sequence") != expected_next_sequence:
        reasons.append("event_bus_next_sequence_mismatch")

    for event_id in order:
        event = _mapping(events.get(event_id))
        if event.get("event_id") != event_id:
            reasons.append(
                f"event_identity_mismatch:{event_id}"
            )
            continue
        for reason in validate_event(event):
            reasons.append(f"{event_id}:{reason}")

    for subscription_id, subscription in subscriptions.items():
        item = _mapping(subscription)
        if item.get("subscription_id") != subscription_id:
            reasons.append(
                f"subscription_identity_mismatch:{subscription_id}"
            )
        if not str(item.get("topic") or "").strip():
            reasons.append(
                f"{subscription_id}:subscription_topic_required"
            )
        if not str(item.get("subscriber") or "").strip():
            reasons.append(
                f"{subscription_id}:subscriber_required"
            )

    return reasons


def create_event_bus_state(
    *,
    state_path: Any,
    bus_name: str = "default",
    now: Any = None,
) -> dict[str, Any]:
    name = str(bus_name or "").strip()
    if not name:
        raise ValueError("event_bus_name_required")

    destination = Path(state_path)
    identity = {
        "bus_name": name,
        "state_path": str(
            destination.resolve(strict=False)
        ).replace("\\", "/").casefold(),
    }
    at = time_text(now)

    return seal_event_bus_state(
        {
            "contract": CONTRACT,
            "bus_id": (
                "runtime-event-bus-"
                f"{fingerprint(identity)[:20]}"
            ),
            "bus_name": name,
            "bus_status": "created",
            "state_path": str(
                destination.resolve(strict=False)
            ),
            "events": {},
            "event_order": [],
            "next_sequence": 1,
            "subscriptions": {},
            "published_count": 0,
            "duplicate_publish_count": 0,
            "replayed_count": 0,
            "created_at": at,
            "updated_at": at,
            "last_event_at": None,
            "failure": None,
        }
    )


def save_event_bus_state(
    state: Mapping[str, Any],
    path: Any,
) -> dict[str, Any]:
    destination = Path(path)
    value = seal_event_bus_state(state)
    reasons = validate_event_bus_state(value)
    if reasons:
        raise ValueError(";".join(reasons))
    _atomic_write_json(value, destination)
    return value


def load_event_bus_state(
    path: Any,
) -> dict[str, Any]:
    source = Path(path)
    if _unsafe(source):
        raise ValueError("unsafe_event_bus_state_path")

    try:
        value = json.loads(
            source.read_text(
                encoding="utf-8-sig"
            )
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError(
            "invalid_event_bus_json"
        ) from exc

    reasons = validate_event_bus_state(value)
    if reasons:
        raise ValueError(";".join(reasons))
    return value


def subscribe(
    state: Mapping[str, Any],
    *,
    topic: str,
    subscriber: str,
    now: Any = None,
) -> dict[str, Any]:
    value = _mapping(state)
    topic_text = str(topic or "").strip()
    subscriber_text = str(subscriber or "").strip()

    if not topic_text:
        raise ValueError("subscription_topic_required")
    if not subscriber_text:
        raise ValueError("subscriber_required")

    identity = {
        "bus_id": value.get("bus_id"),
        "topic": topic_text,
        "subscriber": subscriber_text,
    }
    subscription_id = (
        "event-subscription-"
        f"{fingerprint(identity)[:20]}"
    )

    subscriptions = _mapping(
        value.get("subscriptions")
    )
    if subscription_id in subscriptions:
        return value

    subscriptions[subscription_id] = {
        "subscription_id": subscription_id,
        "topic": topic_text,
        "subscriber": subscriber_text,
        "created_at": time_text(now),
        "active": True,
    }
    value["subscriptions"] = subscriptions
    value["updated_at"] = time_text(now)
    return seal_event_bus_state(value)


def unsubscribe(
    state: Mapping[str, Any],
    *,
    subscription_id: str,
    now: Any = None,
) -> dict[str, Any]:
    value = _mapping(state)
    subscriptions = _mapping(
        value.get("subscriptions")
    )

    if subscription_id not in subscriptions:
        return value

    subscriptions.pop(subscription_id, None)
    value["subscriptions"] = subscriptions
    value["updated_at"] = time_text(now)
    return seal_event_bus_state(value)


def publish(
    state: Mapping[str, Any],
    *,
    event_type: str,
    topic: str,
    source: str,
    payload: Mapping[str, Any],
    idempotency_key: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    now: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    value = _mapping(state)
    event_type_text = str(event_type or "").strip()
    topic_text = str(topic or "").strip()
    source_text = str(source or "").strip()

    if event_type_text not in VALID_EVENT_TYPES:
        raise ValueError("invalid_event_type")
    if not topic_text:
        raise ValueError("event_topic_required")
    if not source_text:
        raise ValueError("event_source_required")
    if not isinstance(payload, Mapping):
        raise ValueError("event_payload_required")

    events = _mapping(value.get("events"))
    order = list(value.get("event_order") or [])

    key = str(idempotency_key or "").strip()
    if key:
        for event_id in order:
            existing = _mapping(events.get(event_id))
            if existing.get("idempotency_key") == key:
                value["duplicate_publish_count"] = int(
                    value.get(
                        "duplicate_publish_count"
                    )
                    or 0
                ) + 1
                value["updated_at"] = time_text(now)
                return (
                    seal_event_bus_state(value),
                    existing,
                )

    sequence = int(value.get("next_sequence") or 1)
    created_at = time_text(now)
    identity = {
        "bus_id": value.get("bus_id"),
        "sequence": sequence,
        "event_type": event_type_text,
        "topic": topic_text,
        "source": source_text,
        "idempotency_key": key or None,
        "created_at": created_at,
        "payload": _mapping(payload),
    }
    event_id = (
        "runtime-event-"
        f"{fingerprint(identity)[:24]}"
    )

    event = seal_event(
        {
            "contract": EVENT_CONTRACT,
            "event_id": event_id,
            "sequence": sequence,
            "event_type": event_type_text,
            "topic": topic_text,
            "source": source_text,
            "payload": _mapping(payload),
            "idempotency_key": key or None,
            "correlation_id": (
                str(correlation_id or "").strip()
                or None
            ),
            "causation_id": (
                str(causation_id or "").strip()
                or None
            ),
            "created_at": created_at,
        }
    )

    events[event_id] = event
    order.append(event_id)

    value["events"] = events
    value["event_order"] = order
    value["next_sequence"] = sequence + 1
    value["published_count"] = int(
        value.get("published_count") or 0
    ) + 1
    value["last_event_at"] = created_at
    value["updated_at"] = created_at
    value["bus_status"] = "running"
    return seal_event_bus_state(value), event


def replay(
    state: Mapping[str, Any],
    *,
    topic: str | None = None,
    event_type: str | None = None,
    after_sequence: int = 0,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    value = _mapping(state)

    if (
        isinstance(after_sequence, bool)
        or not isinstance(after_sequence, int)
        or after_sequence < 0
    ):
        raise ValueError("invalid_after_sequence")

    if (
        limit is not None
        and (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < 1
        )
    ):
        raise ValueError("invalid_replay_limit")

    topic_text = str(topic or "").strip()
    event_type_text = str(event_type or "").strip()
    events = _mapping(value.get("events"))

    result: list[dict[str, Any]] = []
    for event_id in value.get("event_order", []):
        event = _mapping(events.get(event_id))
        if int(event.get("sequence") or 0) <= after_sequence:
            continue
        if topic_text and event.get("topic") != topic_text:
            continue
        if (
            event_type_text
            and event.get("event_type")
            != event_type_text
        ):
            continue

        result.append(event)
        if limit is not None and len(result) >= limit:
            break

    return result


def deliver(
    state: Mapping[str, Any],
    *,
    handlers: Mapping[
        str,
        Callable[[Mapping[str, Any]], Any],
    ],
    after_sequence: int = 0,
    limit: int | None = None,
) -> dict[str, Any]:
    value = _mapping(state)
    deliveries: list[dict[str, Any]] = []
    subscriptions = _mapping(
        value.get("subscriptions")
    )
    events = replay(
        value,
        after_sequence=after_sequence,
        limit=limit,
    )

    for event in events:
        topic = str(event.get("topic") or "")
        for subscription in subscriptions.values():
            item = _mapping(subscription)
            if item.get("active") is not True:
                continue
            if item.get("topic") != topic:
                continue

            subscriber = str(
                item.get("subscriber") or ""
            )
            handler = handlers.get(subscriber)
            if not callable(handler):
                deliveries.append(
                    {
                        "event_id": event.get("event_id"),
                        "subscription_id": item.get(
                            "subscription_id"
                        ),
                        "subscriber": subscriber,
                        "delivered": False,
                        "reason": "handler_not_available",
                    }
                )
                continue

            try:
                result = handler(deepcopy(event))
                deliveries.append(
                    {
                        "event_id": event.get("event_id"),
                        "subscription_id": item.get(
                            "subscription_id"
                        ),
                        "subscriber": subscriber,
                        "delivered": True,
                        "result": deepcopy(result),
                    }
                )
            except Exception as exc:
                deliveries.append(
                    {
                        "event_id": event.get("event_id"),
                        "subscription_id": item.get(
                            "subscription_id"
                        ),
                        "subscriber": subscriber,
                        "delivered": False,
                        "reason": (
                            f"{type(exc).__name__}:{exc}"
                        ),
                    }
                )

    value["replayed_count"] = int(
        value.get("replayed_count") or 0
    ) + len(events)
    value["updated_at"] = time_text(
        datetime.now(timezone.utc)
    )
    value = seal_event_bus_state(value)

    return {
        "contract": CONTRACT,
        "bus_id": value.get("bus_id"),
        "event_count": len(events),
        "delivery_count": len(deliveries),
        "successful_deliveries": sum(
            item.get("delivered") is True
            for item in deliveries
        ),
        "failed_deliveries": sum(
            item.get("delivered") is not True
            for item in deliveries
        ),
        "deliveries": deliveries,
        "state": value,
    }


@dataclass(frozen=True)
class RuntimeBusEvent:
    channel: str
    event_type: str
    payload: Any
    metadata: Any
    sequence: int
    event_id: str
    timestamp: str


@dataclass
class RuntimeBusSubscription:
    channel: str
    handler: Callable[[RuntimeBusEvent], Any]
    subscription_id: str
    active: bool = True


class RuntimeEventBusError(RuntimeError):
    def __init__(self, message: str, *, event: RuntimeBusEvent | None = None,
                 original_exception: BaseException | None = None) -> None:
        self.event = event
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeEventBus:
    """Object compatibility bridge over the durable function-based event bus.

    The JSON state remains the authoritative representation. Object events and
    callback subscriptions are projections retained for legacy runtime callers.
    """

    def __init__(self, state: Mapping[str, Any] | Any | None = None,
                 state_path: Any | None = None, bus_name: str = "default",
                 auto_load: bool = True, auto_save: bool = True,
                 now_provider: Callable[[], Any] | None = None) -> None:
        if state is not None and not isinstance(state, Mapping):
            if state_path is not None:
                raise RuntimeEventBusError("event_bus_state_and_path_conflict")
            state_path, state = state, None
        self.state_path = Path(state_path) if state_path is not None else None
        self.auto_save = bool(auto_save)
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._subscriptions: list[RuntimeBusSubscription] = []
        self._event_cache: dict[str, RuntimeBusEvent] = {}
        if state is not None:
            candidate = seal_event_bus_state(state)
            reasons = validate_event_bus_state(candidate)
            if reasons:
                raise RuntimeEventBusError(";".join(reasons))
            self.state = candidate
        elif self.state_path is not None and auto_load and self.state_path.exists():
            self.state = self._load_state()
        else:
            self.state = create_event_bus_state(state_path=self.state_path or Path("runtime-event-bus.json"),
                                                bus_name=bus_name, now=self.now_provider())

    def _load_state(self) -> dict[str, Any]:
        try:
            return load_event_bus_state(self.state_path)
        except Exception as exc:
            raise RuntimeEventBusError("event_bus_load_failed", original_exception=exc) from exc

    def _maybe_save(self) -> None:
        if self.auto_save and self.state_path is not None:
            self.save()

    @staticmethod
    def _safe(value: Any) -> Any:
        from core.runtime.runtime_safe_schema import to_runtime_safe_schema
        return to_runtime_safe_schema(deepcopy(value))

    def _project(self, raw: Mapping[str, Any]) -> RuntimeBusEvent:
        event_id = str(raw.get("event_id") or "")
        if event_id in self._event_cache:
            return self._event_cache[event_id]
        body = _mapping(raw.get("payload"))
        event = RuntimeBusEvent(
            channel=str(raw.get("topic") or ""),
            event_type=str(body.get("compatibility_event_type") or raw.get("event_type") or ""),
            payload=deepcopy(body.get("compatibility_payload")),
            metadata=deepcopy(body.get("compatibility_metadata")),
            sequence=int(raw.get("sequence") or 0), event_id=event_id,
            timestamp=str(raw.get("created_at") or ""),
        )
        self._event_cache[event_id] = event
        return event

    def load(self) -> dict[str, Any]:
        if self.state_path is None:
            raise RuntimeEventBusError("event_bus_state_path_required")
        self.state = self._load_state()
        self._event_cache.clear()
        return self.state

    def save(self) -> dict[str, Any]:
        if self.state_path is None:
            raise RuntimeEventBusError("event_bus_state_path_required")
        try:
            self.state = save_event_bus_state(self.state, self.state_path)
            return self.state
        except Exception as exc:
            raise RuntimeEventBusError("event_bus_save_failed", original_exception=exc) from exc

    def publish(self, channel: str, event_type: str, payload: Any = None,
                metadata: Any = None, *, idempotency_key: str | None = None,
                source: str = "runtime.compatibility", correlation_id: str | None = None,
                causation_id: str | None = None) -> RuntimeBusEvent:
        channel_text = str(channel or "").strip()
        type_text = str(event_type or "").strip()
        if not channel_text or not type_text:
            raise RuntimeEventBusError("event_bus_channel_and_event_type_required")
        projected_payload = payload
        if isinstance(payload, Mapping) and type_text == "execution_result_recorded":
            from core.runtime.runtime_status import canonical_runtime_status_payload
            projected_payload = normalize_runtime_execution_fields(payload, metadata)
            nested = projected_payload.get("runtime_execution_result")
            if isinstance(nested, Mapping):
                projected_payload["runtime_execution_result"] = canonical_runtime_status_payload(
                    normalize_runtime_execution_fields(nested, metadata))
            projected_payload = canonical_runtime_status_payload(projected_payload)
        envelope = {"compatibility_event_type": type_text,
                    "compatibility_payload": self._safe(projected_payload),
                    "compatibility_metadata": self._safe(metadata)}
        try:
            cached_before = set(self._event_cache)
            self.state, raw = publish(self.state, event_type="audit", topic=channel_text,
                                      source=source, payload=envelope,
                                      idempotency_key=idempotency_key,
                                      correlation_id=correlation_id, causation_id=causation_id,
                                      now=self.now_provider())
            event = self._project(raw)
            # Preserve caller identity for newly-created legacy events.
            if event.event_id not in cached_before:
                event = RuntimeBusEvent(channel_text, type_text, projected_payload, metadata,
                                        int(raw["sequence"]), str(raw["event_id"]), str(raw["created_at"]))
                self._event_cache[event.event_id] = event
            self._maybe_save()
            for subscription in list(self._subscriptions):
                if subscription.active and subscription.channel == channel_text:
                    try:
                        subscription.handler(event)
                    except Exception as exc:
                        raise RuntimeEventBusError("runtime_event_handler_failed", event=event,
                                                   original_exception=exc) from exc
            return event
        except RuntimeEventBusError:
            raise
        except Exception as exc:
            raise RuntimeEventBusError("runtime_event_publish_failed", original_exception=exc) from exc

    def publish_event(self, event: Any, *, channel: str = "runtime.kernel",
                      metadata: Any = None, idempotency_key: str | None = None) -> RuntimeBusEvent:
        return self.publish(channel, type(event).__name__, payload=event,
                            metadata=metadata if metadata is not None else getattr(event, "metadata", None),
                            idempotency_key=idempotency_key)

    def subscribe(self, channel: str, handler: Callable[[RuntimeBusEvent], Any]) -> RuntimeBusSubscription:
        if not str(channel or "").strip() or not callable(handler):
            raise RuntimeEventBusError("invalid_runtime_event_subscription")
        subscription = RuntimeBusSubscription(str(channel).strip(), handler,
            f"compat-subscription-{len(self._subscriptions) + 1}")
        self._subscriptions.append(subscription)
        self.state = subscribe(self.state, topic=subscription.channel,
                               subscriber=subscription.subscription_id, now=self.now_provider())
        match = next((str(key) for key, value in _mapping(self.state.get("subscriptions")).items()
                      if _mapping(value).get("subscriber") == subscription.subscription_id), None)
        if match:
            subscription.subscription_id = match
        self._maybe_save()
        return subscription

    def unsubscribe(self, subscription: RuntimeBusSubscription | str) -> RuntimeBusSubscription | None:
        item = subscription if isinstance(subscription, RuntimeBusSubscription) else next(
            (entry for entry in self._subscriptions if entry.subscription_id == subscription), None)
        if item is None:
            return None
        item.active = False
        self.state = unsubscribe(self.state, subscription_id=item.subscription_id, now=self.now_provider())
        self._maybe_save()
        return item

    def get_events(self, channel: str | None = None) -> list[RuntimeBusEvent]:
        return [self._project(event) for event in replay(self.state, topic=channel)]

    def replay(self, channel: str | None = None,
               handler: Callable[[RuntimeBusEvent], Any] | None = None, *,
               after_sequence: int = 0, limit: int | None = None) -> list[RuntimeBusEvent]:
        events = [self._project(event) for event in replay(
            self.state, topic=channel, after_sequence=after_sequence, limit=limit)]
        if handler is not None:
            for event in events:
                try:
                    handler(event)
                except Exception as exc:
                    raise RuntimeEventBusError("runtime_event_replay_handler_failed", event=event,
                                               original_exception=exc) from exc
        return events

    def deliver(self, handlers: Mapping[str, Callable[[Mapping[str, Any]], Any]], *,
                after_sequence: int = 0, limit: int | None = None) -> dict[str, Any]:
        resolved = dict(handlers)
        for subscription_id, item in _mapping(self.state.get("subscriptions")).items():
            subscriber = str(_mapping(item).get("subscriber") or "")
            if subscription_id in handlers and subscriber not in resolved:
                resolved[subscriber] = handlers[subscription_id]
        result = deliver(self.state, handlers=resolved, after_sequence=after_sequence, limit=limit)
        self.state = result["state"]
        self._maybe_save()
        return result

    def clear(self) -> None:
        bus_name = str(self.state.get("bus_name") or "default")
        path = self.state_path or self.state.get("state_path") or Path("runtime-event-bus.json")
        self.state = create_event_bus_state(state_path=path, bus_name=bus_name, now=self.now_provider())
        self._event_cache.clear()
        self._subscriptions.clear()
        self._maybe_save()


__all__ = [
    "CONTRACT",
    "EVENT_CONTRACT",
    "VALID_BUS_STATUSES",
    "VALID_EVENT_TYPES",
    "RuntimeBusEvent",
    "RuntimeBusSubscription",
    "RuntimeEventBus",
    "RuntimeEventBusError",
    "create_event_bus_state",
    "deliver",
    "load_event_bus_state",
    "publish",
    "replay",
    "save_event_bus_state",
    "seal_event",
    "seal_event_bus_state",
    "subscribe",
    "unsubscribe",
    "validate_event",
    "validate_event_bus_state",
]
