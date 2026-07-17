"""Pure Runtime Resume Execution request/result/failure builders."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from core.runtime import aer_runtime_resume_execution_validation as _validation
from core.runtime.aer_runtime_resume_execution_validation import (
    EXECUTION_FAILURE_CONTRACT,
    EXECUTION_REQUEST_CONTRACT,
    EXECUTION_RESULT_CONTRACT,
    RESUME_CONSUMER_OUTPUT_CONTRACT,
)

CONSUMER_BOUNDARY_CONTRACT = "aer.runtime.resume.consumer_boundary.v1"
EXECUTION_BOUNDARY_CONTRACT = "aer.runtime.resume.execution_boundary.v1"

__all__ = [
    "CONSUMER_BOUNDARY_CONTRACT",
    "EXECUTION_BOUNDARY_CONTRACT",
    "build_execution_request",
    "build_execution_result",
    "build_execution_failure",
    "execution_request_to_summary",
    "execution_result_to_summary",
    "execution_failure_to_summary",
]


def build_execution_request(
    consumer_output: Mapping[str, Any],
    *,
    requested_action: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic execution request descriptor from consumer output.

    The returned request is data-only. It does not execute resume, does not
    authorize execution, and does not call downstream domains.
    """

    source = _mapping_copy(consumer_output)
    execution_boundary = _mapping_copy(source.get("execution_boundary"))
    consumer_boundary = _mapping_copy(source.get("consumer_boundary"))
    source_contract = _text_or_none(source.get("contract"))
    source_status = _text_or_none(source.get("status")) or "invalid_consumer_output"
    source_reason = _text_or_none(source.get("reason"))
    resume_token = _text_or_none(source.get("resume_token"))
    snapshot_id = _text_or_none(source.get("snapshot_id"))
    lineage = _mapping_copy(source.get("lineage"))
    source_is_consumer_output = source_contract == RESUME_CONSUMER_OUTPUT_CONTRACT
    execution_allowed = execution_boundary.get("execution_allowed") is True
    downstream_authorized = consumer_boundary.get("downstream_authorized") is True
    accepted = source.get("accepted_for_future_domain") is True and source.get("blocked") is False

    action = requested_action or ("validate_only" if accepted else "blocked")
    request = {
        "contract": EXECUTION_REQUEST_CONTRACT,
        "execution_request_id": _execution_request_id(source),
        "resume_token": resume_token,
        "snapshot_id": snapshot_id,
        "lineage": lineage,
        "source_contract": source_contract,
        "source_status": source_status,
        "source_reason": source_reason,
        "execution_allowed": False,
        "requested_action": action,
        "preconditions": {
            "consumer_output_contract_valid": source_is_consumer_output,
            "accepted_for_future_domain": accepted,
            "execution_boundary_present": bool(execution_boundary),
            "execution_boundary_allows_execution": execution_allowed,
            "consumer_boundary_present": bool(consumer_boundary),
            "downstream_authorized": downstream_authorized,
        },
        "failure_policy": {
            "on_failure": "describe_only",
            "auto_repair_allowed": False,
            "downstream_handoff_allowed": False,
        },
        "metadata": _mapping_copy(metadata),
        "descriptive_only": True,
    }
    return request


def build_execution_result(
    request: Mapping[str, Any],
    *,
    status: str | None = None,
    failure: Mapping[str, Any] | None = None,
    downstream_handoff_type: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a data-only execution result descriptor from a request.

    This function records validation or blocked/failure state only. It does not
    perform runtime resume execution and does not perform downstream handoff.
    """

    payload = _mapping_copy(request)
    request_valid = _validation.validate_execution_request(payload).get("valid") is True
    failure_payload = _mapping_copy(failure) if failure is not None else None
    if failure_payload is not None and _validation.validate_execution_failure(failure_payload).get("valid") is not True:
        failure_payload = build_execution_failure(
            failure_code="invalid_execution_request",
            category="Compatibility Error",
            owner="Runtime Resume Execution",
            reason="invalid execution failure descriptor",
        )
    if not request_valid and failure_payload is None:
        failure_payload = build_execution_failure(
            failure_code="invalid_execution_request",
            category="Compatibility Error",
            owner="Runtime Resume Execution",
            reason="invalid execution request",
        )

    result_status = status or ("failed" if failure_payload is not None else "validated")
    failed = failure_payload is not None or result_status == "failed"
    downstream_required = result_status == "handoff_required"
    result = {
        "contract": EXECUTION_RESULT_CONTRACT,
        "execution_request_id": payload.get("execution_request_id"),
        "resume_token": payload.get("resume_token"),
        "snapshot_id": payload.get("snapshot_id"),
        "lineage": _mapping_copy(payload.get("lineage")),
        "status": result_status,
        "reason": _result_reason(result_status, failure_payload),
        "completed": False,
        "failed": failed,
        "failure": failure_payload,
        "downstream_handoff_required": downstream_required,
        "downstream_handoff_type": downstream_handoff_type if downstream_required else None,
        "metadata": _mapping_copy(metadata),
        "descriptive_only": True,
    }
    return result


def build_execution_failure(
    *,
    failure_code: str,
    category: str,
    owner: str,
    reason: str,
    recoverable: bool = False,
    downstream_owner: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a data-only execution failure descriptor."""

    return {
        "contract": EXECUTION_FAILURE_CONTRACT,
        "failure_code": failure_code,
        "category": category,
        "owner": owner,
        "reason": reason,
        "recoverable": recoverable,
        "downstream_owner": downstream_owner,
        "metadata": _mapping_copy(metadata),
        "descriptive_only": True,
    }


def execution_request_to_summary(request: Mapping[str, Any]) -> dict[str, Any]:
    """Project an execution request to a stable public builder summary."""

    return _validation.execution_request_to_summary(request)


def execution_result_to_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    """Project an execution result to a stable public builder summary."""

    return _validation.execution_result_to_summary(result)


def execution_failure_to_summary(failure: Mapping[str, Any]) -> dict[str, Any]:
    """Project an execution failure to a stable public builder summary."""

    return _validation.execution_failure_to_summary(failure)


def _execution_request_id(source: Mapping[str, Any]) -> str:
    canonical = {
        "contract": source.get("contract"),
        "resume_token": source.get("resume_token"),
        "snapshot_id": source.get("snapshot_id"),
        "lineage": _mapping_copy(source.get("lineage")),
        "status": source.get("status"),
        "reason": source.get("reason"),
        "execution_boundary": _mapping_copy(source.get("execution_boundary")),
        "consumer_boundary": _mapping_copy(source.get("consumer_boundary")),
    }
    body = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]
    return f"resume-execution-request-v1-{digest}"


def _result_reason(status: str, failure: Mapping[str, Any] | None) -> str | None:
    if failure is not None:
        return _text_or_none(failure.get("reason")) or "execution failure"
    if status == "validated":
        return None
    if status == "blocked":
        return "execution request blocked"
    if status == "handoff_required":
        return "future downstream handoff required"
    if status == "not_started":
        return "execution not started"
    return None


def _mapping_copy(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _text_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None
