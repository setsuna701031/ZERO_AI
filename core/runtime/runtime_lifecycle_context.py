"""Runtime lifecycle context and binding helpers.

This module carries the current lifecycle coordinator across runtime layers.
It does not execute commands, mutate files, or persist state.

RuntimeLifecycleCoordinator owns lifecycle records/transitions.
This context module owns propagation and safe no-op binding helpers.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

from core.runtime.runtime_lifecycle_coordinator import (
    RuntimeLifecycleCoordinator,
    RuntimeLifecycleResult,
)
from core.runtime.runtime_transaction_context import (
    get_current_transaction,
    merge_current_transaction_metadata,
)


_CURRENT_LIFECYCLE_COORDINATOR: ContextVar[RuntimeLifecycleCoordinator | None] = ContextVar(
    "zero_runtime_lifecycle_coordinator",
    default=None,
)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def get_current_lifecycle_coordinator() -> RuntimeLifecycleCoordinator | None:
    return _CURRENT_LIFECYCLE_COORDINATOR.get()


def set_current_lifecycle_coordinator(
    coordinator: RuntimeLifecycleCoordinator | None,
) -> RuntimeLifecycleCoordinator | None:
    if coordinator is not None and not isinstance(coordinator, RuntimeLifecycleCoordinator):
        raise TypeError("coordinator must be RuntimeLifecycleCoordinator")
    previous = _CURRENT_LIFECYCLE_COORDINATOR.get()
    _CURRENT_LIFECYCLE_COORDINATOR.set(coordinator)
    return previous


def clear_current_lifecycle_coordinator() -> None:
    _CURRENT_LIFECYCLE_COORDINATOR.set(None)


@contextmanager
def lifecycle_context(
    coordinator: RuntimeLifecycleCoordinator,
) -> Iterator[RuntimeLifecycleCoordinator]:
    if not isinstance(coordinator, RuntimeLifecycleCoordinator):
        raise TypeError("coordinator must be RuntimeLifecycleCoordinator")
    token = _CURRENT_LIFECYCLE_COORDINATOR.set(coordinator)
    try:
        yield coordinator
    finally:
        _CURRENT_LIFECYCLE_COORDINATOR.reset(token)


def _default_transaction_id() -> str:
    context = get_current_transaction()
    if context is None:
        return ""
    return context.transaction_id


def _default_lineage(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = merge_current_transaction_metadata(metadata)
    lineage = merged.get("lineage")
    return dict(lineage) if isinstance(lineage, dict) else {}


def _default_provenance(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = merge_current_transaction_metadata(metadata)
    provenance = merged.get("provenance")
    return dict(provenance) if isinstance(provenance, dict) else {}


def _default_authority(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = merge_current_transaction_metadata(metadata)
    runtime_transaction = merged.get("runtime_transaction")
    if isinstance(runtime_transaction, dict) and isinstance(runtime_transaction.get("authority"), dict):
        return dict(runtime_transaction["authority"])
    authority = merged.get("authority")
    return dict(authority) if isinstance(authority, dict) else {}


def create_current_lifecycle_record(
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
) -> RuntimeLifecycleResult | None:
    coordinator = get_current_lifecycle_coordinator()
    if coordinator is None:
        return None

    cleaned_lifecycle_id = _clean_text(lifecycle_id)
    cleaned_artifact_id = _clean_text(artifact_id)
    if not cleaned_lifecycle_id or not cleaned_artifact_id:
        return None

    merged_metadata = merge_current_transaction_metadata(metadata)
    try:
        return coordinator.create_record(
            lifecycle_id=cleaned_lifecycle_id,
            artifact_id=cleaned_artifact_id,
            artifact_type=artifact_type,
            transaction_id=_clean_text(transaction_id) or _default_transaction_id(),
            parent_lifecycle_id=parent_lifecycle_id,
            lineage=dict(lineage) if lineage is not None else _default_lineage(merged_metadata),
            authority_metadata=dict(authority_metadata)
            if authority_metadata is not None
            else _default_authority(merged_metadata),
            provenance=dict(provenance) if provenance is not None else _default_provenance(merged_metadata),
            metadata=merged_metadata,
        )
    except ValueError as exc:
        if "already exists" in str(exc):
            return None
        raise


def transition_current_lifecycle(
    lifecycle_id: str,
    to_state: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> RuntimeLifecycleResult | None:
    coordinator = get_current_lifecycle_coordinator()
    if coordinator is None:
        return None
    cleaned_lifecycle_id = _clean_text(lifecycle_id)
    if not cleaned_lifecycle_id:
        return None
    return coordinator.transition(
        cleaned_lifecycle_id,
        to_state,
        metadata=merge_current_transaction_metadata(metadata),
    )


def mark_current_lifecycle_active(
    lifecycle_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> RuntimeLifecycleResult | None:
    return transition_current_lifecycle(lifecycle_id, "active", metadata=metadata)


def mark_current_lifecycle_verifying(
    lifecycle_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> RuntimeLifecycleResult | None:
    return transition_current_lifecycle(lifecycle_id, "verifying", metadata=metadata)


def mark_current_lifecycle_verified(
    lifecycle_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> RuntimeLifecycleResult | None:
    return transition_current_lifecycle(lifecycle_id, "verified", metadata=metadata)


def mark_current_lifecycle_rollback_required(
    lifecycle_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> RuntimeLifecycleResult | None:
    return transition_current_lifecycle(lifecycle_id, "rollback_required", metadata=metadata)


def mark_current_lifecycle_rolling_back(
    lifecycle_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> RuntimeLifecycleResult | None:
    return transition_current_lifecycle(lifecycle_id, "rolling_back", metadata=metadata)


def mark_current_lifecycle_rolled_back(
    lifecycle_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> RuntimeLifecycleResult | None:
    return transition_current_lifecycle(lifecycle_id, "rolled_back", metadata=metadata)


def mark_current_lifecycle_committed(
    lifecycle_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> RuntimeLifecycleResult | None:
    return transition_current_lifecycle(lifecycle_id, "committed", metadata=metadata)


def mark_current_lifecycle_sealed(
    lifecycle_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> RuntimeLifecycleResult | None:
    return transition_current_lifecycle(lifecycle_id, "sealed", metadata=metadata)


def mark_current_lifecycle_failed(
    lifecycle_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> RuntimeLifecycleResult | None:
    return transition_current_lifecycle(lifecycle_id, "failed", metadata=metadata)


def lifecycle_id_for_artifact(artifact_type: str, artifact_id: str) -> str:
    return f"lifecycle:{_clean_text(artifact_type)}:{_clean_text(artifact_id)}"
