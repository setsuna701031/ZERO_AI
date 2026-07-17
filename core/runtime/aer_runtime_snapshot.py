"""Pure Snapshot v1 builder and validator."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


RESUME_SUMMARY_CONTRACT = "aer.runtime.resume_summary.v1"
SNAPSHOT_CONTRACT = "aer.runtime.snapshot.v1"
VALIDATION_REPORT_CONTRACT = "aer.runtime.snapshot.validation_report.v1"

REQUIRED_RESUME_SUMMARY_FIELDS = (
    "contract",
    "valid",
    "outcome",
    "status",
    "reason",
)

SNAPSHOT_FIELDS = (
    "contract",
    "snapshot_id",
    "source_valid",
    "source_outcome",
    "source_status",
    "valid",
    "status",
    "outcome",
    "reason",
    "metadata",
)

VALIDATION_ERROR_CATEGORIES = (
    "Schema Error",
    "Required Field Error",
    "Unknown Field Error",
    "Type Error",
    "Identity Error",
    "Lineage Error",
    "Status Error",
    "Consistency Error",
    "Version Error",
    "Determinism Error",
)

INVALID_UPSTREAM_REASON = "invalid upstream contract"
DEFAULT_INVALID_OUTCOME = "continue"
_SNAPSHOT_ID_PREFIX = "snapshot-v1-"


def build_snapshot_from_resume_summary(resume_summary: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic Snapshot v1 payload from Resume Summary v1 fields."""

    if _resume_summary_is_valid(resume_summary):
        body = {
            "contract": SNAPSHOT_CONTRACT,
            "source_valid": resume_summary["valid"],
            "source_outcome": resume_summary["outcome"],
            "source_status": resume_summary["status"],
            "valid": bool(resume_summary["valid"]),
            "status": "valid" if resume_summary["valid"] else "invalid",
            "outcome": resume_summary["outcome"],
            "reason": None if resume_summary["valid"] else INVALID_UPSTREAM_REASON,
            "metadata": {},
        }
    else:
        body = _invalid_snapshot_body()

    return _with_snapshot_id(body)


def validate_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return a descriptive Snapshot v1 validation report."""

    category = _validation_failure_category(snapshot)
    if category is None:
        return _validation_report(True, None, False, "valid snapshot")
    return _validation_report(False, category, True, category)


def snapshot_to_summary(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Project a Snapshot v1 payload to a minimal public summary."""

    report = validate_snapshot(snapshot)
    if not report["valid"]:
        return {
            "contract": SNAPSHOT_CONTRACT,
            "valid": False,
            "status": "invalid",
            "outcome": DEFAULT_INVALID_OUTCOME,
            "reason": report["category"],
        }

    return {
        "contract": SNAPSHOT_CONTRACT,
        "valid": snapshot["valid"],
        "status": snapshot["status"],
        "outcome": snapshot["outcome"],
        "reason": snapshot["reason"],
    }


def _resume_summary_is_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    keys = set(value.keys())
    required = set(REQUIRED_RESUME_SUMMARY_FIELDS)
    if keys != required:
        return False
    if value["contract"] != RESUME_SUMMARY_CONTRACT:
        return False
    if not isinstance(value["valid"], bool):
        return False
    if not isinstance(value["outcome"], str):
        return False
    if value["status"] not in {"valid", "invalid"}:
        return False
    if value["reason"] is not None and not isinstance(value["reason"], str):
        return False
    return True


def _invalid_snapshot_body() -> dict[str, Any]:
    return {
        "contract": SNAPSHOT_CONTRACT,
        "source_valid": False,
        "source_outcome": DEFAULT_INVALID_OUTCOME,
        "source_status": "invalid",
        "valid": False,
        "status": "invalid",
        "outcome": DEFAULT_INVALID_OUTCOME,
        "reason": INVALID_UPSTREAM_REASON,
        "metadata": {},
    }


def _with_snapshot_id(body: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(body)
    result["snapshot_id"] = _snapshot_id_for_body(body)
    return {field: result[field] for field in SNAPSHOT_FIELDS}


def _snapshot_id_for_body(body: Mapping[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{_SNAPSHOT_ID_PREFIX}{digest}"


def _validation_failure_category(value: Any) -> str | None:
    if not isinstance(value, Mapping):
        return "Schema Error"

    keys = set(value.keys())
    required = set(SNAPSHOT_FIELDS)
    if not required.issubset(keys):
        return "Required Field Error"
    if keys != required:
        return "Unknown Field Error"

    if value["contract"] != SNAPSHOT_CONTRACT:
        return "Version Error"

    if not _snapshot_field_types_are_valid(value):
        return "Type Error"

    expected_id = _snapshot_id_for_body({field: value[field] for field in SNAPSHOT_FIELDS if field != "snapshot_id"})
    if value["snapshot_id"] != expected_id:
        return "Identity Error"

    if value["source_status"] not in {"valid", "invalid"}:
        return "Lineage Error"

    if value["status"] not in {"valid", "invalid"}:
        return "Status Error"

    if value["valid"] and (value["status"] != "valid" or value["reason"] is not None):
        return "Consistency Error"
    if not value["valid"] and (value["status"] != "invalid" or not isinstance(value["reason"], str)):
        return "Consistency Error"

    return None


def _snapshot_field_types_are_valid(value: Mapping[str, Any]) -> bool:
    return (
        isinstance(value["snapshot_id"], str)
        and isinstance(value["source_valid"], bool)
        and isinstance(value["source_outcome"], str)
        and isinstance(value["source_status"], str)
        and isinstance(value["valid"], bool)
        and isinstance(value["status"], str)
        and isinstance(value["outcome"], str)
        and (value["reason"] is None or isinstance(value["reason"], str))
        and isinstance(value["metadata"], Mapping)
    )


def _validation_report(valid: bool, category: str | None, rejected: bool, reason: str) -> dict[str, Any]:
    return {
        "contract": VALIDATION_REPORT_CONTRACT,
        "valid": valid,
        "category": category,
        "rejected": rejected,
        "reason": reason,
        "descriptive_only": True,
        "auto_repair_allowed": False,
    }


__all__ = [
    "RESUME_SUMMARY_CONTRACT",
    "SNAPSHOT_CONTRACT",
    "VALIDATION_ERROR_CATEGORIES",
    "build_snapshot_from_resume_summary",
    "validate_snapshot",
    "snapshot_to_summary",
]
