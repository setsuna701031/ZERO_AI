from __future__ import annotations

"""Validate collected evidence without invoking or modifying Runtime."""

from dataclasses import replace
from typing import Any, Mapping

from core.evidence.evidence_record import EvidenceRecord


def _build_evidence_provenance_boundary():
    validated_evidence: dict[int, EvidenceRecord] = {}

    class EvidenceValidator:
        def validate(self, record: EvidenceRecord | Mapping[str, Any]) -> EvidenceRecord:
            evidence = record if isinstance(record, EvidenceRecord) else EvidenceRecord.from_mapping(record)
            validated = replace(evidence, validation_state="validated")
            validated_evidence[id(validated)] = validated
            return validated

        def reject(self, record: EvidenceRecord | Mapping[str, Any]) -> EvidenceRecord:
            evidence = record if isinstance(record, EvidenceRecord) else EvidenceRecord.from_mapping(record)
            return replace(evidence, validation_state="rejected")

    def is_provenance_validated_evidence(value: Any, *, goal_id: str | None = None) -> bool:
        return bool(
            isinstance(value, EvidenceRecord)
            and value.validation_state == "validated"
            and validated_evidence.get(id(value)) is value
            and (goal_id is None or value.goal_id == goal_id)
        )

    return EvidenceValidator, is_provenance_validated_evidence


EvidenceValidator, is_provenance_validated_evidence = _build_evidence_provenance_boundary()
del _build_evidence_provenance_boundary


__all__ = ["EvidenceValidator", "is_provenance_validated_evidence"]
