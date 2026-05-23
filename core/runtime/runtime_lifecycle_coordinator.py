"""Runtime lifecycle coordinator.

This module provides a shared lifecycle transition policy for runtime artifacts:
transactions, executions, mutations, state records, replay records, and rollback
flows.

It does not execute commands, mutate files, or persist state. It only validates
and records lifecycle transitions so higher runtime layers can share one
coherent lifecycle universe.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from core.runtime.runtime_enforcement_readiness import (
    RuntimeEnforcementMode,
    runtime_enforcement_decision_snapshot,
)
from core.runtime.runtime_status import status_from_lifecycle_phase
from core.runtime.runtime_status_transition import runtime_status_transition_payload

try:
    from core.runtime.runtime_transition_guard import guard_runtime_transition
    from core.runtime.runtime_state_names import (
        SESSION_BLOCKED,
        SESSION_FAILED,
        SESSION_RESTORED,
        SESSION_ROLLED_BACK,
        SESSION_RUNNING,
        SESSION_SEALED,
    )
except Exception:  # pragma: no cover - compatibility during staged runtime imports
    guard_runtime_transition = None  # type: ignore[assignment]
    SESSION_RUNNING = "SESSION_RUNNING"  # type: ignore[assignment]
    SESSION_BLOCKED = "SESSION_BLOCKED"  # type: ignore[assignment]
    SESSION_SEALED = "SESSION_SEALED"  # type: ignore[assignment]
    SESSION_FAILED = "SESSION_FAILED"  # type: ignore[assignment]
    SESSION_ROLLED_BACK = "SESSION_ROLLED_BACK"  # type: ignore[assignment]
    SESSION_RESTORED = "SESSION_RESTORED"  # type: ignore[assignment]


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


def _transition_validation(
    from_state: Any,
    to_state: Any,
    *,
    metadata: dict[str, Any] | None = None,
    enforcement_mode: RuntimeEnforcementMode | str = RuntimeEnforcementMode.AUDIT_ONLY,
) -> dict[str, Any]:
    return runtime_status_transition_payload(
        status_from_lifecycle_phase(from_state),
        status_from_lifecycle_phase(to_state),
        source="runtime_lifecycle_coordinator",
        metadata=metadata,
        mode=enforcement_mode,
    )


def _transition_audit_fields(transition: dict[str, Any]) -> dict[str, Any]:
    decision_snapshot = runtime_enforcement_decision_snapshot(
        transition.get("enforcement_decision")
    )
    return {
        "transition_allowed": transition["allowed"],
        "transition_regression": transition["regression"],
        "transition_reason": transition["transition_reason"],
        "transition_trigger": transition["transition_trigger"],
        "transition_source": transition["transition_source"],
        "transition_evidence": copy.deepcopy(transition["transition_evidence"]),
        "enforcement_readiness": transition["enforcement_readiness"],
        "enforcement_classification": transition["enforcement_classification"],
        "enforcement_reason": transition["enforcement_reason"],
        "safe_to_enforce": transition["safe_to_enforce"],
        "review_required": transition["review_required"],
        "block_recommended": transition["block_recommended"],
        "enforcement_mode": transition.get("enforcement_mode"),
        "enforcement_decision": decision_snapshot,
        "enforcement_decision_schema": decision_snapshot["schema"],
        "enforcement_allowed": transition.get("enforcement_allowed"),
        "blocked": transition.get("blocked"),
        "would_block": transition.get("would_block"),
    }



def _sovereign_state_from_lifecycle(state: Any) -> str:
    normalized = _clean_text(state).lower()
    mapping = {
        "created": SESSION_RUNNING,
        "active": SESSION_RUNNING,
        "verifying": SESSION_RUNNING,
        "verified": SESSION_RUNNING,
        "committed": SESSION_RESTORED,
        "rollback_required": SESSION_ROLLED_BACK,
        "rolling_back": SESSION_ROLLED_BACK,
        "rolled_back": SESSION_ROLLED_BACK,
        "sealed": SESSION_SEALED,
        "failed": SESSION_FAILED,
        "blocked": SESSION_BLOCKED,
    }
    return mapping.get(normalized, SESSION_RUNNING)


def _guard_lifecycle_transition(
    from_state: str,
    to_state: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if guard_runtime_transition is None:
        return {
            "ok": True,
            "transition_guarded": False,
            "from_state": from_state,
            "to_state": to_state,
            "reason": "runtime_transition_guard_unavailable",
        }

    from_sovereign = _sovereign_state_from_lifecycle(from_state)
    to_sovereign = _sovereign_state_from_lifecycle(to_state)

    if from_sovereign == to_sovereign:
        return {
            "ok": True,
            "transition_guarded": True,
            "from_state": from_sovereign,
            "to_state": to_sovereign,
            "reason": "sovereign_state_unchanged",
            "metadata": dict(metadata or {}),
        }

    guard_metadata = {
        **dict(metadata or {}),
        "lifecycle_from_state": from_state,
        "lifecycle_to_state": to_state,
    }
    try:
        result = guard_runtime_transition(
            from_sovereign,
            to_sovereign,
            metadata=guard_metadata,
        )
    except Exception as exc:  # pragma: no cover - defensive bridge for staged guards
        return {
            "ok": False,
            "transition_guarded": True,
            "from_state": from_sovereign,
            "to_state": to_sovereign,
            "lifecycle_from_state": from_state,
            "lifecycle_to_state": to_state,
            "sovereign_from_state": from_sovereign,
            "sovereign_to_state": to_sovereign,
            "reason": "runtime_transition_guard_rejected",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "metadata": guard_metadata,
        }
    return {
        **result,
        "lifecycle_from_state": from_state,
        "lifecycle_to_state": to_state,
        "sovereign_from_state": from_sovereign,
        "sovereign_to_state": to_sovereign,
    }



def _transition_persistence_fields(transition: dict[str, Any]) -> dict[str, Any]:
    audit_fields = _transition_audit_fields(transition)
    decision_snapshot = runtime_enforcement_decision_snapshot(
        audit_fields.get("enforcement_decision")
    )
    return {
        "transition_allowed": audit_fields["transition_allowed"],
        "transition_regression": audit_fields["transition_regression"],
        "transition_reason": audit_fields["transition_reason"],
        "transition_trigger": audit_fields["transition_trigger"],
        "transition_source": audit_fields["transition_source"],
        "transition_evidence": copy.deepcopy(audit_fields["transition_evidence"]),
        "enforcement_mode": audit_fields["enforcement_mode"],
        "enforcement_classification": audit_fields["enforcement_classification"],
        "enforcement_reason": audit_fields["enforcement_reason"],
        "safe_to_enforce": audit_fields["safe_to_enforce"],
        "review_required": audit_fields["review_required"],
        "block_recommended": audit_fields["block_recommended"],
        "enforcement_allowed": audit_fields["enforcement_allowed"],
        "blocked": audit_fields["blocked"],
        "would_block": audit_fields["would_block"],
        "enforcement_decision_schema": decision_snapshot["schema"],
        "enforcement_decision": decision_snapshot,
    }


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
            "canonical_status": status_from_lifecycle_phase(self.state),
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

    def to_metadata(self) -> dict[str, Any]:
        transition = _transition_validation(self.from_state, self.to_state)
        return {
            "allowed": self.allowed,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "canonical_status": status_from_lifecycle_phase(self.to_state),
            "canonical_from_status": transition["from_status"],
            "canonical_to_status": transition["to_status"],
            **_transition_audit_fields(transition),
            "reason": self.reason,
            "requires_rollback": self.requires_rollback,
            "seals_record": self.seals_record,
            "metadata": dict(self.metadata),
        }


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

    def to_metadata(self) -> dict[str, Any]:
        transition = _transition_validation(self.decision.from_state, self.decision.to_state)
        audit_fields = _transition_audit_fields(transition)
        audit_fields.update(
            {
                key: self.metadata[key]
                for key in audit_fields
                if key in self.metadata
            }
        )
        return {
            "record": self.record.to_metadata(),
            "decision": self.decision.to_metadata(),
            "transitioned": self.transitioned,
            "status": self.status,
            "canonical_status": status_from_lifecycle_phase(self.record.state),
            "canonical_from_status": transition["from_status"],
            "canonical_to_status": transition["to_status"],
            **audit_fields,
            "metadata": dict(self.metadata),
        }


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
        transition = _transition_validation("created", "created")
        return RuntimeLifecycleResult(
            record=record,
            decision=decision,
            transitioned=False,
            status="created",
            metadata={
                "action": "create_record",
                "canonical_status": status_from_lifecycle_phase("created"),
                **_transition_audit_fields(transition),
            },
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
        enforcement_mode: RuntimeEnforcementMode | str = RuntimeEnforcementMode.AUDIT_ONLY,
    ) -> RuntimeLifecycleResult:
        record = self.get_record(lifecycle_id)
        target = _normalize_state(to_state)
        transition_guard_result = {
            "ok": True,
            "transition_guarded": False,
            "from_state": record.state,
            "to_state": target,
            "lifecycle_from_state": record.state,
            "lifecycle_to_state": target,
            "reason": "guard_not_evaluated",
            "metadata": dict(metadata or {}),
        }

        decision = self.policy.evaluate(record=record, to_state=target, metadata=metadata)
        transition = _transition_validation(
            decision.from_state,
            decision.to_state,
            metadata=metadata,
            enforcement_mode=enforcement_mode,
        )
        if not decision.allowed:
            return RuntimeLifecycleResult(
                record=record,
                decision=decision,
                transitioned=False,
                status="blocked",
                metadata={
                    "action": "transition_blocked",
                    "canonical_status": status_from_lifecycle_phase("blocked"),
                    **_transition_audit_fields(transition),
                    "runtime_transition_guard": copy.deepcopy(transition_guard_result),
                    **dict(metadata or {}),
                },
            )

        transition_guard_result = _guard_lifecycle_transition(
            record.state,
            target,
            metadata=metadata,
        )
        if target == record.state:
            return RuntimeLifecycleResult(
                record=record,
                decision=decision,
                transitioned=False,
                status="unchanged",
                metadata={
                    "action": "transition_unchanged",
                    "canonical_status": status_from_lifecycle_phase(target),
                    **_transition_audit_fields(transition),
                    "runtime_transition_guard": copy.deepcopy(transition_guard_result),
                    **dict(metadata or {}),
                },
            )

        persistence_fields = _transition_persistence_fields(transition)
        event = {
            "from_state": record.state,
            "to_state": target,
            "reason": decision.reason,
            "timestamp": utc_timestamp(),
            "metadata": {
                **persistence_fields,
                "runtime_transition_guard": copy.deepcopy(transition_guard_result),
                **dict(metadata or {}),
            },
            "enforcement_decision": persistence_fields["enforcement_decision"],
            "enforcement_decision_schema": persistence_fields["enforcement_decision_schema"],
            "enforcement_mode": persistence_fields["enforcement_mode"],
            "enforcement_classification": persistence_fields["enforcement_classification"],
            "enforcement_allowed": persistence_fields["enforcement_allowed"],
            "blocked": persistence_fields["blocked"],
            "would_block": persistence_fields["would_block"],
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
            metadata={
                **dict(record.metadata),
                "last_lifecycle_transition": copy.deepcopy(event),
                "last_enforcement_decision": copy.deepcopy(persistence_fields["enforcement_decision"]),
                "last_enforcement_decision_schema": persistence_fields["enforcement_decision_schema"],
                **dict(metadata or {}),
            },
        )
        self._records[updated.lifecycle_id] = updated
        return RuntimeLifecycleResult(
            record=updated,
            decision=decision,
            transitioned=True,
            status="transitioned",
            metadata={
                "action": "transition",
                "canonical_status": status_from_lifecycle_phase(target),
                **_transition_audit_fields(transition),
                "runtime_transition_guard": copy.deepcopy(transition_guard_result),
                **dict(metadata or {}),
            },
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
