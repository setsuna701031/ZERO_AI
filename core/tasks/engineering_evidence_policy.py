from __future__ import annotations

"""Read-only policy layer for engineering evidence classification."""

import copy
import time
from typing import Any, Mapping, Sequence


ENGINEERING_EVIDENCE_POLICY_SCHEMA = "zero.engineering_evidence_policy.v1"

ACTIVE_EVIDENCE_STATE = "active"
ARCHIVED_EVIDENCE_STATE = "archived"
EVIDENCE_POLICY_STATES = {ACTIVE_EVIDENCE_STATE, ARCHIVED_EVIDENCE_STATE}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _evidence_id(evidence: Mapping[str, Any]) -> str:
    return _clean_text(evidence.get("evidence_id") or evidence.get("id"))


def _evidence_type(evidence: Mapping[str, Any]) -> str:
    return _clean_text(evidence.get("evidence_type") or evidence.get("type"), "unknown") or "unknown"


class EngineeringEvidencePolicy:
    """Classify evidence and build deterministic evidence summaries."""

    def classify_evidence(self, evidence: Mapping[str, Any]) -> str:
        record = _as_mapping(evidence)
        metadata = _as_mapping(record.get("metadata"))
        if bool(record.get("archived")) or bool(metadata.get("archived")):
            return ARCHIVED_EVIDENCE_STATE

        for candidate in (
            record.get("evidence_state"),
            record.get("lifecycle_state"),
            record.get("state"),
            record.get("status"),
            metadata.get("evidence_state"),
            metadata.get("lifecycle_state"),
            metadata.get("state"),
            metadata.get("status"),
        ):
            state = _clean_text(candidate).lower()
            if state == ARCHIVED_EVIDENCE_STATE:
                return ARCHIVED_EVIDENCE_STATE
            if state == ACTIVE_EVIDENCE_STATE:
                return ACTIVE_EVIDENCE_STATE
        return ACTIVE_EVIDENCE_STATE

    def is_archived_evidence(self, evidence: Mapping[str, Any]) -> bool:
        return self.classify_evidence(evidence) == ARCHIVED_EVIDENCE_STATE

    def is_active_evidence(self, evidence: Mapping[str, Any]) -> bool:
        return self.classify_evidence(evidence) == ACTIVE_EVIDENCE_STATE

    def select_latest_evidence(self, evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        records = [_as_mapping(item) for item in evidence if isinstance(item, Mapping)]
        latest = max(records, key=lambda item: (_as_float(item.get("created_at")), _evidence_id(item)), default={})
        return copy.deepcopy(latest)

    def build_evidence_summary(self, evidence: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        records = [_as_mapping(item) for item in evidence if isinstance(item, Mapping)]
        active: list[dict[str, Any]] = []
        archived: list[dict[str, Any]] = []
        evidence_type_summary: dict[str, dict[str, Any]] = {}

        for record in records:
            state = self.classify_evidence(record)
            target = archived if state == ARCHIVED_EVIDENCE_STATE else active
            target.append(copy.deepcopy(record))

            evidence_type = _evidence_type(record)
            type_summary = evidence_type_summary.setdefault(
                evidence_type,
                {
                    "evidence_type": evidence_type,
                    "active": 0,
                    "archived": 0,
                    "total": 0,
                    "latest_evidence": {},
                },
            )
            type_summary[state] += 1
            type_summary["total"] += 1
            type_summary["latest_evidence"] = self.select_latest_evidence(
                [type_summary["latest_evidence"], record] if type_summary["latest_evidence"] else [record]
            )

        return {
            "schema": ENGINEERING_EVIDENCE_POLICY_SCHEMA,
            "ok": True,
            "active": active,
            "archived": archived,
            "active_count": len(active),
            "archived_count": len(archived),
            "evidence_count": len(records),
            "latest_evidence": self.select_latest_evidence(records),
            "evidence_type_summary": evidence_type_summary,
            "updated_at": time.time(),
        }


__all__ = [
    "ACTIVE_EVIDENCE_STATE",
    "ARCHIVED_EVIDENCE_STATE",
    "ENGINEERING_EVIDENCE_POLICY_SCHEMA",
    "EVIDENCE_POLICY_STATES",
    "EngineeringEvidencePolicy",
]
