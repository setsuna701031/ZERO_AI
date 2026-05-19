"""Runtime lifecycle coordinator.

This module provides a shared lifecycle transition policy for runtime artifacts:
transactions, executions, mutations, state records, replay records, and rollback
flows.

It does not execute commands, mutate files, or persist state. It only validates
and records lifecycle transitions so higher runtime layers can share one
coherent lifecycle universe.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any


RUNTIME_LIFECYCLE_STATES = {
    "created",
    "active",
    "verifying",
    "verified",
    "rollback_required",
    "rolling_back",
    "rolled_back",
    "committed",
    "sealed",
    "failed",
}

TERMINAL_LIFECYCLE_STATES = {
    "rolled_back",
    "committed",
    "sealed",
    "failed",
}

DEFAULT_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "created": {"active", "failed"},
    "active": {"verifying", "verified", "rollback_required", "committed", "failed"},
    "verifying": {"verified", "rollback_required", "failed"},
    "verified": {"committed", "sealed", "rollback_required", "failed"},
    "rollback_required": {"rolling_back", "failed"},
    "rolling_back": {"rolled_back", "failed"},
    "rolled_back": {"sealed"},
    "committed": {"sealed"},
    "sealed": set(),
    "failed": {"sealed"},
}

RUNTIME_ARTIFACT_TYPES = {
    "transaction",
    "execution",
    "mutation",
    "state",
    "snapshot",
    "replay",
    "rollback",
    "side_effect",
    "session",
}


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_state(value: Any) -> str:
    state = _clean_text(value).lower()
    if state not in RUNTIME_LIFECYCLE_STATES:
        raise ValueError(f"unsupported runtime lifecycle state: {value}")
    return state


def _normalize_artifact_type(value: Any) -> str:
    artifact_type = _clean_text(value).lower()
    if artifact_type not in RUNTIME_ARTIFACT_TYPES:
        raise ValueError(f"unsupported runtime artifact type: {value}")
    return artifact_type


@dataclass(frozen=True)
class RuntimeLifecycleRecord:
    lifecycle_id: str
    artifact_id: str
    artifact_type: str
    state: str = "created"
    transaction_id: str = ""
    parent_lifecycle_id: str = ""
    lineage: dict[str, Any] = field(default_factory=dict)
    authority_metadata: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)
    sealed: bool = False
    verified: bool = False
    rollback_required: bool = False
    transition_history: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        lifecycle_id = _clean_text(self.lifecycle_id)
        artifact_id = _clean_text(self.artifact_id)
        if not lifecycle_id:
            raise ValueError("lifecycle_id is required")
        if not artifact_id:
            raise ValueError("artifact_id is required")
        object.__setattr__(self, "lifecycle_id", lifecycle_id)
        object.__setattr__(self, "artifact_id", artifact_id)
        object.__setattr__(self, "artifact_type", _normalize_artifact_type(self.artifact_type))
        object.__setattr__(self, "state", _normalize_state(self.state))
        object.__setattr__(self, "transaction_id", _clean_text(self.transaction_id))
        object.__setattr__(self, "parent_lifecycle_id", _clean_text(self.parent_lifecycle_id))

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_LIFECYCLE_STATES or self.sealed

    def to_metadata(self) -> dict[str, Any]:
        return {
            "lifecycle_id": self.lifecycle_id,
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "state": self.state,
            "transaction_id": self.transaction_id,
            "parent_lifecycle_id": self.parent_lifecycle_id,
            "sealed": self.sealed,
            "verified": self.verified,
            "rollback_required": self.rollback_required,
            "lineage": dict(self.lineage),
            "authority": dict(self.authority_metadata),
            "provenance": dict(self.provenance),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "transition_history": [dict(item) for item in self.transition_history],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RuntimeLifecycleDecision:
    allowed: bool
    from_state: str
    to_state: str
    reason: str
    requires_rollback: bool = False
    seals_record: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeLifecycleResult:
    record: RuntimeLifecycleRecord
    decision: RuntimeLifecycleDecision
    transitioned: bool
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.decision.allowed and self.status in {"created", "transitioned", "unchanged"}


class RuntimeLifecyclePolicy:
    def __init__(
        self,
        *,
        allowed_transitions: dict[str, set[str]] | None = None,
    ) -> None:
        self.allowed_transitions = {
            state: set(targets)
            for state, targets in (allowed_transitions or DEFAULT_ALLOWED_TRANSITIONS).items()
        }

    def evaluate(
        self,
        *,
        record: RuntimeLifecycleRecord,
        to_state: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeLifecycleDecision:
        target = _normalize_state(to_state)
        source = record.state

        if record.sealed:
            return RuntimeLifecycleDecision(
                allowed=False,
                from_state=source,
                to_state=target,
                reason="lifecycle_record_is_sealed",
                metadata=dict(metadata or {}),
            )

        if target == source:
            return RuntimeLifecycleDecision(
                allowed=True,
                from_state=source,
                to_state=target,
                reason="lifecycle_state_unchanged",
                requires_rollback=record.rollback_required,
                seals_record=target == "sealed",
                metadata=dict(metadata or {}),
            )

        allowed_targets = self.allowed_transitions.get(source, set())
        if target not in allowed_targets:
            return RuntimeLifecycleDecision(
                allowed=False,
                from_state=source,
                to_state=target,
                reason=f"invalid_lifecycle_transition:{source}->{target}",
                metadata=dict(metadata or {}),
            )

        return RuntimeLifecycleDecision(
            allowed=True,
            from_state=source,
            to_state=target,
            reason="transition_allowed",
            requires_rollback=target in {"rollback_required", "rolling_back"},
            seals_record=target == "sealed",
            metadata=dict(metadata or {}),
        )


class RuntimeLifecycleCoordinator:
    """In-memory lifecycle coordinator for runtime artifact state."""

    def __init__(
        self,
        *,
        policy: RuntimeLifecyclePolicy | None = None,
    ) -> None:
        self.policy = policy or RuntimeLifecyclePolicy()
        self._records: dict[str, RuntimeLifecycleRecord] = {}

    def create_record(
        self,
        *,
        lifecycle_id: str,
        artifact_id: str,
        artifact_type: str,
        transaction_id: str = "",
        parent_lifecycle_id: str = "",
        lineage: dict[str, Any] | None = None,
        authority_metadata: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeLifecycleResult:
        cleaned_id = _clean_text(lifecycle_id)
        if cleaned_id in self._records:
            raise ValueError(f"lifecycle record already exists: {cleaned_id}")
        if parent_lifecycle_id and parent_lifecycle_id not in self._records:
            raise ValueError(f"parent lifecycle record does not exist: {parent_lifecycle_id}")

        record = RuntimeLifecycleRecord(
            lifecycle_id=cleaned_id,
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            transaction_id=transaction_id,
            parent_lifecycle_id=parent_lifecycle_id,
            lineage=dict(lineage or {}),
            authority_metadata=dict(authority_metadata or {}),
            provenance=dict(provenance or {}),
            metadata=dict(metadata or {}),
        )
        self._records[record.lifecycle_id] = record
        decision = RuntimeLifecycleDecision(
            allowed=True,
            from_state="created",
            to_state="created",
            reason="lifecycle_record_created",
            metadata=dict(metadata or {}),
        )
        return RuntimeLifecycleResult(
            record=record,
            decision=decision,
            transitioned=False,
            status="created",
            metadata={"action": "create_record"},
        )

    def get_record(self, lifecycle_id: str) -> RuntimeLifecycleRecord:
        cleaned_id = _clean_text(lifecycle_id)
        if cleaned_id not in self._records:
            raise KeyError(f"unknown lifecycle record: {cleaned_id}")
        return self._records[cleaned_id]

    def transition(
        self,
        lifecycle_id: str,
        to_state: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeLifecycleResult:
        record = self.get_record(lifecycle_id)
        decision = self.policy.evaluate(record=record, to_state=to_state, metadata=metadata)
        if not decision.allowed:
            return RuntimeLifecycleResult(
                record=record,
                decision=decision,
                transitioned=False,
                status="blocked",
                metadata={"action": "transition_blocked", **dict(metadata or {})},
            )

        target = _normalize_state(to_state)
        if target == record.state:
            return RuntimeLifecycleResult(
                record=record,
                decision=decision,
                transitioned=False,
                status="unchanged",
                metadata={"action": "transition_unchanged", **dict(metadata or {})},
            )

        event = {
            "from_state": record.state,
            "to_state": target,
            "reason": decision.reason,
            "timestamp": utc_timestamp(),
            "metadata": dict(metadata or {}),
        }
        updated = replace(
            record,
            state=target,
            updated_at=event["timestamp"],
            sealed=record.sealed or target == "sealed",
            verified=record.verified or target == "verified",
            rollback_required=(record.rollback_required or target == "rollback_required")
            and target not in {"rolled_back", "committed", "sealed"},
            transition_history=(*record.transition_history, event),
            metadata={**dict(record.metadata), "last_lifecycle_transition": event, **dict(metadata or {})},
        )
        self._records[updated.lifecycle_id] = updated
        return RuntimeLifecycleResult(
            record=updated,
            decision=decision,
            transitioned=True,
            status="transitioned",
            metadata={"action": "transition", **dict(metadata or {})},
        )

    def mark_active(self, lifecycle_id: str, metadata: dict[str, Any] | None = None) -> RuntimeLifecycleResult:
        return self.transition(lifecycle_id, "active", metadata=metadata)

    def mark_verifying(self, lifecycle_id: str, metadata: dict[str, Any] | None = None) -> RuntimeLifecycleResult:
        return self.transition(lifecycle_id, "verifying", metadata=metadata)

    def mark_verified(self, lifecycle_id: str, metadata: dict[str, Any] | None = None) -> RuntimeLifecycleResult:
        return self.transition(lifecycle_id, "verified", metadata=metadata)

    def mark_rollback_required(self, lifecycle_id: str, metadata: dict[str, Any] | None = None) -> RuntimeLifecycleResult:
        return self.transition(lifecycle_id, "rollback_required", metadata=metadata)

    def mark_rolling_back(self, lifecycle_id: str, metadata: dict[str, Any] | None = None) -> RuntimeLifecycleResult:
        return self.transition(lifecycle_id, "rolling_back", metadata=metadata)

    def mark_rolled_back(self, lifecycle_id: str, metadata: dict[str, Any] | None = None) -> RuntimeLifecycleResult:
        return self.transition(lifecycle_id, "rolled_back", metadata=metadata)

    def commit(self, lifecycle_id: str, metadata: dict[str, Any] | None = None) -> RuntimeLifecycleResult:
        return self.transition(lifecycle_id, "committed", metadata=metadata)

    def seal(self, lifecycle_id: str, metadata: dict[str, Any] | None = None) -> RuntimeLifecycleResult:
        return self.transition(lifecycle_id, "sealed", metadata=metadata)

    def fail(self, lifecycle_id: str, metadata: dict[str, Any] | None = None) -> RuntimeLifecycleResult:
        return self.transition(lifecycle_id, "failed", metadata=metadata)

    def records_for_transaction(self, transaction_id: str) -> tuple[RuntimeLifecycleRecord, ...]:
        cleaned_id = _clean_text(transaction_id)
        return tuple(
            record
            for record in self._records.values()
            if record.transaction_id == cleaned_id
        )
