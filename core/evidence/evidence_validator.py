from __future__ import annotations

"""Validate collected evidence without invoking or modifying Runtime."""

from dataclasses import replace
from typing import Any, Mapping

from core.evidence.evidence_record import EvidenceRecord


_VALIDATED_EVIDENCE: dict[int, EvidenceRecord] = {}


def is_provenance_validated_evidence(value: Any) -> bool:
    return (
        isinstance(value, EvidenceRecord)
        and value.validation_state == "validated"
        and _VALIDATED_EVIDENCE.get(id(value)) is value
    )


class EvidenceValidator:
    def validate(self, record: EvidenceRecord | Mapping[str, Any]) -> EvidenceRecord:
        evidence = record if isinstance(record, EvidenceRecord) else EvidenceRecord.from_mapping(record)
        validated = replace(evidence, validation_state="validated")
        _VALIDATED_EVIDENCE[id(validated)] = validated
        return validated

    def reject(self, record: EvidenceRecord | Mapping[str, Any]) -> EvidenceRecord:
        evidence = record if isinstance(record, EvidenceRecord) else EvidenceRecord.from_mapping(record)
        return replace(evidence, validation_state="rejected")


__all__ = ["EvidenceValidator", "is_provenance_validated_evidence"]
