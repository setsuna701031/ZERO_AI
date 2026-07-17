"""Canonical runtime transition record.

This module defines the stable transition record shared by runtime lifecycle,
guard, enforcement, replay, recovery, and sovereignty surfaces.

It is intentionally pure:
- no command execution
- no file mutation
- no scheduler import
- no agent_loop import
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


RUNTIME_TRANSITION_RECORD_SCHEMA = "runtime_transition_record.v1"


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _deepcopy_mapping(value: dict[str, Any] | None) -> dict[str, Any]:
    return copy.deepcopy(dict(value or {}))


@dataclass(frozen=True)
class RuntimeTransitionRecord:
    """Canonical transition record shared across runtime governance surfaces."""

    transition_id: str
    source: str
    from_state: str
    to_state: str
    allowed: bool
    reason: str
    status: str
    schema: str = RUNTIME_TRANSITION_RECORD_SCHEMA
    timestamp: str = field(default_factory=utc_timestamp)
    normalized_from_state: str = ""
    normalized_to_state: str = ""
    canonical_from_status: str = ""
    canonical_to_status: str = ""
    enforcement_mode: str = ""
    enforcement_allowed: bool | None = None
    enforcement_classification: str = ""
    blocked: bool | None = None
    would_block: bool | None = None
    guard_ok: bool | None = None
    guard_reason: str = ""
    lifecycle_id: str = ""
    artifact_id: str = ""
    artifact_type: str = ""
    replay_id: str = ""
    recovery_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        transition_id = _clean_text(self.transition_id)
        source = _clean_text(self.source)
        from_state = _clean_text(self.from_state)
        to_state = _clean_text(self.to_state)
        reason = _clean_text(self.reason)
        status = _clean_text(self.status)

        if not transition_id:
            raise ValueError("transition_id is required")
        if not source:
            raise ValueError("source is required")
        if not from_state:
            raise ValueError("from_state is required")
        if not to_state:
            raise ValueError("to_state is required")
        if not reason:
            raise ValueError("reason is required")
        if not status:
            raise ValueError("status is required")

        object.__setattr__(self, "transition_id", transition_id)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "from_state", from_state)
        object.__setattr__(self, "to_state", to_state)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "normalized_from_state", _clean_text(self.normalized_from_state))
        object.__setattr__(self, "normalized_to_state", _clean_text(self.normalized_to_state))
        object.__setattr__(self, "canonical_from_status", _clean_text(self.canonical_from_status))
        object.__setattr__(self, "canonical_to_status", _clean_text(self.canonical_to_status))
        object.__setattr__(self, "enforcement_mode", _clean_text(self.enforcement_mode))
        object.__setattr__(self, "enforcement_classification", _clean_text(self.enforcement_classification))
        object.__setattr__(self, "guard_reason", _clean_text(self.guard_reason))
        object.__setattr__(self, "lifecycle_id", _clean_text(self.lifecycle_id))
        object.__setattr__(self, "artifact_id", _clean_text(self.artifact_id))
        object.__setattr__(self, "artifact_type", _clean_text(self.artifact_type))
        object.__setattr__(self, "replay_id", _clean_text(self.replay_id))
        object.__setattr__(self, "recovery_id", _clean_text(self.recovery_id))
        object.__setattr__(self, "metadata", _deepcopy_mapping(self.metadata))
        object.__setattr__(self, "evidence", _deepcopy_mapping(self.evidence))

    @property
    def ok(self) -> bool:
        if not self.allowed:
            return False
        if self.blocked is True:
            return False
        if self.guard_ok is False:
            return False
        return self.status not in {"blocked", "rejected", "failed"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "transition_id": self.transition_id,
            "source": self.source,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "normalized_from_state": self.normalized_from_state,
            "normalized_to_state": self.normalized_to_state,
            "canonical_from_status": self.canonical_from_status,
            "canonical_to_status": self.canonical_to_status,
            "allowed": self.allowed,
            "reason": self.reason,
            "status": self.status,
            "ok": self.ok,
            "timestamp": self.timestamp,
            "enforcement_mode": self.enforcement_mode,
            "enforcement_allowed": self.enforcement_allowed,
            "enforcement_classification": self.enforcement_classification,
            "blocked": self.blocked,
            "would_block": self.would_block,
            "guard_ok": self.guard_ok,
            "guard_reason": self.guard_reason,
            "lifecycle_id": self.lifecycle_id,
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "replay_id": self.replay_id,
            "recovery_id": self.recovery_id,
            "metadata": copy.deepcopy(self.metadata),
            "evidence": copy.deepcopy(self.evidence),
        }

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "RuntimeTransitionRecord":
        payload = dict(value or {})
        return cls(
            transition_id=payload.get("transition_id", ""),
            source=payload.get("source", ""),
            from_state=payload.get("from_state", ""),
            to_state=payload.get("to_state", ""),
            normalized_from_state=payload.get("normalized_from_state", ""),
            normalized_to_state=payload.get("normalized_to_state", ""),
            canonical_from_status=payload.get("canonical_from_status", ""),
            canonical_to_status=payload.get("canonical_to_status", ""),
            allowed=bool(payload.get("allowed", False)),
            reason=payload.get("reason", ""),
            status=payload.get("status", ""),
            timestamp=payload.get("timestamp") or utc_timestamp(),
            enforcement_mode=payload.get("enforcement_mode", ""),
            enforcement_allowed=payload.get("enforcement_allowed"),
            enforcement_classification=payload.get("enforcement_classification", ""),
            blocked=payload.get("blocked"),
            would_block=payload.get("would_block"),
            guard_ok=payload.get("guard_ok"),
            guard_reason=payload.get("guard_reason", ""),
            lifecycle_id=payload.get("lifecycle_id", ""),
            artifact_id=payload.get("artifact_id", ""),
            artifact_type=payload.get("artifact_type", ""),
            replay_id=payload.get("replay_id", ""),
            recovery_id=payload.get("recovery_id", ""),
            metadata=payload.get("metadata") or {},
            evidence=payload.get("evidence") or {},
        )


def runtime_transition_record_from_parts(
    *,
    transition_id: str,
    source: str,
    from_state: str,
    to_state: str,
    allowed: bool,
    reason: str,
    status: str,
    normalized_from_state: str = "",
    normalized_to_state: str = "",
    canonical_from_status: str = "",
    canonical_to_status: str = "",
    enforcement_mode: str = "",
    enforcement_allowed: bool | None = None,
    enforcement_classification: str = "",
    blocked: bool | None = None,
    would_block: bool | None = None,
    guard_ok: bool | None = None,
    guard_reason: str = "",
    lifecycle_id: str = "",
    artifact_id: str = "",
    artifact_type: str = "",
    replay_id: str = "",
    recovery_id: str = "",
    metadata: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
) -> RuntimeTransitionRecord:
    return RuntimeTransitionRecord(
        transition_id=transition_id,
        source=source,
        from_state=from_state,
        to_state=to_state,
        normalized_from_state=normalized_from_state,
        normalized_to_state=normalized_to_state,
        canonical_from_status=canonical_from_status,
        canonical_to_status=canonical_to_status,
        allowed=allowed,
        reason=reason,
        status=status,
        enforcement_mode=enforcement_mode,
        enforcement_allowed=enforcement_allowed,
        enforcement_classification=enforcement_classification,
        blocked=blocked,
        would_block=would_block,
        guard_ok=guard_ok,
        guard_reason=guard_reason,
        lifecycle_id=lifecycle_id,
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        replay_id=replay_id,
        recovery_id=recovery_id,
        metadata=metadata or {},
        evidence=evidence or {},
    )
