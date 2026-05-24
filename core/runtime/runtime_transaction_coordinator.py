"""Runtime transaction coordinator.

This module provides a small, dependency-light transaction scope layer for
binding runtime execution, mutation, state, snapshot, replay, and side-effect
records into one coherent transaction universe.

It intentionally does not execute, mutate, persist files, or open public
execution. It only tracks transaction membership and lifecycle state.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from core.runtime.runtime_seal import attach_runtime_seal
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION
from core.runtime.runtime_event_bus import RuntimeEventBus
from core.runtime.runtime_execution_result_fields import normalize_runtime_execution_fields
from core.runtime.runtime_authority import build_authority_metadata
from core.runtime.runtime_closure import build_runtime_closure_fields
from core.runtime.runtime_consistency import build_runtime_state_consistency
from core.runtime.runtime_recovery_readiness import build_runtime_recovery_readiness_fields
from core.runtime.runtime_events import (
    RUNTIME_EVENT_CHANNEL,
    RuntimeEvent,
    TransactionCommittedEvent,
    TransactionRolledBackEvent,
)
from core.runtime.runtime_journal import RuntimeJournal
from core.runtime.runtime_status import (
    canonical_runtime_status_payload,
    status_from_transaction_state,
)
from core.runtime.runtime_status_transition import runtime_status_transition_payload


OPEN_STATUSES = {"created", "active", "rollback_required"}
CLOSED_STATUSES = {"committed", "rolled_back", "sealed", "failed"}


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _merge_metadata(base: dict[str, Any] | None, extra: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base or {})
    if extra:
        merged.update(dict(extra))
    return merged


def _append_unique(values: tuple[str, ...], value: str) -> tuple[str, ...]:
    cleaned = _clean_text(value)
    if not cleaned:
        return values
    if cleaned in values:
        return values
    return (*values, cleaned)


def _normalize_execution_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(metadata or {})
    if any(
        key in data
        for key in (
            "authority_source",
            "authority_scope",
            "authority_status",
            "authority_reason",
            "ownership_source",
            "ownership_scope",
            "authority_seal",
            "runtime_authority",
        )
    ):
        data["authority_seal"] = build_authority_metadata(data)

    for key in ("runtime_execution_result", "execution_result"):
        if isinstance(data.get(key), dict):
            data[key] = normalize_runtime_execution_fields(
                data[key],
                metadata=data[key].get("metadata"),
                evidence=data[key].get("evidence"),
            )

    if any(
        key in data
        for key in (
            "ok",
            "executed",
            "blocked",
            "failed",
            "verification",
            "verification_passed",
            "changed_files",
            "impacted_files",
            "target_path",
            "target_paths",
            "operations",
            "mutations",
        )
    ):
        return _attach_consistency_metadata(
            normalize_runtime_execution_fields(
                data,
                metadata=data.get("metadata"),
                evidence=data.get("evidence"),
            )
        )

    if any(key in data for key in ("status", "phase", "state", "result")):
        return _attach_consistency_metadata(canonical_runtime_status_payload(data))

    return _attach_consistency_metadata(data)


def _attach_consistency_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    data = dict(metadata or {})
    if any(
        key in data
        for key in (
            "lifecycle_status",
            "lifecycle_state",
            "execution_status",
            "execution_evidence",
            "transaction_status",
            "transaction_boundary",
            "authority_status",
            "authority_seal",
            "ownership_source",
            "runtime_consistency",
        )
    ):
        data["consistency_seal"] = build_runtime_state_consistency(data)
    return data


def _transaction_transition_flags(
    from_status: Any,
    to_status: Any,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    transition = runtime_status_transition_payload(
        status_from_transaction_state(from_status),
        status_from_transaction_state(to_status),
        source="runtime_transaction_coordinator",
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


@dataclass(frozen=True)
class RuntimeTransactionScope:
    transaction_id: str
    parent_transaction_id: str = ""
    lineage: dict[str, Any] = field(default_factory=dict)
    authority_metadata: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    status: str = "created"
    started_at: str = field(default_factory=utc_timestamp)
    finished_at: str = ""
    execution_ids: tuple[str, ...] = ()
    mutation_transaction_ids: tuple[str, ...] = ()
    state_ids: tuple[str, ...] = ()
    snapshot_ids: tuple[str, ...] = ()
    replay_ids: tuple[str, ...] = ()
    side_effect_ids: tuple[str, ...] = ()
    rollback_required: bool = False
    verified: bool = False
    sealed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        transaction_id = _clean_text(self.transaction_id)
        if not transaction_id:
            raise ValueError("transaction_id is required")
        object.__setattr__(self, "transaction_id", transaction_id)
        object.__setattr__(self, "parent_transaction_id", _clean_text(self.parent_transaction_id))
        normalized_status = _clean_text(self.status).lower() or "created"
        if normalized_status not in OPEN_STATUSES | CLOSED_STATUSES:
            raise ValueError(f"unsupported transaction status: {self.status}")
        object.__setattr__(self, "status", normalized_status)

    @property
    def is_closed(self) -> bool:
        return self.status in CLOSED_STATUSES or self.sealed

    def to_metadata(self) -> dict[str, Any]:
        closure = build_runtime_closure_fields(
            {
                **self.metadata,
                "transaction_status": self.status,
                "finished_at": self.finished_at,
                "source": "runtime_transaction_coordinator",
            },
            artifact_type="transaction",
            artifact_id=self.transaction_id,
            closure_reason=self.metadata.get("closure_reason") or self.metadata.get("last_action"),
            finalized_by="runtime_transaction_coordinator",
        )
        transition = _transaction_transition_flags(
            self.metadata.get("previous_status", "unknown"),
            self.status,
            self.metadata,
        )
        normalized_metadata = _normalize_execution_metadata(self.metadata)
        recovery = build_runtime_recovery_readiness_fields(
            {
                **normalized_metadata,
                **self.metadata,
                "transaction_boundary": {
                    "transaction_id": self.transaction_id,
                    "transaction_status": self.status,
                    "transaction_legality": "legal",
                },
                "authority_seal": self.authority_metadata,
                "runtime_closure": closure,
                "closure_evidence": closure.get("closure_evidence"),
            },
            artifact_type="transaction",
            artifact_id=self.transaction_id,
        )
        return {
            "transaction_id": self.transaction_id,
            "parent_transaction_id": self.parent_transaction_id,
            "status": self.status,
            "canonical_status": status_from_transaction_state(self.status),
            **transition,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "rollback_required": self.rollback_required,
            "verified": self.verified,
            "sealed": self.sealed,
            **closure,
            **recovery,
            "lineage": dict(self.lineage),
            "authority": dict(self.authority_metadata),
            "provenance": dict(self.provenance),
            "execution_ids": list(self.execution_ids),
            "mutation_transaction_ids": list(self.mutation_transaction_ids),
            "state_ids": list(self.state_ids),
            "snapshot_ids": list(self.snapshot_ids),
            "replay_ids": list(self.replay_ids),
            "side_effect_ids": list(self.side_effect_ids),
            "metadata": {**normalized_metadata, **recovery},
        }


@dataclass(frozen=True)
class RuntimeTransactionSnapshot:
    transaction_id: str
    files: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def __post_init__(self) -> None:
        if not _clean_text(self.transaction_id):
            raise ValueError("transaction_id is required")
        object.__setattr__(self, "transaction_id", _clean_text(self.transaction_id))

    def to_metadata(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "canonical_status": status_from_transaction_state(self.metadata.get("status", "created")),
            "files": [dict(item) for item in self.files],
            "metadata": _normalize_execution_metadata(self.metadata),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RuntimeTransactionResult:
    scope: RuntimeTransactionScope
    status: str
    committed: bool = False
    rolled_back: bool = False
    sealed: bool = False
    verified: bool = False
    rollback_required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in {"active", "committed", "sealed", "rolled_back"}

    def to_metadata(self) -> dict[str, Any]:
        closure = build_runtime_closure_fields(
            {
                **self.metadata,
                "transaction_status": self.status,
                "source": "runtime_transaction_coordinator",
            },
            artifact_type="transaction",
            artifact_id=self.scope.transaction_id,
            finalized_by="runtime_transaction_coordinator",
        )
        transition = _transaction_transition_flags(
            self.metadata.get("previous_status", self.scope.metadata.get("previous_status", "unknown")),
            self.status,
            self.metadata,
        )
        normalized_metadata = _normalize_execution_metadata(self.metadata)
        recovery = build_runtime_recovery_readiness_fields(
            {
                **normalized_metadata,
                **self.metadata,
                "transaction_boundary": {
                    "transaction_id": self.scope.transaction_id,
                    "transaction_status": self.status,
                    "transaction_legality": "legal",
                },
                "authority_seal": self.scope.authority_metadata,
                "runtime_closure": closure,
                "closure_evidence": closure.get("closure_evidence"),
            },
            artifact_type="transaction",
            artifact_id=self.scope.transaction_id,
        )
        return {
            "transaction": self.scope.to_metadata(),
            "status": self.status,
            "canonical_status": status_from_transaction_state(self.status),
            **transition,
            "committed": self.committed,
            "rolled_back": self.rolled_back,
            "sealed": self.sealed,
            "verified": self.verified,
            "rollback_required": self.rollback_required,
            **closure,
            **recovery,
            "metadata": {**normalized_metadata, **recovery},
        }


class RuntimeTransactionCoordinator:
    """In-memory runtime transaction coordinator.

    The coordinator is deliberately small and deterministic. Persistence should
    be provided by the governed runtime persistence/state layers, not by this
    coordinator.
    """

    def __init__(
        self,
        *,
        event_bus: RuntimeEventBus | None = None,
        journal: RuntimeJournal | None = None,
    ) -> None:
        self._scopes: dict[str, RuntimeTransactionScope] = {}
        self._snapshots: dict[str, RuntimeTransactionSnapshot] = {}
        self.event_bus = event_bus
        self.journal = journal

    def begin_transaction(
        self,
        *,
        transaction_id: str,
        parent_transaction_id: str = "",
        lineage: dict[str, Any] | None = None,
        authority_metadata: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTransactionResult:
        cleaned_id = _clean_text(transaction_id)
        if not cleaned_id:
            raise ValueError("transaction_id is required")
        if cleaned_id in self._scopes:
            raise ValueError(f"transaction already exists: {cleaned_id}")

        parent_id = _clean_text(parent_transaction_id)
        if parent_id and parent_id not in self._scopes:
            raise ValueError(f"parent transaction does not exist: {parent_id}")

        scope = RuntimeTransactionScope(
            transaction_id=cleaned_id,
            parent_transaction_id=parent_id,
            lineage=dict(lineage or {}),
            authority_metadata=dict(authority_metadata or {}),
            provenance=dict(provenance or {}),
            status="active",
            metadata=dict(metadata or {}),
        )
        if self.journal is not None:
            self.journal.append_transaction_boundary(
                "begin",
                scope.transaction_id,
                metadata={"phase": "append_before_apply"},
            )
        self._scopes[scope.transaction_id] = scope
        return self._result(scope, metadata={"action": "begin_transaction"})

    def capture_snapshot(
        self,
        transaction_id: str,
        *,
        files: tuple[dict[str, Any], ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTransactionSnapshot:
        scope = self._require_open(transaction_id)
        snapshot = RuntimeTransactionSnapshot(
            transaction_id=scope.transaction_id,
            files=files,
            metadata=dict(metadata or {}),
        )
        if self.journal is not None:
            self.journal.append(
                "transaction_snapshot",
                payload=snapshot.to_metadata(),
                metadata={"phase": "append_before_apply"},
            )
        self._snapshots[scope.transaction_id] = snapshot
        return snapshot

    def get_snapshot(self, transaction_id: str) -> RuntimeTransactionSnapshot:
        cleaned_id = _clean_text(transaction_id)
        if cleaned_id not in self._snapshots:
            raise KeyError(f"unknown transaction snapshot: {cleaned_id}")
        return self._snapshots[cleaned_id]

    def get_scope(self, transaction_id: str) -> RuntimeTransactionScope:
        cleaned_id = _clean_text(transaction_id)
        if cleaned_id not in self._scopes:
            raise KeyError(f"unknown transaction: {cleaned_id}")
        return self._scopes[cleaned_id]

    def bind_execution(
        self,
        transaction_id: str,
        execution_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTransactionResult:
        return self._bind_id(transaction_id, "execution_ids", execution_id, "bind_execution", metadata)

    def bind_mutation(
        self,
        transaction_id: str,
        mutation_transaction_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTransactionResult:
        return self._bind_id(
            transaction_id,
            "mutation_transaction_ids",
            mutation_transaction_id,
            "bind_mutation",
            metadata,
        )

    def bind_state(
        self,
        transaction_id: str,
        state_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTransactionResult:
        return self._bind_id(transaction_id, "state_ids", state_id, "bind_state", metadata)

    def bind_snapshot(
        self,
        transaction_id: str,
        snapshot_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTransactionResult:
        return self._bind_id(transaction_id, "snapshot_ids", snapshot_id, "bind_snapshot", metadata)

    def bind_replay(
        self,
        transaction_id: str,
        replay_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTransactionResult:
        return self._bind_id(transaction_id, "replay_ids", replay_id, "bind_replay", metadata)

    def bind_side_effect(
        self,
        transaction_id: str,
        side_effect_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTransactionResult:
        return self._bind_id(transaction_id, "side_effect_ids", side_effect_id, "bind_side_effect", metadata)

    def mark_verified(
        self,
        transaction_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTransactionResult:
        scope = self._require_open(transaction_id)
        updated = replace(
            scope,
            verified=True,
            metadata=_merge_metadata(
                scope.metadata,
                {
                    "last_action": "mark_verified",
                    "previous_status": scope.status,
                    **dict(metadata or {}),
                },
            ),
        )
        self._scopes[updated.transaction_id] = updated
        return self._result(updated, metadata={"action": "mark_verified", **dict(metadata or {})})

    def mark_rollback_required(
        self,
        transaction_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTransactionResult:
        scope = self._require_open(transaction_id)
        updated = replace(
            scope,
            status="rollback_required",
            rollback_required=True,
            metadata=_merge_metadata(
                scope.metadata,
                {
                    "last_action": "mark_rollback_required",
                    "previous_status": scope.status,
                    **dict(metadata or {}),
                },
            ),
        )
        self._scopes[updated.transaction_id] = updated
        return self._result(updated, metadata={"action": "mark_rollback_required", **dict(metadata or {})})

    def commit(
        self,
        transaction_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTransactionResult:
        scope = self._require_open(transaction_id)
        if scope.rollback_required:
            raise RuntimeError(f"cannot commit rollback-required transaction: {transaction_id}")
        if self.journal is not None:
            self.journal.append_transaction_boundary(
                "commit",
                transaction_id,
                metadata={"phase": "append_before_commit", **dict(metadata or {})},
            )
        updated = replace(
            scope,
            status="committed",
            finished_at=utc_timestamp(),
            metadata=_merge_metadata(
                scope.metadata,
                {
                    "last_action": "commit",
                    "previous_status": scope.status,
                    **dict(metadata or {}),
                },
            ),
        )
        self._scopes[updated.transaction_id] = updated
        self._emit(TransactionCommittedEvent(transaction_id=updated.transaction_id, metadata=dict(metadata or {})))
        return self._result(
            updated,
            committed=True,
            metadata={"action": "commit", **dict(metadata or {})},
        )

    def rollback(
        self,
        transaction_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTransactionResult:
        scope = self._require_not_sealed(transaction_id)
        if scope.status == "committed":
            raise RuntimeError(f"cannot rollback committed transaction: {transaction_id}")
        if self.journal is not None:
            self.journal.append_transaction_boundary(
                "rollback",
                transaction_id,
                metadata={"phase": "append_before_rollback", **dict(metadata or {})},
            )
        updated = replace(
            scope,
            status="rolled_back",
            finished_at=utc_timestamp(),
            rollback_required=False,
            metadata=_merge_metadata(
                scope.metadata,
                {
                    "last_action": "rollback",
                    "previous_status": scope.status,
                    **dict(metadata or {}),
                },
            ),
        )
        self._scopes[updated.transaction_id] = updated
        self._emit(TransactionRolledBackEvent(transaction_id=updated.transaction_id, metadata=dict(metadata or {})))
        return self._result(
            updated,
            rolled_back=True,
            metadata={"action": "rollback", **dict(metadata or {})},
        )

    def seal(
        self,
        transaction_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTransactionResult:
        scope = self.get_scope(transaction_id)
        if scope.sealed:
            duplicate_closure = build_runtime_closure_fields(
                {
                    **scope.metadata,
                    **dict(metadata or {}),
                    "transaction_status": scope.status,
                    "runtime_closure": scope.to_metadata(),
                },
                artifact_type="transaction",
                artifact_id=scope.transaction_id,
                closure_status="sealed",
                closure_reason="duplicate_transaction_closure",
                finalized_by="runtime_transaction_coordinator",
            )
            updated = replace(
                scope,
                metadata=_merge_metadata(
                    scope.metadata,
                    {
                        "last_action": "seal_already_sealed",
                        "closure_evidence": duplicate_closure["closure_evidence"],
                        "runtime_closure": duplicate_closure,
                        **dict(metadata or {}),
                    },
                ),
            )
            self._scopes[updated.transaction_id] = updated
            return self._result(
                updated,
                sealed=True,
                committed=updated.status == "committed",
                rolled_back=updated.status == "rolled_back",
                metadata={"action": "seal_already_sealed", **dict(metadata or {})},
            )
        updated = replace(
            scope,
            status="sealed",
            sealed=True,
            finished_at=scope.finished_at or utc_timestamp(),
            metadata=_merge_metadata(
                scope.metadata,
                {
                    "last_action": "seal",
                    "previous_status": scope.status,
                    **dict(metadata or {}),
                },
            ),
        )
        self._scopes[updated.transaction_id] = updated
        return self._result(
            updated,
            sealed=True,
            committed=scope.status == "committed",
            rolled_back=scope.status == "rolled_back",
            metadata={"action": "seal", **dict(metadata or {})},
        )

    def _bind_id(
        self,
        transaction_id: str,
        field_name: str,
        value: str,
        action: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTransactionResult:
        scope = self._require_open(transaction_id)
        current_values = getattr(scope, field_name)
        updated_values = _append_unique(current_values, value)
        updated = replace(
            scope,
            **{
                field_name: updated_values,
                "metadata": _merge_metadata(
                    scope.metadata,
                    {
                        "last_action": action,
                        "previous_status": scope.status,
                        **dict(metadata or {}),
                    },
                ),
            },
        )
        self._scopes[updated.transaction_id] = updated
        return self._result(updated, metadata={"action": action, **dict(metadata or {})})

    def _require_open(self, transaction_id: str) -> RuntimeTransactionScope:
        scope = self.get_scope(transaction_id)
        if scope.is_closed:
            closure = build_runtime_closure_fields(
                {
                    **scope.metadata,
                    "transaction_status": scope.status,
                    "reopen_attempt": True,
                    "requested_status": "open",
                    "source": "runtime_transaction_coordinator",
                },
                artifact_type="transaction",
                artifact_id=scope.transaction_id,
                closure_reason="committed_transaction_cannot_reopen",
                finalized_by="runtime_transaction_coordinator",
            )
            updated = replace(
                scope,
                metadata=_merge_metadata(
                    scope.metadata,
                    {
                        "last_action": "closed_transaction_reopen_rejected",
                        "closure_evidence": closure["closure_evidence"],
                        "runtime_closure": closure,
                    },
                ),
            )
            self._scopes[updated.transaction_id] = updated
            raise RuntimeError(f"transaction is closed: {transaction_id}")
        return scope

    def _require_not_sealed(self, transaction_id: str) -> RuntimeTransactionScope:
        scope = self.get_scope(transaction_id)
        if scope.sealed:
            raise RuntimeError(f"transaction is sealed: {transaction_id}")
        return scope

    def _result(
        self,
        scope: RuntimeTransactionScope,
        *,
        committed: bool = False,
        rolled_back: bool = False,
        sealed: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTransactionResult:
        return RuntimeTransactionResult(
            scope=scope,
            status=scope.status,
            committed=committed or scope.status == "committed",
            rolled_back=rolled_back or scope.status == "rolled_back",
            sealed=sealed or scope.sealed,
            verified=scope.verified,
            rollback_required=scope.rollback_required,
            metadata=_normalize_execution_metadata(metadata),
        )

    def _emit(self, event: RuntimeEvent) -> None:
        if self.journal is not None:
            self.journal.append_event(event, phase="after_transaction_boundary")
        if self.event_bus is not None:
            self.event_bus.publish_event(event, channel=RUNTIME_EVENT_CHANNEL)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "runtime_version": RUNTIME_KERNEL_VERSION,
            "abi_version": RUNTIME_ABI_VERSION,
            "artifact_type": "runtime_transaction_coordinator",
            "canonical_status": status_from_transaction_state("active"),
            "transactions": [
                scope.to_metadata()
                for _, scope in sorted(self._scopes.items())
            ],
            "snapshots": [
                snapshot.to_metadata()
                for _, snapshot in sorted(self._snapshots.items())
            ],
        }
        return attach_runtime_seal(payload, artifact_type="runtime_transaction_coordinator")

