"""Runtime transaction context.

This module provides process-local transaction context propagation for the ZERO
runtime kernel. It does not execute commands, mutate files, or persist state.
It only carries the current transaction identity/metadata across runtime layers.

The coordinator owns lifecycle and binding. The context owns propagation.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

from core.runtime.runtime_transaction_coordinator import (
    RuntimeTransactionCoordinator,
    RuntimeTransactionResult,
    RuntimeTransactionScope,
)


_CURRENT_TRANSACTION: ContextVar["RuntimeTransactionContext | None"] = ContextVar(
    "zero_runtime_transaction_context",
    default=None,
)
_CURRENT_COORDINATOR: ContextVar[RuntimeTransactionCoordinator | None] = ContextVar(
    "zero_runtime_transaction_coordinator",
    default=None,
)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


@dataclass(frozen=True)
class RuntimeTransactionContext:
    transaction_id: str
    parent_transaction_id: str = ""
    lineage: dict[str, Any] = field(default_factory=dict)
    authority_metadata: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        transaction_id = _clean_text(self.transaction_id)
        if not transaction_id:
            raise ValueError("transaction_id is required")
        object.__setattr__(self, "transaction_id", transaction_id)
        object.__setattr__(self, "parent_transaction_id", _clean_text(self.parent_transaction_id))

    @classmethod
    def from_scope(cls, scope: RuntimeTransactionScope) -> "RuntimeTransactionContext":
        return cls(
            transaction_id=scope.transaction_id,
            parent_transaction_id=scope.parent_transaction_id,
            lineage=dict(scope.lineage),
            authority_metadata=dict(scope.authority_metadata),
            provenance=dict(scope.provenance),
            metadata=dict(scope.metadata),
        )

    def to_metadata(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "parent_transaction_id": self.parent_transaction_id,
            "lineage": dict(self.lineage),
            "authority": dict(self.authority_metadata),
            "provenance": dict(self.provenance),
            "metadata": dict(self.metadata),
        }


def get_current_transaction() -> RuntimeTransactionContext | None:
    return _CURRENT_TRANSACTION.get()


def get_current_transaction_coordinator() -> RuntimeTransactionCoordinator | None:
    return _CURRENT_COORDINATOR.get()


def require_current_transaction() -> RuntimeTransactionContext:
    context = get_current_transaction()
    if context is None:
        raise RuntimeError("runtime transaction context is required")
    return context


def set_current_transaction(
    context: RuntimeTransactionContext,
    coordinator: RuntimeTransactionCoordinator | None = None,
) -> RuntimeTransactionContext | None:
    if not isinstance(context, RuntimeTransactionContext):
        raise TypeError("context must be RuntimeTransactionContext")
    if coordinator is not None and not isinstance(coordinator, RuntimeTransactionCoordinator):
        raise TypeError("coordinator must be RuntimeTransactionCoordinator")
    previous = _CURRENT_TRANSACTION.get()
    _CURRENT_TRANSACTION.set(context)
    if coordinator is not None:
        _CURRENT_COORDINATOR.set(coordinator)
    return previous


def set_current_transaction_coordinator(
    coordinator: RuntimeTransactionCoordinator | None,
) -> RuntimeTransactionCoordinator | None:
    if coordinator is not None and not isinstance(coordinator, RuntimeTransactionCoordinator):
        raise TypeError("coordinator must be RuntimeTransactionCoordinator")
    previous = _CURRENT_COORDINATOR.get()
    _CURRENT_COORDINATOR.set(coordinator)
    return previous


def clear_current_transaction() -> None:
    _CURRENT_TRANSACTION.set(None)
    _CURRENT_COORDINATOR.set(None)


@contextmanager
def transaction_context(
    context: RuntimeTransactionContext,
    coordinator: RuntimeTransactionCoordinator | None = None,
) -> Iterator[RuntimeTransactionContext]:
    if not isinstance(context, RuntimeTransactionContext):
        raise TypeError("context must be RuntimeTransactionContext")
    if coordinator is not None and not isinstance(coordinator, RuntimeTransactionCoordinator):
        raise TypeError("coordinator must be RuntimeTransactionCoordinator")
    token = _CURRENT_TRANSACTION.set(context)
    coordinator_token = None
    if coordinator is not None:
        coordinator_token = _CURRENT_COORDINATOR.set(coordinator)
    try:
        yield context
    finally:
        _CURRENT_TRANSACTION.reset(token)
        if coordinator_token is not None:
            _CURRENT_COORDINATOR.reset(coordinator_token)


@contextmanager
def transaction_scope(
    coordinator: RuntimeTransactionCoordinator,
    *,
    transaction_id: str,
    parent_transaction_id: str = "",
    lineage: dict[str, Any] | None = None,
    authority_metadata: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    auto_commit: bool = False,
    auto_seal: bool = False,
    rollback_on_exception: bool = True,
) -> Iterator[RuntimeTransactionContext]:
    """Begin a coordinator-backed transaction and propagate it as current.

    By default this context manager only begins and propagates the transaction.
    Callers that want automatic lifecycle closure can set auto_commit and/or
    auto_seal. On exception, rollback is attempted unless rollback_on_exception
    is False.
    """

    if not isinstance(coordinator, RuntimeTransactionCoordinator):
        raise TypeError("coordinator must be RuntimeTransactionCoordinator")

    begin_result = coordinator.begin_transaction(
        transaction_id=transaction_id,
        parent_transaction_id=parent_transaction_id,
        lineage=lineage or {},
        authority_metadata=authority_metadata or {},
        provenance=provenance or {},
        metadata=metadata or {},
    )
    context = RuntimeTransactionContext.from_scope(begin_result.scope)
    token = _CURRENT_TRANSACTION.set(context)
    coordinator_token = _CURRENT_COORDINATOR.set(coordinator)
    try:
        yield context
    except Exception:
        if rollback_on_exception:
            try:
                coordinator.mark_rollback_required(
                    context.transaction_id,
                    metadata={"reason": "transaction_scope_exception"},
                )
                coordinator.rollback(
                    context.transaction_id,
                    metadata={"reason": "transaction_scope_exception"},
                )
            except Exception:
                pass
        raise
    else:
        if auto_commit:
            coordinator.commit(context.transaction_id, metadata={"source": "transaction_scope"})
        if auto_seal:
            coordinator.seal(context.transaction_id, metadata={"source": "transaction_scope"})
    finally:
        _CURRENT_TRANSACTION.reset(token)
        _CURRENT_COORDINATOR.reset(coordinator_token)


def current_transaction_metadata() -> dict[str, Any]:
    context = get_current_transaction()
    if context is None:
        return {}
    return context.to_metadata()


def merge_current_transaction_metadata(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(metadata or {})
    context = get_current_transaction()
    if context is not None:
        merged.setdefault("runtime_transaction", context.to_metadata())
        merged.setdefault("transaction_id", context.transaction_id)
        if context.parent_transaction_id:
            merged.setdefault("parent_transaction_id", context.parent_transaction_id)
        if context.lineage:
            existing_lineage = merged.get("lineage") if isinstance(merged.get("lineage"), dict) else {}
            merged["lineage"] = {**dict(context.lineage), **dict(existing_lineage)}
        if context.provenance:
            existing_provenance = merged.get("provenance") if isinstance(merged.get("provenance"), dict) else {}
            merged["provenance"] = {**dict(context.provenance), **dict(existing_provenance)}
    return merged


def attach_current_transaction_to_mapping(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    merged = dict(payload)
    return merge_current_transaction_metadata(merged)


class RuntimeTransactionBinder:
    """Convenience binder that links observed runtime ids to current transaction."""

    def __init__(self, coordinator: RuntimeTransactionCoordinator) -> None:
        if not isinstance(coordinator, RuntimeTransactionCoordinator):
            raise TypeError("coordinator must be RuntimeTransactionCoordinator")
        self.coordinator = coordinator

    def bind_execution(self, execution_id: str, metadata: dict[str, Any] | None = None) -> RuntimeTransactionResult | None:
        context = get_current_transaction()
        if context is None:
            return None
        return self.coordinator.bind_execution(context.transaction_id, execution_id, metadata=metadata)

    def bind_mutation(self, mutation_transaction_id: str, metadata: dict[str, Any] | None = None) -> RuntimeTransactionResult | None:
        context = get_current_transaction()
        if context is None:
            return None
        return self.coordinator.bind_mutation(context.transaction_id, mutation_transaction_id, metadata=metadata)

    def bind_state(self, state_id: str, metadata: dict[str, Any] | None = None) -> RuntimeTransactionResult | None:
        context = get_current_transaction()
        if context is None:
            return None
        return self.coordinator.bind_state(context.transaction_id, state_id, metadata=metadata)

    def bind_snapshot(self, snapshot_id: str, metadata: dict[str, Any] | None = None) -> RuntimeTransactionResult | None:
        context = get_current_transaction()
        if context is None:
            return None
        return self.coordinator.bind_snapshot(context.transaction_id, snapshot_id, metadata=metadata)

    def bind_replay(self, replay_id: str, metadata: dict[str, Any] | None = None) -> RuntimeTransactionResult | None:
        context = get_current_transaction()
        if context is None:
            return None
        return self.coordinator.bind_replay(context.transaction_id, replay_id, metadata=metadata)

    def bind_side_effect(self, side_effect_id: str, metadata: dict[str, Any] | None = None) -> RuntimeTransactionResult | None:
        context = get_current_transaction()
        if context is None:
            return None
        return self.coordinator.bind_side_effect(context.transaction_id, side_effect_id, metadata=metadata)


def _bind_with_current_coordinator(
    binder_name: str,
    artifact_id: str,
    metadata: dict[str, Any] | None = None,
) -> RuntimeTransactionResult | None:
    artifact_id = _clean_text(artifact_id)
    if not artifact_id:
        return None
    coordinator = get_current_transaction_coordinator()
    context = get_current_transaction()
    if coordinator is None or context is None:
        return None
    binder = RuntimeTransactionBinder(coordinator)
    method = getattr(binder, binder_name)
    return method(artifact_id, metadata=metadata)


def bind_current_execution(
    execution_id: str,
    metadata: dict[str, Any] | None = None,
) -> RuntimeTransactionResult | None:
    return _bind_with_current_coordinator("bind_execution", execution_id, metadata)


def bind_current_mutation(
    mutation_transaction_id: str,
    metadata: dict[str, Any] | None = None,
) -> RuntimeTransactionResult | None:
    return _bind_with_current_coordinator("bind_mutation", mutation_transaction_id, metadata)


def bind_current_state(
    state_id: str,
    metadata: dict[str, Any] | None = None,
) -> RuntimeTransactionResult | None:
    return _bind_with_current_coordinator("bind_state", state_id, metadata)


def bind_current_snapshot(
    snapshot_id: str,
    metadata: dict[str, Any] | None = None,
) -> RuntimeTransactionResult | None:
    return _bind_with_current_coordinator("bind_snapshot", snapshot_id, metadata)


def bind_current_replay(
    replay_id: str,
    metadata: dict[str, Any] | None = None,
) -> RuntimeTransactionResult | None:
    return _bind_with_current_coordinator("bind_replay", replay_id, metadata)


def bind_current_side_effect(
    side_effect_id: str,
    metadata: dict[str, Any] | None = None,
) -> RuntimeTransactionResult | None:
    return _bind_with_current_coordinator("bind_side_effect", side_effect_id, metadata)
