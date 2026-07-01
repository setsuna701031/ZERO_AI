"""Pure Runtime Resume Execution contract validation helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


EXECUTION_REQUEST_CONTRACT = "aer.runtime.resume.execution_request.v1"
EXECUTION_RESULT_CONTRACT = "aer.runtime.resume.execution_result.v1"
EXECUTION_FAILURE_CONTRACT = "aer.runtime.resume.execution_failure.v1"
RESUME_CONSUMER_OUTPUT_CONTRACT = "aer.runtime.resume.consumer_output.v1"

REQUEST_REQUIRED_FIELDS = frozenset(
    {
        "contract",
        "execution_request_id",
        "resume_token",
        "snapshot_id",
        "lineage",
        "source_contract",
        "source_status",
        "source_reason",
        "execution_allowed",
        "requested_action",
        "preconditions",
        "failure_policy",
        "metadata",
        "descriptive_only",
    }
)

RESULT_REQUIRED_FIELDS = frozenset(
    {
        "contract",
        "execution_request_id",
        "resume_token",
        "snapshot_id",
        "lineage",
        "status",
        "reason",
        "completed",
        "failed",
        "failure",
        "downstream_handoff_required",
        "downstream_handoff_type",
        "metadata",
        "descriptive_only",
    }
)

FAILURE_REQUIRED_FIELDS = frozenset(
    {
        "contract",
        "failure_code",
        "category",
        "owner",
        "reason",
        "recoverable",
        "downstream_owner",
        "metadata",
        "descriptive_only",
    }
)

ALLOWED_REQUESTED_ACTIONS = frozenset({"resume_runtime", "validate_only", "blocked"})

ALLOWED_RESULT_STATUSES = frozenset(
    {"not_started", "blocked", "validated", "completed", "failed", "handoff_required"}
)

ALLOWED_HANDOFF_TYPES = frozenset(
    {"recovery", "scheduler", "dispatcher", "operator", "persistence", "audit", "journal", "replay"}
)

ALLOWED_FAILURE_CODES = frozenset(
    {
        "invalid_execution_request",
        "invalid_consumer_output",
        "consumer_boundary_violation",
        "execution_not_authorized",
        "precondition_failed",
        "lineage_mismatch",
        "identity_mismatch",
        "unsupported_requested_action",
        "future_domain_required",
        "downstream_contract_missing",
        "runtime_execution_failed",
        "ownership_violation",
    }
)

ALLOWED_FAILURE_CATEGORIES = frozenset(
    {
        "Compatibility Error",
        "Consumer Boundary Error",
        "Execution Boundary Error",
        "Precondition Error",
        "Lineage Error",
        "Identity Error",
        "Status Error",
        "Future Domain Required",
        "Runtime Execution Error",
        "Ownership Violation",
    }
)

ALLOWED_FAILURE_OWNERS = frozenset(
    {
        "Runtime Resume Execution",
        "Runtime Resume Consumer Boundary",
        "Future Recovery",
        "Future Scheduler",
        "Future Dispatcher",
        "Future Operator",
        "Future Persistence",
        "Future Audit",
        "Future Journal",
        "Future Replay",
    }
)

__all__ = [
    "EXECUTION_REQUEST_CONTRACT",
    "EXECUTION_RESULT_CONTRACT",
    "EXECUTION_FAILURE_CONTRACT",
    "RESUME_CONSUMER_OUTPUT_CONTRACT",
    "REQUEST_REQUIRED_FIELDS",
    "RESULT_REQUIRED_FIELDS",
    "FAILURE_REQUIRED_FIELDS",
    "ALLOWED_REQUESTED_ACTIONS",
    "ALLOWED_RESULT_STATUSES",
    "ALLOWED_HANDOFF_TYPES",
    "ALLOWED_FAILURE_CODES",
    "ALLOWED_FAILURE_CATEGORIES",
    "ALLOWED_FAILURE_OWNERS",
    "validate_execution_request",
    "validate_execution_result",
    "validate_execution_failure",
    "execution_request_to_summary",
    "execution_result_to_summary",
    "execution_failure_to_summary",
]


def validate_execution_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a Runtime Resume Execution Request without side effects."""

    if not isinstance(request, Mapping):
        return _report("Compatibility Error", "execution request must be a mapping")
    payload = dict(request)
    if payload.get("contract") != EXECUTION_REQUEST_CONTRACT:
        return _report("Compatibility Error", "invalid execution request contract")
    field_report = _validate_fields(payload, REQUEST_REQUIRED_FIELDS, "execution request")
    if field_report is not None:
        return field_report
    safety_report = _validate_safe_values(payload, "execution request")
    if safety_report is not None:
        return safety_report
    if not _non_empty_text(payload.get("execution_request_id")):
        return _report("Identity Error", "invalid execution request identity")
    if not _non_empty_text(payload.get("resume_token")):
        return _report("Identity Error", "invalid resume token")
    if not isinstance(payload.get("snapshot_id"), (str, type(None))):
        return _report("Identity Error", "invalid snapshot identity")
    if not isinstance(payload.get("lineage"), Mapping):
        return _report("Lineage Error", "invalid lineage")
    if not _non_empty_text(payload.get("source_contract")):
        return _report("Consumer Boundary Error", "invalid source contract")
    if not _non_empty_text(payload.get("source_status")):
        return _report("Status Error", "invalid source status")
    if payload.get("source_reason") is not None and not isinstance(payload.get("source_reason"), str):
        return _report("Consumer Boundary Error", "invalid source reason")
    if payload.get("execution_allowed") is not False:
        return _report("Execution Boundary Error", "execution must not be authorized by validation")
    if payload.get("requested_action") not in ALLOWED_REQUESTED_ACTIONS:
        return _report("Status Error", "unsupported requested action")
    if not isinstance(payload.get("preconditions"), Mapping):
        return _report("Precondition Error", "invalid preconditions")
    if not isinstance(payload.get("failure_policy"), Mapping):
        return _report("Compatibility Error", "invalid failure policy")
    if not isinstance(payload.get("metadata"), Mapping):
        return _report("Compatibility Error", "invalid metadata")
    if payload.get("descriptive_only") is not True:
        return _report("Execution Boundary Error", "execution request must be descriptive only")
    return _report(None, None)


def validate_execution_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a Runtime Resume Execution Result without side effects."""

    if not isinstance(result, Mapping):
        return _report("Compatibility Error", "execution result must be a mapping")
    payload = dict(result)
    if payload.get("contract") != EXECUTION_RESULT_CONTRACT:
        return _report("Compatibility Error", "invalid execution result contract")
    field_report = _validate_fields(payload, RESULT_REQUIRED_FIELDS, "execution result")
    if field_report is not None:
        return field_report
    safety_report = _validate_safe_values(payload, "execution result")
    if safety_report is not None:
        return safety_report
    if not _non_empty_text(payload.get("execution_request_id")):
        return _report("Identity Error", "invalid execution request identity")
    if not _non_empty_text(payload.get("resume_token")):
        return _report("Identity Error", "invalid resume token")
    if not isinstance(payload.get("snapshot_id"), (str, type(None))):
        return _report("Identity Error", "invalid snapshot identity")
    if not isinstance(payload.get("lineage"), Mapping):
        return _report("Lineage Error", "invalid lineage")
    if payload.get("status") not in ALLOWED_RESULT_STATUSES:
        return _report("Status Error", "invalid execution result status")
    if payload.get("reason") is not None and not isinstance(payload.get("reason"), str):
        return _report("Status Error", "invalid execution result reason")
    if not isinstance(payload.get("completed"), bool) or not isinstance(payload.get("failed"), bool):
        return _report("Status Error", "invalid completion flags")
    if payload.get("completed") is True and payload.get("failed") is True:
        return _report("Status Error", "completion flags conflict")
    failure = payload.get("failure")
    if failure is not None and validate_execution_failure(failure).get("valid") is not True:
        return _report("Runtime Execution Error", "invalid execution failure")
    if not isinstance(payload.get("downstream_handoff_required"), bool):
        return _report("Future Domain Required", "invalid downstream handoff flag")
    handoff_type = payload.get("downstream_handoff_type")
    if handoff_type is not None and handoff_type not in ALLOWED_HANDOFF_TYPES:
        return _report("Future Domain Required", "invalid downstream handoff type")
    if not isinstance(payload.get("metadata"), Mapping):
        return _report("Compatibility Error", "invalid metadata")
    if payload.get("descriptive_only") is not True:
        return _report("Execution Boundary Error", "execution result must be descriptive only")
    return _report(None, None)


def validate_execution_failure(failure: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a Runtime Resume Execution Failure without side effects."""

    if not isinstance(failure, Mapping):
        return _report("Compatibility Error", "execution failure must be a mapping")
    payload = dict(failure)
    if payload.get("contract") != EXECUTION_FAILURE_CONTRACT:
        return _report("Compatibility Error", "invalid execution failure contract")
    field_report = _validate_fields(payload, FAILURE_REQUIRED_FIELDS, "execution failure")
    if field_report is not None:
        return field_report
    safety_report = _validate_safe_values(payload, "execution failure")
    if safety_report is not None:
        return safety_report
    if payload.get("failure_code") not in ALLOWED_FAILURE_CODES:
        return _report("Status Error", "invalid failure code")
    if payload.get("category") not in ALLOWED_FAILURE_CATEGORIES:
        return _report("Compatibility Error", "invalid failure category")
    if payload.get("owner") not in ALLOWED_FAILURE_OWNERS:
        return _report("Ownership Violation", "invalid failure owner")
    if not isinstance(payload.get("reason"), str):
        return _report("Runtime Execution Error", "invalid failure reason")
    if not isinstance(payload.get("recoverable"), bool):
        return _report("Runtime Execution Error", "invalid recoverable flag")
    downstream_owner = payload.get("downstream_owner")
    if downstream_owner is not None and downstream_owner not in ALLOWED_FAILURE_OWNERS:
        return _report("Ownership Violation", "invalid downstream owner")
    if not isinstance(payload.get("metadata"), Mapping):
        return _report("Compatibility Error", "invalid metadata")
    if payload.get("descriptive_only") is not True:
        return _report("Execution Boundary Error", "execution failure must be descriptive only")
    return _report(None, None)


def execution_request_to_summary(request: Mapping[str, Any]) -> dict[str, Any]:
    """Project an execution request to a stable public validation summary."""

    payload = _mapping_copy(request)
    return {
        "contract": EXECUTION_REQUEST_CONTRACT,
        "valid": validate_execution_request(payload).get("valid") is True,
        "execution_request_id": payload.get("execution_request_id"),
        "resume_token": payload.get("resume_token"),
        "snapshot_id": payload.get("snapshot_id"),
        "source_contract": payload.get("source_contract"),
        "source_status": payload.get("source_status"),
        "execution_allowed": payload.get("execution_allowed") is True,
        "requested_action": payload.get("requested_action"),
    }


def execution_result_to_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    """Project an execution result to a stable public validation summary."""

    payload = _mapping_copy(result)
    return {
        "contract": EXECUTION_RESULT_CONTRACT,
        "valid": validate_execution_result(payload).get("valid") is True,
        "execution_request_id": payload.get("execution_request_id"),
        "resume_token": payload.get("resume_token"),
        "snapshot_id": payload.get("snapshot_id"),
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "completed": payload.get("completed") is True,
        "failed": payload.get("failed") is True,
        "downstream_handoff_required": payload.get("downstream_handoff_required") is True,
        "downstream_handoff_type": payload.get("downstream_handoff_type"),
    }


def execution_failure_to_summary(failure: Mapping[str, Any]) -> dict[str, Any]:
    """Project an execution failure to a stable public validation summary."""

    payload = _mapping_copy(failure)
    return {
        "contract": EXECUTION_FAILURE_CONTRACT,
        "valid": validate_execution_failure(payload).get("valid") is True,
        "failure_code": payload.get("failure_code"),
        "category": payload.get("category"),
        "owner": payload.get("owner"),
        "reason": payload.get("reason"),
        "recoverable": payload.get("recoverable") is True,
        "downstream_owner": payload.get("downstream_owner"),
    }


def _validate_fields(payload: Mapping[str, Any], required: frozenset[str], label: str) -> dict[str, Any] | None:
    fields = set(payload)
    if not required <= fields:
        return _report("Compatibility Error", f"missing {label} fields")
    if fields != required:
        return _report("Compatibility Error", f"unknown {label} fields")
    return None


def _validate_safe_values(value: Any, label: str) -> dict[str, Any] | None:
    if _contains_callable(value):
        return _report("Execution Boundary Error", f"{label} contains executable value")
    return None


def _contains_callable(value: Any) -> bool:
    if callable(value):
        return True
    if isinstance(value, Mapping):
        return any(_contains_callable(item) for item in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_callable(item) for item in value)
    return False


def _mapping_copy(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _report(category: str | None, reason: str | None) -> dict[str, Any]:
    return {
        "valid": category is None,
        "category": category,
        "reason": reason,
        "auto_repair_allowed": False,
        "descriptive_only": True,
    }
