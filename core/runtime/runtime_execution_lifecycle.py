"""Runtime execution lifecycle integration helpers.

This module integrates execution runtime flows with the shared lifecycle fabric.
It does not execute commands directly. It only coordinates lifecycle state
creation and transitions for execution artifacts.
"""

from __future__ import annotations

from typing import Any

from core.runtime.runtime_lifecycle_context import (
    create_current_lifecycle_record,
    lifecycle_id_for_artifact,
    mark_current_lifecycle_active,
    mark_current_lifecycle_committed,
    mark_current_lifecycle_failed,
    mark_current_lifecycle_rollback_required,
    mark_current_lifecycle_rolled_back,
    mark_current_lifecycle_rolling_back,
    mark_current_lifecycle_sealed,
    mark_current_lifecycle_verified,
    mark_current_lifecycle_verifying,
)
from core.runtime.runtime_transaction_context import (
    bind_current_execution,
    merge_current_transaction_metadata,
)


def execution_lifecycle_id(execution_id: str) -> str:
    return lifecycle_id_for_artifact("execution", execution_id)


def _merged_lineage(
    lineage: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = merge_current_transaction_metadata({"lineage": dict(lineage or {}), **dict(metadata or {})})
    value = merged.get("lineage")
    return dict(value) if isinstance(value, dict) else dict(lineage or {})


def _merged_provenance(
    provenance: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = merge_current_transaction_metadata({"provenance": dict(provenance or {}), **dict(metadata or {})})
    value = merged.get("provenance")
    return dict(value) if isinstance(value, dict) else dict(provenance or {})


def begin_execution_lifecycle(
    execution_id: str,
    *,
    lineage: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    lifecycle_id = execution_lifecycle_id(execution_id)
    merged_metadata = merge_current_transaction_metadata(metadata)
    merged_lineage = _merged_lineage(lineage, metadata)
    merged_provenance = _merged_provenance(provenance, metadata)

    bind_current_execution(
        execution_id,
        metadata={"source": "runtime_execution_lifecycle"},
    )

    create_current_lifecycle_record(
        lifecycle_id=lifecycle_id,
        artifact_id=execution_id,
        artifact_type="execution",
        lineage=merged_lineage,
        provenance=merged_provenance,
        metadata=merged_metadata,
    )

    mark_current_lifecycle_active(
        lifecycle_id,
        metadata={"source": "runtime_execution_lifecycle"},
    )


def mark_execution_verifying(
    execution_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    mark_current_lifecycle_verifying(
        execution_lifecycle_id(execution_id),
        metadata=metadata,
    )


def mark_execution_verified(
    execution_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    mark_current_lifecycle_verified(
        execution_lifecycle_id(execution_id),
        metadata=metadata,
    )


def commit_execution_lifecycle(
    execution_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    mark_current_lifecycle_committed(
        execution_lifecycle_id(execution_id),
        metadata=metadata,
    )


def seal_execution_lifecycle(
    execution_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    mark_current_lifecycle_sealed(
        execution_lifecycle_id(execution_id),
        metadata=metadata,
    )


def fail_execution_lifecycle(
    execution_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    mark_current_lifecycle_failed(
        execution_lifecycle_id(execution_id),
        metadata=metadata,
    )


def require_execution_rollback(
    execution_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    mark_current_lifecycle_rollback_required(
        execution_lifecycle_id(execution_id),
        metadata=metadata,
    )


def begin_execution_rollback(
    execution_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    mark_current_lifecycle_rolling_back(
        execution_lifecycle_id(execution_id),
        metadata=metadata,
    )


def finish_execution_rollback(
    execution_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    mark_current_lifecycle_rolled_back(
        execution_lifecycle_id(execution_id),
        metadata=metadata,
    )
