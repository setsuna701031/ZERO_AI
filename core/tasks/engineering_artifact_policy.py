from __future__ import annotations

"""Read-only policy layer for engineering artifact classification.

EngineeringArtifactPolicy owns deterministic artifact classification and
summary rules. It does not load data, persist data, execute work, schedule
tasks, call runtime owners, use memory, or render UI.
"""

import copy
import time
from typing import Any, Mapping, Sequence


ENGINEERING_ARTIFACT_POLICY_SCHEMA = "zero.engineering_artifact_policy.v1"

ACTIVE_ARTIFACT_STATE = "active"
ARCHIVED_ARTIFACT_STATE = "archived"
ARTIFACT_POLICY_STATES = {ACTIVE_ARTIFACT_STATE, ARCHIVED_ARTIFACT_STATE}


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


def _artifact_id(artifact: Mapping[str, Any]) -> str:
    return _clean_text(artifact.get("artifact_id") or artifact.get("id"))


def _artifact_type(artifact: Mapping[str, Any]) -> str:
    return _clean_text(artifact.get("artifact_type") or artifact.get("type"), "unknown") or "unknown"


class EngineeringArtifactPolicy:
    """Classify artifacts and build deterministic artifact summaries."""

    def classify_artifact(self, artifact: Mapping[str, Any]) -> str:
        record = _as_mapping(artifact)
        metadata = _as_mapping(record.get("metadata"))
        if bool(record.get("archived")) or bool(metadata.get("archived")):
            return ARCHIVED_ARTIFACT_STATE

        for candidate in (
            record.get("artifact_state"),
            record.get("lifecycle_state"),
            record.get("state"),
            record.get("status"),
            metadata.get("artifact_state"),
            metadata.get("lifecycle_state"),
            metadata.get("state"),
            metadata.get("status"),
        ):
            state = _clean_text(candidate).lower()
            if state == ARCHIVED_ARTIFACT_STATE:
                return ARCHIVED_ARTIFACT_STATE
            if state == ACTIVE_ARTIFACT_STATE:
                return ACTIVE_ARTIFACT_STATE
        return ACTIVE_ARTIFACT_STATE

    def is_archived_artifact(self, artifact: Mapping[str, Any]) -> bool:
        return self.classify_artifact(artifact) == ARCHIVED_ARTIFACT_STATE

    def is_active_artifact(self, artifact: Mapping[str, Any]) -> bool:
        return self.classify_artifact(artifact) == ACTIVE_ARTIFACT_STATE

    def select_latest_artifact(self, artifacts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        records = [_as_mapping(item) for item in artifacts if isinstance(item, Mapping)]
        latest = max(records, key=lambda item: (_as_float(item.get("created_at")), _artifact_id(item)), default={})
        return copy.deepcopy(latest)

    def build_artifact_summary(self, artifacts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        records = [_as_mapping(item) for item in artifacts if isinstance(item, Mapping)]
        active: list[dict[str, Any]] = []
        archived: list[dict[str, Any]] = []
        artifact_type_summary: dict[str, dict[str, Any]] = {}

        for record in records:
            state = self.classify_artifact(record)
            target = archived if state == ARCHIVED_ARTIFACT_STATE else active
            target.append(copy.deepcopy(record))

            artifact_type = _artifact_type(record)
            type_summary = artifact_type_summary.setdefault(
                artifact_type,
                {
                    "artifact_type": artifact_type,
                    "active": 0,
                    "archived": 0,
                    "total": 0,
                    "latest_artifact": {},
                },
            )
            type_summary[state] += 1
            type_summary["total"] += 1
            type_summary["latest_artifact"] = self.select_latest_artifact(
                [type_summary["latest_artifact"], record] if type_summary["latest_artifact"] else [record]
            )

        return {
            "schema": ENGINEERING_ARTIFACT_POLICY_SCHEMA,
            "ok": True,
            "active": active,
            "archived": archived,
            "active_count": len(active),
            "archived_count": len(archived),
            "artifact_count": len(records),
            "latest_artifact": self.select_latest_artifact(records),
            "artifact_type_summary": artifact_type_summary,
            "updated_at": time.time(),
        }


__all__ = [
    "ACTIVE_ARTIFACT_STATE",
    "ARCHIVED_ARTIFACT_STATE",
    "ARTIFACT_POLICY_STATES",
    "ENGINEERING_ARTIFACT_POLICY_SCHEMA",
    "EngineeringArtifactPolicy",
]
