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
from core.runtime.runtime_status import status_from_lifecycle_phase
from core.runtime.runtime_status_transition import runtime_status_transition_payload


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


def _with_canonical_status(metadata: dict[str, Any] | None, phase: str) -> dict[str, Any]:
    previous = dict(metadata or {}).get("from_status") or dict(metadata or {}).get("from_phase")
    transition = runtime_status_transition_payload(
        status_from_lifecycle_phase(previous),
        status_from_lifecycle_phase(phase),
        source="runtime_execution_lifecycle",
    )
    return {
        **dict(metadata or {}),
        "canonical_status": status_from_lifecycle_phase(phase),
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


def begin_execution_lifecycle(
    execution_id: str,
    *,
    lineage: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    lifecycle_id = execution_lifecycle_id(execution_id)
    merged_metadata = merge_current_transaction_metadata(
        _with_canonical_status(metadata, "created")
    )
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
        metadata=_with_canonical_status(
            {"source": "runtime_execution_lifecycle"},
            "active",
        ),
    )


def mark_execution_verifying(
    execution_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    mark_current_lifecycle_verifying(
        execution_lifecycle_id(execution_id),
        metadata=_with_canonical_status(metadata, "verifying"),
    )


def mark_execution_verified(
    execution_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    mark_current_lifecycle_verified(
        execution_lifecycle_id(execution_id),
        metadata=_with_canonical_status(metadata, "verified"),
    )


def commit_execution_lifecycle(
    execution_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    mark_current_lifecycle_committed(
        execution_lifecycle_id(execution_id),
        metadata=_with_canonical_status(metadata, "committed"),
    )


def seal_execution_lifecycle(
    execution_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    mark_current_lifecycle_sealed(
        execution_lifecycle_id(execution_id),
        metadata=_with_canonical_status(metadata, "sealed"),
    )


def fail_execution_lifecycle(
    execution_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    mark_current_lifecycle_failed(
        execution_lifecycle_id(execution_id),
        metadata=_with_canonical_status(metadata, "failed"),
    )


def require_execution_rollback(
    execution_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    mark_current_lifecycle_rollback_required(
        execution_lifecycle_id(execution_id),
        metadata=_with_canonical_status(metadata, "rollback_required"),
    )


def begin_execution_rollback(
    execution_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    mark_current_lifecycle_rolling_back(
        execution_lifecycle_id(execution_id),
        metadata=_with_canonical_status(metadata, "rolling_back"),
    )


def finish_execution_rollback(
    execution_id: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> None:
    mark_current_lifecycle_rolled_back(
        execution_lifecycle_id(execution_id),
        metadata=_with_canonical_status(metadata, "rolled_back"),
    )
