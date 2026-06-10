from __future__ import annotations

"""Validate collected evidence without invoking or modifying Runtime."""

from dataclasses import replace
from typing import Any, Mapping

from core.evidence.evidence_record import EvidenceRecord


class EvidenceValidator:
    def validate(self, record: EvidenceRecord | Mapping[str, Any], *, accepted: bool) -> EvidenceRecord:
        evidence = record if isinstance(record, EvidenceRecord) else EvidenceRecord.from_mapping(record)
        return replace(evidence, validation_state="validated" if accepted else "rejected")


__all__ = ["EvidenceValidator"]
