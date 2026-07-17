from __future__ import annotations

import copy
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


EVENT_EXECUTION = "execution_event"
EVENT_MUTATION = "mutation_event"
EVENT_RECOVERY = "recovery_event"
EVENT_POLICY = "policy_event"
EVENT_TRANSACTION = "transaction_event"
EVENT_ZONE = "zone_transition_event"

STREAM_ACTIVE = "active"
STREAM_REPLAYED = "replayed"

REBUILD_ALLOWED = "allowed"
REBUILD_BLOCKED = "blocked"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeEvent:
    event_id: str
    event_type: str
    runtime_zone: str
    payload: dict[str, Any]
    sequence: int
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "runtime_zone": self.runtime_zone,
            "payload": copy.deepcopy(self.payload),
            "sequence": self.sequence,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RuntimeEventSourcingDecision:
    rebuild_status: str
    allowed: bool
    reason: str
    reconstructed_state: dict[str, Any]
    event_stream: list[dict[str, Any]]
    created_at: str = field(default_factory=utc_timestamp)
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            object.__setattr__(
                self,
                "fingerprint",
                _stable_fingerprint(self.to_dict(include_fingerprint=False)),
            )

    def to_dict(self, include_fingerprint: bool = True) -> dict[str, Any]:
        payload = {
            "artifact_type": "runtime_event_sourcing_decision",
            "rebuild_status": self.rebuild_status,
            "allowed": self.allowed,
            "reason": self.reason,
            "reconstructed_state": copy.deepcopy(self.reconstructed_state),
            "event_stream": copy.deepcopy(self.event_stream),
            "created_at": self.created_at,
        }

        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
            payload["verified"] = self.verify()

        return payload

    def verify(self) -> bool:
        return self.fingerprint == _stable_fingerprint(
            self.to_dict(include_fingerprint=False)
        )


class RuntimeEventSourcingLayer:
    """
    Event-sourced runtime architecture.

    Runtime history is append-only and reconstructable through event replay.
    """

    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []

    def append_event(
        self,
        *,
        event_type: str,
        runtime_zone: str,
        payload: dict[str, Any] | None = None,
    ) -> RuntimeEvent:
        event = RuntimeEvent(
            event_id="event-" + secrets.token_hex(8),
            event_type=str(event_type),
            runtime_zone=str(runtime_zone),
            payload=copy.deepcopy(payload or {}),
            sequence=len(self.events) + 1,
            created_at=utc_timestamp(),
        )

        self.events.append(event)
        return event

    def replay_event_stream(self) -> RuntimeEventSourcingDecision:
        reconstructed_state: dict[str, Any] = {
            "zones": {},
            "event_count": len(self.events),
            "last_event_type": None,
        }

        for event in self.events:
            reconstructed_state["last_event_type"] = event.event_type

            zone_state = reconstructed_state["zones"].setdefault(
                event.runtime_zone,
                {
                    "events": [],
                },
            )

            zone_state["events"].append(
                {
                    "event_type": event.event_type,
                    "payload": copy.deepcopy(event.payload),
                    "sequence": event.sequence,
                }
            )

        return RuntimeEventSourcingDecision(
            rebuild_status=STREAM_REPLAYED,
            allowed=True,
            reason="event_stream_replayed",
            reconstructed_state=reconstructed_state,
            event_stream=[item.to_dict() for item in self.events],
        )

    def rebuild_runtime_state(
        self,
        *,
        target_zone: str,
    ) -> RuntimeEventSourcingDecision:
        if not self.events:
            return RuntimeEventSourcingDecision(
                rebuild_status=REBUILD_BLOCKED,
                allowed=False,
                reason="event_stream_empty",
                reconstructed_state={},
                event_stream=[],
            )

        state = {
            "target_zone": target_zone,
            "events": [],
        }

        for event in self.events:
            if event.runtime_zone == target_zone:
                state["events"].append(
                    {
                        "event_type": event.event_type,
                        "payload": copy.deepcopy(event.payload),
                        "sequence": event.sequence,
                    }
                )

        return RuntimeEventSourcingDecision(
            rebuild_status=REBUILD_ALLOWED,
            allowed=True,
            reason="runtime_state_rebuilt",
            reconstructed_state=state,
            event_stream=[item.to_dict() for item in self.events],
        )


__all__ = [
    "RuntimeEventSourcingLayer",
    "RuntimeEvent",
    "RuntimeEventSourcingDecision",
    "EVENT_EXECUTION",
    "EVENT_MUTATION",
    "EVENT_RECOVERY",
    "EVENT_POLICY",
    "EVENT_TRANSACTION",
    "EVENT_ZONE",
    "STREAM_ACTIVE",
    "STREAM_REPLAYED",
    "REBUILD_ALLOWED",
    "REBUILD_BLOCKED",
]
