"""Pure Runtime Recovery plan builder."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from core.runtime import aer_runtime_recovery_validation as _validation
from core.runtime.aer_runtime_recovery_validation import (
    RECOVERY_EXECUTION_BOUNDARY_CONTRACT,
    RECOVERY_PLAN_CONTRACT,
)


__all__ = [
    "build_recovery_plan",
]


def build_recovery_plan(
    eligibility: Mapping[str, Any],
    *,
    recovery_token: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic data-only Recovery Plan from eligibility input."""

    source = _plain_mapping(eligibility)
    eligibility_report = _validation.validate_recovery_eligibility(source)
    eligibility_valid = eligibility_report.get("valid") is True

    status = _plan_status(source, eligibility_valid)
    reason = _plan_reason(source, eligibility_valid, eligibility_report)
    failure_classification = _failure_classification(source, eligibility_valid)

    plan = {
        "contract": RECOVERY_PLAN_CONTRACT,
        "recovery_token": _recovery_token(source, recovery_token),
        "eligible": bool(source.get("eligible")) if eligibility_valid else False,
        "status": status,
        "reason": reason,
        "execution_summary": _plain_mapping(source.get("execution_summary")) if eligibility_valid else {},
        "failure_classification": failure_classification,
        "plan_steps": _plan_steps(status, failure_classification),
        "execution_boundary": _execution_boundary(status),
        "metadata": _plain_mapping(metadata),
        "descriptive_only": True,
    }
    return plan


def _plan_status(source: Mapping[str, Any], eligibility_valid: bool) -> str:
    if not eligibility_valid:
        return "invalid_recovery_request"
    if source.get("eligible") is not True or source.get("blocked") is True:
        return "blocked"
    if source.get("recovery_authorized") is not True:
        return "recovery_not_authorized"
    return "planned"


def _plan_reason(
    source: Mapping[str, Any],
    eligibility_valid: bool,
    eligibility_report: Mapping[str, Any],
) -> str | None:
    if not eligibility_valid:
        return _text_or_none(eligibility_report.get("reason")) or "invalid recovery eligibility"
    source_reason = _text_or_none(source.get("reason"))
    if source_reason is not None:
        return source_reason
    if source.get("eligible") is not True or source.get("blocked") is True:
        return "recovery eligibility is blocked"
    if source.get("recovery_authorized") is not True:
        return "recovery is not authorized"
    return None


def _failure_classification(source: Mapping[str, Any], eligibility_valid: bool) -> str | None:
    if not eligibility_valid:
        return "invalid_recovery_request"
    return _text_or_none(source.get("failure_classification"))


def _plan_steps(status: str, failure_classification: str | None) -> list[str]:
    if status == "planned":
        classification = failure_classification or "unclassified recovery failure"
        return [f"describe recovery planning for {classification}"]
    if status == "blocked":
        return ["describe blocked recovery eligibility"]
    if status == "recovery_not_authorized":
        return ["describe recovery authorization requirement"]
    return ["describe invalid recovery eligibility"]


def _execution_boundary(status: str) -> dict[str, Any]:
    return {
        "contract": RECOVERY_EXECUTION_BOUNDARY_CONTRACT,
        "execution_allowed": False,
        "future_domain_only": True,
        "downstream_authorized": False,
        "reason": _boundary_reason(status),
    }


def _boundary_reason(status: str) -> str:
    if status == "planned":
        return "recovery plan remains descriptive and future-domain only"
    if status == "blocked":
        return "blocked recovery plan cannot authorize execution"
    if status == "recovery_not_authorized":
        return "unauthorized recovery plan cannot authorize execution"
    return "invalid recovery eligibility cannot authorize execution"


def _recovery_token(source: Mapping[str, Any], recovery_token: str | None) -> str:
    if _non_empty_text(recovery_token):
        return recovery_token.strip()
    body = json.dumps(_plain_mapping(source), sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]
    return f"recovery-plan-v1-{digest}"


def _plain_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _plain_value(item) for key, item in value.items()}


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _plain_mapping(value)
    if isinstance(value, list):
        return [_plain_value(item) for item in value]
    if isinstance(value, tuple):
        return [_plain_value(item) for item in value]
    return value


def _text_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
