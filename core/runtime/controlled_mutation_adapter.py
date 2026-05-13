from __future__ import annotations

import hashlib
import json
from typing import Any

from core.runtime.controlled_mutation_boundary import (
    ControlledMutationBoundary,
    ControlledMutationResult,
)


class ControlledMutationAdapterRejected(RuntimeError):
    pass


class ControlledMutationAdapter:
    def __init__(
        self,
        adapter_id: str,
        boundary: ControlledMutationBoundary,
    ) -> None:
        self.adapter_id = self._validate_text("adapter_id", adapter_id)
        if not isinstance(boundary, ControlledMutationBoundary):
            raise ControlledMutationAdapterRejected(
                "controlled mutation adapter requires ControlledMutationBoundary"
            )
        self.boundary = boundary

    def emit_planned(
        self,
        mutation_id: str,
        metadata: Any = None,
        runtime_args: Any = None,
        evidence_refs: Any = None,
        rollback_refs: Any = None,
    ) -> ControlledMutationResult:
        return self.boundary.plan_mutation(
            mutation_id=mutation_id,
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )

    def emit_applied(
        self,
        mutation_id: str,
        metadata: Any = None,
        runtime_args: Any = None,
        evidence_refs: Any = None,
        rollback_refs: Any = None,
    ) -> ControlledMutationResult:
        return self.boundary.record_apply(
            mutation_id=mutation_id,
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )

    def emit_verified(
        self,
        mutation_id: str,
        metadata: Any = None,
        runtime_args: Any = None,
        evidence_refs: Any = None,
        rollback_refs: Any = None,
    ) -> ControlledMutationResult:
        return self.boundary.record_verify(
            mutation_id=mutation_id,
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )

    def emit_rollback_plan(
        self,
        mutation_id: str,
        metadata: Any = None,
        runtime_args: Any = None,
        evidence_refs: Any = None,
        rollback_refs: Any = None,
    ) -> ControlledMutationResult:
        return self.boundary.record_rollback_plan(
            mutation_id=mutation_id,
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )

    def emit_rolled_back(
        self,
        mutation_id: str,
        metadata: Any = None,
        runtime_args: Any = None,
        evidence_refs: Any = None,
        rollback_refs: Any = None,
    ) -> ControlledMutationResult:
        return self.boundary.record_rollback(
            mutation_id=mutation_id,
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )

    def emit_failed(
        self,
        mutation_id: str,
        error: Any,
        metadata: Any = None,
        runtime_args: Any = None,
        evidence_refs: Any = None,
        rollback_refs: Any = None,
    ) -> ControlledMutationResult:
        return self.boundary.record_failure(
            mutation_id=mutation_id,
            error=error,
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )

    def emit_blocked(
        self,
        mutation_id: str,
        reason: Any,
        metadata: Any = None,
        runtime_args: Any = None,
        evidence_refs: Any = None,
        rollback_refs: Any = None,
    ) -> ControlledMutationResult:
        return self.boundary.record_blocked(
            mutation_id=mutation_id,
            reason=reason,
            metadata=metadata,
            runtime_args=runtime_args,
            evidence_refs=evidence_refs,
            rollback_refs=rollback_refs,
        )

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            {
                "adapter_id": self.adapter_id,
                "boundary_fingerprint": self.boundary.fingerprint,
            },
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _validate_text(self, field_name: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ControlledMutationAdapterRejected(
                f"controlled mutation adapter {field_name} is required"
            )
        return value


__all__ = [
    "ControlledMutationAdapter",
    "ControlledMutationAdapterRejected",
]
