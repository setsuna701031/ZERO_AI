from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class ControlledMutationRollbackRejected(RuntimeError):
    pass


class ControlledMutationRollbackRecord:
    ALLOWED_PHASES = {
        "planned",
        "started",
        "completed",
        "failed",
        "blocked",
    }

    def __init__(
        self,
        record_id: str,
        boundary_id: str,
        rollback_id: str,
        sandbox_id: str,
        mutation_id: str,
        rollback_phase: str,
        sequence: int,
        rollback_strategy: Any = None,
        rollback_summary: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
        created_at: str | None = None,
    ) -> None:
        self._record_id = self._validate_text("record_id", record_id)
        self._boundary_id = self._validate_text("boundary_id", boundary_id)
        self._rollback_id = self._validate_text("rollback_id", rollback_id)
        self._sandbox_id = self._validate_text("sandbox_id", sandbox_id)
        self._mutation_id = self._validate_text("mutation_id", mutation_id)
        self._rollback_phase = self._validate_phase(rollback_phase)
        self._sequence = self._validate_sequence(sequence)
        self._rollback_strategy = copy.deepcopy(rollback_strategy)
        self._rollback_summary = copy.deepcopy(rollback_summary)
        self._evidence_refs = copy.deepcopy(evidence_refs)
        self._metadata = copy.deepcopy(metadata)
        self._runtime_args = copy.deepcopy(runtime_args)
        self._created_at = (
            created_at
            if created_at is not None
            else datetime.now(timezone.utc).isoformat()
        )

    @property
    def record_id(self) -> str:
        return self._record_id

    @property
    def boundary_id(self) -> str:
        return self._boundary_id

    @property
    def rollback_id(self) -> str:
        return self._rollback_id

    @property
    def sandbox_id(self) -> str:
        return self._sandbox_id

    @property
    def mutation_id(self) -> str:
        return self._mutation_id

    @property
    def rollback_phase(self) -> str:
        return self._rollback_phase

    @property
    def rollback_strategy(self) -> Any:
        return copy.deepcopy(self._rollback_strategy)

    @property
    def rollback_summary(self) -> Any:
        return copy.deepcopy(self._rollback_summary)

    @property
    def evidence_refs(self) -> Any:
        return copy.deepcopy(self._evidence_refs)

    @property
    def metadata(self) -> Any:
        return copy.deepcopy(self._metadata)

    @property
    def runtime_args(self) -> Any:
        return copy.deepcopy(self._runtime_args)

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def created_at(self) -> str:
        return self._created_at

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self._fingerprint_payload(),
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _fingerprint_payload(self) -> dict[str, Any]:
        return {
            "record_id": self._record_id,
            "boundary_id": self._boundary_id,
            "rollback_id": self._rollback_id,
            "sandbox_id": self._sandbox_id,
            "mutation_id": self._mutation_id,
            "rollback_phase": self._rollback_phase,
            "rollback_strategy": self._rollback_strategy,
            "rollback_summary": self._rollback_summary,
            "evidence_refs": self._evidence_refs,
            "metadata": self._metadata,
            "runtime_args": self._runtime_args,
            "sequence": self._sequence,
        }

    def _validate_text(self, field_name: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ControlledMutationRollbackRejected(
                f"controlled mutation rollback {field_name} is required"
            )
        return value

    def _validate_phase(self, phase: str) -> str:
        phase = self._validate_text("rollback_phase", phase)
        if phase not in self.ALLOWED_PHASES:
            raise ControlledMutationRollbackRejected(
                f"controlled mutation rollback phase is unsupported: {phase}"
            )
        return phase

    def _validate_sequence(self, sequence: int) -> int:
        if not isinstance(sequence, int) or sequence < 1:
            raise ControlledMutationRollbackRejected(
                "controlled mutation rollback sequence must be positive"
            )
        return sequence


class ControlledMutationRollbackBoundary:
    def __init__(self, boundary_id: str) -> None:
        self.boundary_id = self._validate_text("boundary_id", boundary_id)
        self._sequence = 0
        self._records: list[ControlledMutationRollbackRecord] = []

    def record_rollback_planned(
        self,
        rollback_id: str,
        sandbox_id: str,
        mutation_id: str,
        rollback_strategy: Any = None,
        rollback_summary: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationRollbackRecord:
        return self._record(
            rollback_phase="planned",
            rollback_id=rollback_id,
            sandbox_id=sandbox_id,
            mutation_id=mutation_id,
            rollback_strategy=rollback_strategy,
            rollback_summary=rollback_summary,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def record_rollback_started(
        self,
        rollback_id: str,
        sandbox_id: str,
        mutation_id: str,
        rollback_strategy: Any = None,
        rollback_summary: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationRollbackRecord:
        return self._record(
            rollback_phase="started",
            rollback_id=rollback_id,
            sandbox_id=sandbox_id,
            mutation_id=mutation_id,
            rollback_strategy=rollback_strategy,
            rollback_summary=rollback_summary,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def record_rollback_completed(
        self,
        rollback_id: str,
        sandbox_id: str,
        mutation_id: str,
        rollback_summary: Any,
        rollback_strategy: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationRollbackRecord:
        return self._record(
            rollback_phase="completed",
            rollback_id=rollback_id,
            sandbox_id=sandbox_id,
            mutation_id=mutation_id,
            rollback_strategy=rollback_strategy,
            rollback_summary=rollback_summary,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def record_rollback_failed(
        self,
        rollback_id: str,
        sandbox_id: str,
        mutation_id: str,
        rollback_summary: Any,
        rollback_strategy: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationRollbackRecord:
        return self._record(
            rollback_phase="failed",
            rollback_id=rollback_id,
            sandbox_id=sandbox_id,
            mutation_id=mutation_id,
            rollback_strategy=rollback_strategy,
            rollback_summary=rollback_summary,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def record_rollback_blocked(
        self,
        rollback_id: str,
        sandbox_id: str,
        mutation_id: str,
        rollback_summary: Any,
        rollback_strategy: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationRollbackRecord:
        return self._record(
            rollback_phase="blocked",
            rollback_id=rollback_id,
            sandbox_id=sandbox_id,
            mutation_id=mutation_id,
            rollback_strategy=rollback_strategy,
            rollback_summary=rollback_summary,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def list_records(self) -> list[ControlledMutationRollbackRecord]:
        return copy.deepcopy(self._records)

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            {
                "boundary_id": self.boundary_id,
                "record_fingerprints": [
                    record.fingerprint
                    for record in self._records
                ],
            },
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _record(
        self,
        rollback_phase: str,
        rollback_id: str,
        sandbox_id: str,
        mutation_id: str,
        rollback_strategy: Any = None,
        rollback_summary: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationRollbackRecord:
        rollback_id = self._validate_text("rollback_id", rollback_id)
        sandbox_id = self._validate_text("sandbox_id", sandbox_id)
        mutation_id = self._validate_text("mutation_id", mutation_id)
        self._sequence += 1
        record = ControlledMutationRollbackRecord(
            record_id=self._record_id(
                rollback_id=rollback_id,
                sandbox_id=sandbox_id,
                mutation_id=mutation_id,
                rollback_phase=rollback_phase,
                sequence=self._sequence,
            ),
            boundary_id=self.boundary_id,
            rollback_id=rollback_id,
            sandbox_id=sandbox_id,
            mutation_id=mutation_id,
            rollback_phase=rollback_phase,
            sequence=self._sequence,
            rollback_strategy=rollback_strategy,
            rollback_summary=rollback_summary,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )
        self._records.append(copy.deepcopy(record))
        return copy.deepcopy(record)

    def _record_id(
        self,
        rollback_id: str,
        sandbox_id: str,
        mutation_id: str,
        rollback_phase: str,
        sequence: int,
    ) -> str:
        return (
            f"{self.boundary_id}:{rollback_id}:{sandbox_id}:"
            f"{mutation_id}:{rollback_phase}:{sequence}"
        )

    def _validate_text(self, field_name: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ControlledMutationRollbackRejected(
                f"controlled mutation rollback boundary {field_name} is required"
            )
        return value


__all__ = [
    "ControlledMutationRollbackBoundary",
    "ControlledMutationRollbackRecord",
    "ControlledMutationRollbackRejected",
]
