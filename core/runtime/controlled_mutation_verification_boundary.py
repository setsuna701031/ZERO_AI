from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class ControlledMutationVerificationRejected(RuntimeError):
    pass


class ControlledMutationVerificationRecord:
    ALLOWED_PHASES = {
        "planned",
        "started",
        "passed",
        "failed",
        "blocked",
    }

    def __init__(
        self,
        record_id: str,
        boundary_id: str,
        verification_id: str,
        sandbox_id: str,
        mutation_id: str,
        verification_phase: str,
        sequence: int,
        verification_strategy: Any = None,
        verification_summary: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
        created_at: str | None = None,
    ) -> None:
        self._record_id = self._validate_text("record_id", record_id)
        self._boundary_id = self._validate_text("boundary_id", boundary_id)
        self._verification_id = self._validate_text("verification_id", verification_id)
        self._sandbox_id = self._validate_text("sandbox_id", sandbox_id)
        self._mutation_id = self._validate_text("mutation_id", mutation_id)
        self._verification_phase = self._validate_phase(verification_phase)
        self._sequence = self._validate_sequence(sequence)
        self._verification_strategy = copy.deepcopy(verification_strategy)
        self._verification_summary = copy.deepcopy(verification_summary)
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
    def verification_id(self) -> str:
        return self._verification_id

    @property
    def sandbox_id(self) -> str:
        return self._sandbox_id

    @property
    def mutation_id(self) -> str:
        return self._mutation_id

    @property
    def verification_phase(self) -> str:
        return self._verification_phase

    @property
    def verification_strategy(self) -> Any:
        return copy.deepcopy(self._verification_strategy)

    @property
    def verification_summary(self) -> Any:
        return copy.deepcopy(self._verification_summary)

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
            "verification_id": self._verification_id,
            "sandbox_id": self._sandbox_id,
            "mutation_id": self._mutation_id,
            "verification_phase": self._verification_phase,
            "verification_strategy": self._verification_strategy,
            "verification_summary": self._verification_summary,
            "evidence_refs": self._evidence_refs,
            "metadata": self._metadata,
            "runtime_args": self._runtime_args,
            "sequence": self._sequence,
        }

    def _validate_text(self, field_name: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ControlledMutationVerificationRejected(
                f"controlled mutation verification {field_name} is required"
            )
        return value

    def _validate_phase(self, phase: str) -> str:
        phase = self._validate_text("verification_phase", phase)
        if phase not in self.ALLOWED_PHASES:
            raise ControlledMutationVerificationRejected(
                f"controlled mutation verification phase is unsupported: {phase}"
            )
        return phase

    def _validate_sequence(self, sequence: int) -> int:
        if not isinstance(sequence, int) or sequence < 1:
            raise ControlledMutationVerificationRejected(
                "controlled mutation verification sequence must be positive"
            )
        return sequence


class ControlledMutationVerificationBoundary:
    def __init__(self, boundary_id: str) -> None:
        self.boundary_id = self._validate_text("boundary_id", boundary_id)
        self._sequence = 0
        self._records: list[ControlledMutationVerificationRecord] = []

    def record_verification_planned(
        self,
        verification_id: str,
        sandbox_id: str,
        mutation_id: str,
        verification_strategy: Any = None,
        verification_summary: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationVerificationRecord:
        return self._record(
            verification_phase="planned",
            verification_id=verification_id,
            sandbox_id=sandbox_id,
            mutation_id=mutation_id,
            verification_strategy=verification_strategy,
            verification_summary=verification_summary,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def record_verification_started(
        self,
        verification_id: str,
        sandbox_id: str,
        mutation_id: str,
        verification_strategy: Any = None,
        verification_summary: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationVerificationRecord:
        return self._record(
            verification_phase="started",
            verification_id=verification_id,
            sandbox_id=sandbox_id,
            mutation_id=mutation_id,
            verification_strategy=verification_strategy,
            verification_summary=verification_summary,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def record_verification_passed(
        self,
        verification_id: str,
        sandbox_id: str,
        mutation_id: str,
        verification_summary: Any,
        verification_strategy: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationVerificationRecord:
        return self._record(
            verification_phase="passed",
            verification_id=verification_id,
            sandbox_id=sandbox_id,
            mutation_id=mutation_id,
            verification_strategy=verification_strategy,
            verification_summary=verification_summary,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def record_verification_failed(
        self,
        verification_id: str,
        sandbox_id: str,
        mutation_id: str,
        verification_summary: Any,
        verification_strategy: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationVerificationRecord:
        return self._record(
            verification_phase="failed",
            verification_id=verification_id,
            sandbox_id=sandbox_id,
            mutation_id=mutation_id,
            verification_strategy=verification_strategy,
            verification_summary=verification_summary,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def record_verification_blocked(
        self,
        verification_id: str,
        sandbox_id: str,
        mutation_id: str,
        verification_summary: Any,
        verification_strategy: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationVerificationRecord:
        return self._record(
            verification_phase="blocked",
            verification_id=verification_id,
            sandbox_id=sandbox_id,
            mutation_id=mutation_id,
            verification_strategy=verification_strategy,
            verification_summary=verification_summary,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )

    def list_records(self) -> list[ControlledMutationVerificationRecord]:
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
        verification_phase: str,
        verification_id: str,
        sandbox_id: str,
        mutation_id: str,
        verification_strategy: Any = None,
        verification_summary: Any = None,
        evidence_refs: Any = None,
        metadata: Any = None,
        runtime_args: Any = None,
    ) -> ControlledMutationVerificationRecord:
        verification_id = self._validate_text("verification_id", verification_id)
        sandbox_id = self._validate_text("sandbox_id", sandbox_id)
        mutation_id = self._validate_text("mutation_id", mutation_id)
        self._sequence += 1
        record = ControlledMutationVerificationRecord(
            record_id=self._record_id(
                verification_id=verification_id,
                sandbox_id=sandbox_id,
                mutation_id=mutation_id,
                verification_phase=verification_phase,
                sequence=self._sequence,
            ),
            boundary_id=self.boundary_id,
            verification_id=verification_id,
            sandbox_id=sandbox_id,
            mutation_id=mutation_id,
            verification_phase=verification_phase,
            sequence=self._sequence,
            verification_strategy=verification_strategy,
            verification_summary=verification_summary,
            evidence_refs=evidence_refs,
            metadata=metadata,
            runtime_args=runtime_args,
        )
        self._records.append(copy.deepcopy(record))
        return copy.deepcopy(record)

    def _record_id(
        self,
        verification_id: str,
        sandbox_id: str,
        mutation_id: str,
        verification_phase: str,
        sequence: int,
    ) -> str:
        return (
            f"{self.boundary_id}:{verification_id}:{sandbox_id}:"
            f"{mutation_id}:{verification_phase}:{sequence}"
        )

    def _validate_text(self, field_name: str, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ControlledMutationVerificationRejected(
                f"controlled mutation verification boundary {field_name} is required"
            )
        return value


__all__ = [
    "ControlledMutationVerificationBoundary",
    "ControlledMutationVerificationRecord",
    "ControlledMutationVerificationRejected",
]
