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
        return {
            "transaction_id": self.transaction_id,
            "parent_transaction_id": self.parent_transaction_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "rollback_required": self.rollback_required,
            "verified": self.verified,
            "sealed": self.sealed,
            "lineage": dict(self.lineage),
            "authority": dict(self.authority_metadata),
            "provenance": dict(self.provenance),
            "execution_ids": list(self.execution_ids),
            "mutation_transaction_ids": list(self.mutation_transaction_ids),
            "state_ids": list(self.state_ids),
            "snapshot_ids": list(self.snapshot_ids),
            "replay_ids": list(self.replay_ids),
            "side_effect_ids": list(self.side_effect_ids),
            "metadata": dict(self.metadata),
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
        return {
            "transaction": self.scope.to_metadata(),
            "status": self.status,
            "committed": self.committed,
            "rolled_back": self.rolled_back,
            "sealed": self.sealed,
            "verified": self.verified,
            "rollback_required": self.rollback_required,
            "metadata": dict(self.metadata),
        }


class RuntimeTransactionCoordinator:
    """In-memory runtime transaction coordinator.

    The coordinator is deliberately small and deterministic. Persistence should
    be provided by the governed runtime persistence/state layers, not by this
    coordinator.
    """

    def __init__(self) -> None:
        self._scopes: dict[str, RuntimeTransactionScope] = {}

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
        self._scopes[scope.transaction_id] = scope
        return self._result(scope, metadata={"action": "begin_transaction"})

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
            metadata=_merge_metadata(scope.metadata, {"last_action": "mark_verified", **dict(metadata or {})}),
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
            metadata=_merge_metadata(scope.metadata, {"last_action": "mark_rollback_required", **dict(metadata or {})}),
        )
        self._scopes[updated.transaction_id] = updated
        return self._result(updated, metadata={"action": "mark_rollback_required", **dict(metadata or {})})

    def commit(
        self,
        transaction_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimeTransactionResult:
        scope = self._require_open(transaction_id)
        updated = replace(
            scope,
            status="committed",
            finished_at=utc_timestamp(),
            metadata=_merge_metadata(scope.metadata, {"last_action": "commit", **dict(metadata or {})}),
        )
        self._scopes[updated.transaction_id] = updated
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
        updated = replace(
            scope,
            status="rolled_back",
            finished_at=utc_timestamp(),
            rollback_required=False,
            metadata=_merge_metadata(scope.metadata, {"last_action": "rollback", **dict(metadata or {})}),
        )
        self._scopes[updated.transaction_id] = updated
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
            return self._result(
                scope,
                sealed=True,
                committed=scope.status == "committed",
                rolled_back=scope.status == "rolled_back",
                metadata={"action": "seal_already_sealed", **dict(metadata or {})},
            )
        updated = replace(
            scope,
            status="sealed",
            sealed=True,
            finished_at=scope.finished_at or utc_timestamp(),
            metadata=_merge_metadata(scope.metadata, {"last_action": "seal", **dict(metadata or {})}),
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
                "metadata": _merge_metadata(scope.metadata, {"last_action": action, **dict(metadata or {})}),
            },
        )
        self._scopes[updated.transaction_id] = updated
        return self._result(updated, metadata={"action": action, **dict(metadata or {})})

    def _require_open(self, transaction_id: str) -> RuntimeTransactionScope:
        scope = self.get_scope(transaction_id)
        if scope.is_closed:
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
            metadata=dict(metadata or {}),
        )
