from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.runtime.runtime_events import (
    RUNTIME_EVENT_CHANNEL,
    RuntimeEvent,
    RuntimeStateTransitionEvent,
)
from core.runtime.runtime_execution_result_fields import normalize_runtime_execution_fields
from core.runtime.runtime_event_bus import RuntimeEventBus
from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_status import (
    canonical_runtime_status_payload,
    status_from_lifecycle_phase,
)
from core.runtime.runtime_status_transition import runtime_status_transition_payload


RUNTIME_STATES = {
    "PENDING",
    "SCANNING",
    "PLANNING",
    "APPLYING",
    "VERIFYING",
    "COMMITTING",
    "ROLLING_BACK",
    "RECOVERING",
    "REPLAYING",
    "FINALIZED",
    "FAILED",
    "BLOCKED",
}

ALLOWED_TRANSITIONS = {
    "PENDING": {"SCANNING", "BLOCKED", "FAILED"},
    "SCANNING": {"PLANNING", "BLOCKED", "FAILED"},
    "PLANNING": {"APPLYING", "BLOCKED", "FAILED"},
    "APPLYING": {"VERIFYING", "ROLLING_BACK", "RECOVERING", "FAILED", "BLOCKED"},
    "VERIFYING": {"COMMITTING", "ROLLING_BACK", "RECOVERING", "FAILED", "BLOCKED"},
    "COMMITTING": {"REPLAYING", "FINALIZED", "ROLLING_BACK", "FAILED", "BLOCKED"},
    "ROLLING_BACK": {"RECOVERING", "REPLAYING", "FINALIZED", "FAILED"},
    "RECOVERING": {"PLANNING", "APPLYING", "VERIFYING", "REPLAYING", "FINALIZED", "FAILED"},
    "REPLAYING": {"FINALIZED", "FAILED"},
    "FINALIZED": set(),
    "FAILED": set(),
    "BLOCKED": {"RECOVERING", "FAILED"},
}


@dataclass(frozen=True)
class RuntimeStateTransition:
    sequence: int
    old_state: str
    new_state: str
    reason: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        transition = runtime_status_transition_payload(
            status_from_lifecycle_phase(self.old_state),
            status_from_lifecycle_phase(self.new_state),
            source="runtime_kernel_state",
            metadata=self.metadata,
        )
        return {
            "canonical_status": status_from_lifecycle_phase(self.new_state),
            "canonical_from_status": transition["from_status"],
            "canonical_to_status": transition["to_status"],
            "transition_allowed": transition["allowed"],
            "transition_regression": transition["regression"],
            "transition_reason": transition["transition_reason"],
            "transition_trigger": transition["transition_trigger"],
            "transition_source": transition["transition_source"],
            "transition_evidence": transition["transition_evidence"],
            "enforcement_readiness": transition["enforcement_readiness"],
            "enforcement_classification": transition["enforcement_classification"],
            "enforcement_reason": transition["enforcement_reason"],
            "safe_to_enforce": transition["safe_to_enforce"],
            "review_required": transition["review_required"],
            "block_recommended": transition["block_recommended"],
            "sequence": self.sequence,
            "old_state": self.old_state,
            "new_state": self.new_state,
            "reason": self.reason,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RuntimeCheckpoint:
    checkpoint_id: str
    state: str
    sequence: int
    created_at: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "state": self.state,
            "canonical_status": status_from_lifecycle_phase(self.state),
            "sequence": self.sequence,
            "created_at": self.created_at,
            "payload": copy.deepcopy(self.payload),
        }


class RuntimeKernelStateMachine:
    def __init__(
        self,
        *,
        event_bus: RuntimeEventBus | None = None,
        journal: RuntimeJournal | None = None,
    ) -> None:
        self.state = "PENDING"
        self.transitions: list[RuntimeStateTransition] = []
        self.checkpoints: list[RuntimeCheckpoint] = []
        self.events: list[RuntimeEvent] = []
        self.event_bus = event_bus
        self.journal = journal
        self._sequence = 0

    def transition(
        self,
        new_state: str,
        *,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeStateTransition:
        target = _normalize_state(new_state)
        if target != self.state and target not in ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"invalid_runtime_transition:{self.state}->{target}")
        next_sequence = self._sequence + 1
        event = RuntimeStateTransitionEvent(
            old_state=self.state,
            new_state=target,
            reason=str(reason or ""),
            metadata=metadata or {},
            sequence=next_sequence,
        )
        self._append_event_before_apply(event)
        self._sequence = next_sequence
        record = RuntimeStateTransition(
            sequence=next_sequence,
            old_state=self.state,
            new_state=target,
            reason=str(reason or ""),
            created_at=_utc_now(),
            metadata={
                **dict(metadata or {}),
                **_kernel_transition_flags(self.state, target, metadata),
            },
        )
        self.transitions.append(record)
        self.state = target
        return record

    def checkpoint(self, payload: dict[str, Any] | None = None) -> RuntimeCheckpoint:
        data = _normalize_checkpoint_payload(payload or {})
        seed = {
            "state": self.state,
            "sequence": self._sequence,
            "payload": data,
            "transition_count": len(self.transitions),
        }
        checkpoint = RuntimeCheckpoint(
            checkpoint_id="runtime-checkpoint-" + _stable_hash(seed)[:16],
            state=self.state,
            sequence=self._sequence,
            created_at=_utc_now(),
            payload=data,
        )
        self.checkpoints.append(checkpoint)
        return checkpoint

    def restore(self, checkpoint_id: str) -> RuntimeCheckpoint:
        for checkpoint in reversed(self.checkpoints):
            if checkpoint.checkpoint_id == checkpoint_id:
                self.state = checkpoint.state
                self._sequence = checkpoint.sequence
                return checkpoint
        raise ValueError(f"runtime_checkpoint_not_found:{checkpoint_id}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "canonical_status": status_from_lifecycle_phase(self.state),
            "transitions": [item.to_dict() for item in self.transitions],
            "checkpoints": [item.to_dict() for item in self.checkpoints],
            "events": [item.to_dict() for item in self.events],
        }

    def _append_event_before_apply(self, event: RuntimeEvent) -> None:
        if self.journal is not None:
            self.journal.append_event(event, phase="before_state_transition")
        if self.event_bus is not None:
            published = self.event_bus.publish_event(
                event,
                channel=RUNTIME_EVENT_CHANNEL,
                metadata=event.metadata,
            )
            if isinstance(published.payload, RuntimeEvent):
                event = published.payload
        self.events.append(event)


def _normalize_state(value: str) -> str:
    state = str(value or "").strip().upper()
    if state not in RUNTIME_STATES:
        raise ValueError(f"unknown_runtime_state:{value}")
    return state


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _kernel_transition_flags(
    old_state: Any,
    new_state: Any,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    transition = runtime_status_transition_payload(
        status_from_lifecycle_phase(old_state),
        status_from_lifecycle_phase(new_state),
        source="runtime_kernel_state",
        metadata=metadata,
    )
    return {
        "canonical_from_status": transition["from_status"],
        "canonical_to_status": transition["to_status"],
        "transition_allowed": transition["allowed"],
        "transition_regression": transition["regression"],
        "transition_reason": transition["transition_reason"],
        "transition_trigger": transition["transition_trigger"],
        "transition_source": transition["transition_source"],
        "transition_evidence": transition["transition_evidence"],
        "enforcement_readiness": transition["enforcement_readiness"],
        "enforcement_classification": transition["enforcement_classification"],
        "enforcement_reason": transition["enforcement_reason"],
        "safe_to_enforce": transition["safe_to_enforce"],
        "review_required": transition["review_required"],
        "block_recommended": transition["block_recommended"],
    }


def _normalize_checkpoint_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(payload or {})
    if not isinstance(data, dict):
        return {}

    for key in ("runtime_execution_result", "execution_result"):
        if isinstance(data.get(key), dict):
            data[key] = normalize_runtime_execution_fields(
                data[key],
                metadata=data[key].get("metadata"),
                evidence=data[key].get("evidence"),
            )

    if _looks_like_execution_payload(data):
        return canonical_runtime_status_payload(normalize_runtime_execution_fields(
            data,
            metadata=data.get("metadata"),
            evidence=data.get("evidence"),
        ))

    return canonical_runtime_status_payload(data, status=status_from_lifecycle_phase(data.get("state") or data.get("status") or data.get("phase")))


def _looks_like_execution_payload(payload: dict[str, Any]) -> bool:
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
        )
    )


__all__ = [
    "ALLOWED_TRANSITIONS",
    "RUNTIME_STATES",
    "RuntimeCheckpoint",
    "RuntimeKernelStateMachine",
    "RuntimeStateTransition",
]

# ZERO v7.3.14 - Runtime finalized rollback transition seal
# Allows governed repair/recovery path to move from FINALIZED to ROLLING_BACK.


try:
    ALLOWED_TRANSITIONS.setdefault(RuntimeKernelPhase.FINALIZED, set()).add(
        RuntimeKernelPhase.ROLLING_BACK
    )
except Exception:
    try:
        ALLOWED_TRANSITIONS.setdefault("FINALIZED", set()).add("ROLLING_BACK")
    except Exception:
        pass
