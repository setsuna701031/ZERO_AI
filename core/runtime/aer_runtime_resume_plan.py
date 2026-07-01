"""Pure Runtime Resume eligibility and planning boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


ELIGIBILITY_CONTRACT = "aer.runtime.resume.eligibility.v1"
PLAN_CONTRACT = "aer.runtime.resume.plan.v1"
EXECUTION_BOUNDARY_CONTRACT = "aer.runtime.resume.execution_boundary.v1"
SNAPSHOT_CONSUMER_RESULT_CONTRACT = "aer.runtime.snapshot.consumer_result.v1"

_ELIGIBILITY_FIELDS = {
    "contract",
    "eligible",
    "blocked",
    "status",
    "reason",
    "snapshot_id",
    "lineage",
    "consumer_status",
    "validation",
    "descriptive_only",
}

_PLAN_REQUIRED_FIELDS = {
    "contract",
    "resume_token",
    "eligible",
    "status",
    "reason",
    "snapshot_id",
    "lineage",
    "consumer_status",
    "plan_steps",
    "execution_boundary",
    "metadata",
    "descriptive_only",
}

_PLAN_OPTIONAL_FIELDS = {
    "blocked_reason",
    "recovery_classification",
    "operator_note",
}

_ELIGIBILITY_STATUSES = {
    "eligible",
    "blocked",
    "invalid_snapshot",
    "invalid_consumer_result",
    "missing_identity",
    "lineage_mismatch",
    "unsupported_status",
    "recovery_required",
}


def check_resume_eligibility(consumer_result: Mapping[str, Any]) -> dict[str, Any]:
    """Create a descriptive resume eligibility decision from a consumer result."""

    result = _mapping_or_empty(consumer_result)
    consumer_status = _text_or_none(result.get("status"))
    snapshot_id = _text_or_none(result.get("snapshot_id"))
    lineage = _lineage(result.get("lineage"))
    validation = _mapping_copy(result.get("validation"))

    status = "eligible"
    reason: str | None = None
    if result.get("contract") != SNAPSHOT_CONSUMER_RESULT_CONTRACT:
        status = "invalid_consumer_result"
        reason = "invalid consumer result contract"
    elif result.get("accepted") is not True or result.get("rejected") is True:
        status = "invalid_snapshot"
        reason = _text_or_none(result.get("reason")) or "invalid snapshot"
    elif consumer_status != "accepted":
        status = "unsupported_status"
        reason = "unsupported consumer status"
    elif not snapshot_id:
        status = "missing_identity"
        reason = "missing snapshot identity"
    elif not _lineage_is_complete(lineage):
        status = "lineage_mismatch"
        reason = "lineage mismatch"
    elif validation.get("valid") is not True:
        status = "invalid_snapshot"
        reason = _text_or_none(validation.get("reason")) or "invalid snapshot"
    elif lineage.get("source_outcome") in {"recover", "recovery_required"}:
        status = "recovery_required"
        reason = "recovery required"

    eligible = status == "eligible"
    return {
        "contract": ELIGIBILITY_CONTRACT,
        "eligible": eligible,
        "blocked": not eligible,
        "status": status,
        "reason": reason,
        "snapshot_id": snapshot_id,
        "lineage": lineage,
        "consumer_status": consumer_status,
        "validation": validation,
        "descriptive_only": True,
    }


def validate_resume_eligibility(eligibility: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a Runtime Resume eligibility decision descriptively."""

    payload = _mapping_or_empty(eligibility)
    category = None
    reason = None

    if not isinstance(eligibility, Mapping):
        category = "Eligibility Error"
        reason = "eligibility must be a mapping"
    elif payload.get("contract") != ELIGIBILITY_CONTRACT:
        category = "Compatibility Error"
        reason = "invalid eligibility contract"
    elif set(payload) != _ELIGIBILITY_FIELDS:
        missing = _ELIGIBILITY_FIELDS - set(payload)
        category = "Eligibility Error" if missing else "Compatibility Error"
        reason = "missing eligibility fields" if missing else "unknown eligibility fields"
    elif not isinstance(payload.get("eligible"), bool) or not isinstance(payload.get("blocked"), bool):
        category = "Eligibility Error"
        reason = "eligibility booleans are invalid"
    elif payload.get("eligible") == payload.get("blocked"):
        category = "Eligibility Error"
        reason = "eligibility and blocked flags conflict"
    elif payload.get("status") not in _ELIGIBILITY_STATUSES:
        category = "Status Error"
        reason = "invalid eligibility status"
    elif payload.get("eligible") is True and payload.get("status") != "eligible":
        category = "Status Error"
        reason = "eligible decision must use eligible status"
    elif payload.get("eligible") is False and payload.get("status") == "eligible":
        category = "Status Error"
        reason = "blocked decision must not use eligible status"
    elif payload.get("snapshot_id") is not None and not isinstance(payload.get("snapshot_id"), str):
        category = "Identity Error"
        reason = "invalid snapshot identity"
    elif not isinstance(payload.get("lineage"), Mapping):
        category = "Lineage Error"
        reason = "invalid lineage"
    elif not isinstance(payload.get("validation"), Mapping):
        category = "Consumer Result Error"
        reason = "invalid validation evidence"
    elif payload.get("consumer_status") is not None and not isinstance(payload.get("consumer_status"), str):
        category = "Consumer Result Error"
        reason = "invalid consumer status"
    elif payload.get("descriptive_only") is not True:
        category = "Safety Error"
        reason = "eligibility must be descriptive only"

    return _validation_report(category, reason)


def build_resume_plan(
    eligibility: Mapping[str, Any],
    consumer_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a deterministic Resume Plan without running it."""

    decision = _mapping_or_empty(eligibility)
    result = _mapping_or_empty(consumer_result)
    is_valid_eligibility = validate_resume_eligibility(decision)["valid"] is True
    eligible = is_valid_eligibility and decision.get("eligible") is True
    status = "planned" if eligible else _text_or_none(decision.get("status")) or "blocked"
    reason = None if eligible else _text_or_none(decision.get("reason")) or "resume blocked"

    snapshot_id = _text_or_none(decision.get("snapshot_id")) or _text_or_none(result.get("snapshot_id"))
    lineage = _lineage(decision.get("lineage")) or _lineage(result.get("lineage"))
    consumer_status = _text_or_none(decision.get("consumer_status")) or _text_or_none(result.get("status"))
    plan_steps = (
        ["verify_identity", "prepare_resume_handoff"]
        if eligible
        else ["record_blocked_resume"]
    )

    plan = {
        "contract": PLAN_CONTRACT,
        "resume_token": _resume_token(decision, result),
        "eligible": eligible,
        "status": status,
        "reason": reason,
        "snapshot_id": snapshot_id,
        "lineage": lineage,
        "consumer_status": consumer_status,
        "plan_steps": plan_steps,
        "execution_boundary": _execution_boundary(),
        "metadata": {},
        "descriptive_only": True,
    }
    if not eligible:
        plan["blocked_reason"] = reason
    if status == "recovery_required":
        plan["recovery_classification"] = "future_recovery_domain"
    return plan


def validate_resume_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a Runtime Resume Plan descriptively."""

    payload = _mapping_or_empty(plan)
    allowed_fields = _PLAN_REQUIRED_FIELDS | _PLAN_OPTIONAL_FIELDS
    category = None
    reason = None

    if not isinstance(plan, Mapping):
        category = "Planning Error"
        reason = "plan must be a mapping"
    elif payload.get("contract") != PLAN_CONTRACT:
        category = "Compatibility Error"
        reason = "invalid plan contract"
    elif not _PLAN_REQUIRED_FIELDS <= set(payload):
        category = "Planning Error"
        reason = "missing plan fields"
    elif not set(payload) <= allowed_fields:
        category = "Compatibility Error"
        reason = "unknown plan fields"
    elif not _is_nonempty_text(payload.get("resume_token")):
        category = "Identity Error"
        reason = "invalid resume token"
    elif payload.get("snapshot_id") is not None and not isinstance(payload.get("snapshot_id"), str):
        category = "Identity Error"
        reason = "invalid snapshot identity"
    elif not isinstance(payload.get("eligible"), bool):
        category = "Planning Error"
        reason = "invalid plan eligibility flag"
    elif not isinstance(payload.get("status"), str):
        category = "Status Error"
        reason = "invalid plan status"
    elif payload.get("reason") is not None and not isinstance(payload.get("reason"), str):
        category = "Planning Error"
        reason = "invalid plan reason"
    elif not isinstance(payload.get("lineage"), Mapping):
        category = "Lineage Error"
        reason = "invalid plan lineage"
    elif payload.get("consumer_status") is not None and not isinstance(payload.get("consumer_status"), str):
        category = "Consumer Result Error"
        reason = "invalid consumer status"
    elif not _descriptive_string_list(payload.get("plan_steps")):
        category = "Planning Error"
        reason = "invalid plan steps"
    elif not _valid_execution_boundary(payload.get("execution_boundary")):
        category = "Execution Boundary Error"
        reason = "invalid execution boundary"
    elif not isinstance(payload.get("metadata"), Mapping):
        category = "Planning Error"
        reason = "invalid metadata"
    elif payload.get("descriptive_only") is not True:
        category = "Safety Error"
        reason = "plan must be descriptive only"

    return _validation_report(category, reason)


def resume_eligibility_to_summary(eligibility: Mapping[str, Any]) -> dict[str, Any]:
    """Project an eligibility decision to a stable public summary."""

    payload = _mapping_or_empty(eligibility)
    return {
        "contract": ELIGIBILITY_CONTRACT,
        "eligible": payload.get("eligible") is True,
        "blocked": payload.get("blocked") is True,
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "snapshot_id": payload.get("snapshot_id"),
        "lineage": _lineage(payload.get("lineage")),
    }


def resume_plan_to_summary(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Project a Resume Plan to a stable public summary."""

    payload = _mapping_or_empty(plan)
    return {
        "contract": PLAN_CONTRACT,
        "resume_token": payload.get("resume_token"),
        "eligible": payload.get("eligible") is True,
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "snapshot_id": payload.get("snapshot_id"),
        "lineage": _lineage(payload.get("lineage")),
        "consumer_status": payload.get("consumer_status"),
        "execution_boundary": _execution_boundary_summary(payload.get("execution_boundary")),
    }


def _resume_token(eligibility: Mapping[str, Any], consumer_result: Mapping[str, Any]) -> str:
    canonical = {
        "eligibility_contract": eligibility.get("contract"),
        "eligibility_status": eligibility.get("status"),
        "eligible": eligibility.get("eligible"),
        "snapshot_id": eligibility.get("snapshot_id") or consumer_result.get("snapshot_id"),
        "lineage": _lineage(eligibility.get("lineage")) or _lineage(consumer_result.get("lineage")),
        "consumer_contract": consumer_result.get("contract"),
        "consumer_status": consumer_result.get("status"),
    }
    body = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return "resume-plan-v1-" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def _execution_boundary() -> dict[str, Any]:
    return {
        "contract": EXECUTION_BOUNDARY_CONTRACT,
        "execution_allowed": False,
        "future_domain_only": True,
        "reason": "runtime resume execution is outside Package 127",
    }


def _valid_execution_boundary(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return value == _execution_boundary()


def _execution_boundary_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return _execution_boundary()
    return {
        "contract": value.get("contract"),
        "execution_allowed": value.get("execution_allowed"),
        "future_domain_only": value.get("future_domain_only"),
        "reason": value.get("reason"),
    }


def _validation_report(category: str | None, reason: str | None) -> dict[str, Any]:
    valid = category is None
    return {
        "valid": valid,
        "category": None if valid else category,
        "reason": None if valid else reason,
        "auto_repair_allowed": False,
        "descriptive_only": True,
    }


def _lineage(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: value[key]
        for key in ("source_valid", "source_outcome", "source_status")
        if key in value
    }


def _lineage_is_complete(value: Mapping[str, Any]) -> bool:
    return {"source_valid", "source_outcome", "source_status"} <= set(value)


def _mapping_copy(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _is_nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _descriptive_string_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) for item in value)


__all__ = [
    "ELIGIBILITY_CONTRACT",
    "PLAN_CONTRACT",
    "EXECUTION_BOUNDARY_CONTRACT",
    "check_resume_eligibility",
    "validate_resume_eligibility",
    "build_resume_plan",
    "validate_resume_plan",
    "resume_eligibility_to_summary",
    "resume_plan_to_summary",
]
