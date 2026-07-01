"""Pure Runtime Resume Execution consumer boundary helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime import aer_runtime_resume_execution_validation as _validation
from core.runtime.aer_runtime_resume_execution_validation import (
    EXECUTION_FAILURE_CONTRACT,
    EXECUTION_REQUEST_CONTRACT,
    EXECUTION_RESULT_CONTRACT,
)

EXECUTION_CONSUMER_INPUT_CONTRACT = "aer.runtime.resume.execution_consumer_input.v1"
EXECUTION_CONSUMER_OUTPUT_CONTRACT = "aer.runtime.resume.execution_consumer_output.v1"
EXECUTION_CONSUMER_BOUNDARY_CONTRACT = "aer.runtime.resume.execution_consumer_boundary.v1"

_INPUT_REQUIRED_FIELDS = frozenset(
    {
        "contract",
        "source_contract",
        "source_valid",
        "source_kind",
        "execution_request_id",
        "resume_token",
        "snapshot_id",
        "status",
        "reason",
        "completed",
        "failed",
        "downstream_handoff_required",
        "downstream_handoff_type",
        "consumer_boundary",
        "descriptive_only",
    }
)

_OUTPUT_REQUIRED_FIELDS = frozenset(
    {
        "contract",
        "accepted_for_future_domain",
        "blocked",
        "status",
        "reason",
        "execution_request_id",
        "resume_token",
        "snapshot_id",
        "source_kind",
        "downstream_handoff_required",
        "downstream_handoff_type",
        "consumer_boundary",
        "descriptive_only",
    }
)

_BOUNDARY_REQUIRED_FIELDS = frozenset(
    {
        "contract",
        "future_domain_only",
        "execution_allowed",
        "downstream_authorized",
        "allowed_future_domains",
        "reason",
    }
)

_ALLOWED_SOURCE_KINDS = frozenset({"execution_request", "execution_result", "execution_failure"})
_ALLOWED_OUTPUT_STATUSES = frozenset(
    {
        "accepted_for_future_domain",
        "blocked",
        "invalid_consumer_input",
        "invalid_execution_summary",
        "future_domain_required",
        "execution_not_authorized",
    }
)
_ALLOWED_HANDOFF_TYPES = frozenset(
    {"recovery", "scheduler", "dispatcher", "operator", "persistence", "audit", "journal", "replay"}
)

__all__ = [
    "EXECUTION_CONSUMER_INPUT_CONTRACT",
    "EXECUTION_CONSUMER_OUTPUT_CONTRACT",
    "EXECUTION_CONSUMER_BOUNDARY_CONTRACT",
    "build_execution_consumer_input",
    "validate_execution_consumer_input",
    "build_execution_consumer_output",
    "validate_execution_consumer_output",
    "execution_consumer_input_to_summary",
    "execution_consumer_output_to_summary",
]


def build_execution_consumer_input(source_summary: Mapping[str, Any]) -> dict[str, Any]:
    """Build a downstream-safe consumer input from an execution summary.

    The returned payload is a data-only boundary descriptor. It does not run
    resume execution and does not authorize any downstream domain.
    """

    source = _mapping_copy(source_summary)
    source_contract = _text_or_none(source.get("contract"))
    source_kind = _source_kind(source_contract)
    downstream_type = _text_or_none(source.get("downstream_handoff_type"))
    downstream_required = source.get("downstream_handoff_required") is True
    return {
        "contract": EXECUTION_CONSUMER_INPUT_CONTRACT,
        "source_contract": source_contract,
        "source_valid": source.get("valid") is True,
        "source_kind": source_kind,
        "execution_request_id": _text_or_none(source.get("execution_request_id")),
        "resume_token": _text_or_none(source.get("resume_token")),
        "snapshot_id": _text_or_none(source.get("snapshot_id")),
        "status": _source_status(source),
        "reason": _text_or_none(source.get("reason")),
        "completed": source.get("completed") is True,
        "failed": source.get("failed") is True,
        "downstream_handoff_required": downstream_required,
        "downstream_handoff_type": downstream_type if downstream_required else None,
        "consumer_boundary": _consumer_boundary(),
        "descriptive_only": True,
    }


def validate_execution_consumer_input(consumer_input: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a Runtime Resume Execution consumer input descriptor."""

    if not isinstance(consumer_input, Mapping):
        return _report("Execution Consumer Error", "consumer input must be a mapping")
    payload = dict(consumer_input)
    if payload.get("contract") != EXECUTION_CONSUMER_INPUT_CONTRACT:
        return _report("Compatibility Error", "invalid execution consumer input contract")
    field_report = _validate_fields(payload, _INPUT_REQUIRED_FIELDS, "consumer input")
    if field_report is not None:
        return field_report
    safety_report = _validate_safe_values(payload, "consumer input")
    if safety_report is not None:
        return safety_report
    if payload.get("source_contract") not in {
        EXECUTION_REQUEST_CONTRACT,
        EXECUTION_RESULT_CONTRACT,
        EXECUTION_FAILURE_CONTRACT,
    }:
        return _report("Compatibility Error", "invalid execution source contract")
    if not isinstance(payload.get("source_valid"), bool):
        return _report("Execution Consumer Error", "invalid source validity flag")
    if payload.get("source_kind") not in _ALLOWED_SOURCE_KINDS:
        return _report("Compatibility Error", "invalid source kind")
    if (
        not _non_empty_text(payload.get("execution_request_id"))
        and payload.get("source_kind") != "execution_failure"
        and payload.get("status") != "invalid_consumer_input"
    ):
        return _report("Identity Error", "invalid execution request identity")
    if payload.get("resume_token") is not None and not isinstance(payload.get("resume_token"), str):
        return _report("Identity Error", "invalid resume token")
    if payload.get("snapshot_id") is not None and not isinstance(payload.get("snapshot_id"), str):
        return _report("Identity Error", "invalid snapshot identity")
    if payload.get("status") is not None and not isinstance(payload.get("status"), str):
        return _report("Status Error", "invalid source status")
    if payload.get("reason") is not None and not isinstance(payload.get("reason"), str):
        return _report("Status Error", "invalid source reason")
    if not isinstance(payload.get("completed"), bool) or not isinstance(payload.get("failed"), bool):
        return _report("Status Error", "invalid source completion flags")
    if not isinstance(payload.get("downstream_handoff_required"), bool):
        return _report("Future Domain Required", "invalid downstream handoff flag")
    handoff_type = payload.get("downstream_handoff_type")
    if handoff_type is not None and handoff_type not in _ALLOWED_HANDOFF_TYPES:
        return _report("Future Domain Required", "invalid downstream handoff type")
    if not _valid_consumer_boundary(payload.get("consumer_boundary")):
        return _report("Execution Boundary Error", "invalid execution consumer boundary")
    if payload.get("descriptive_only") is not True:
        return _report("Execution Boundary Error", "consumer input must be descriptive only")
    return _report(None, None)


def build_execution_consumer_output(consumer_input: Mapping[str, Any]) -> dict[str, Any]:
    """Build a data-only consumer output descriptor from consumer input."""

    payload = _mapping_copy(consumer_input)
    valid_input = validate_execution_consumer_input(payload).get("valid") is True
    source_valid = payload.get("source_valid") is True
    downstream_required = payload.get("downstream_handoff_required") is True
    if not valid_input:
        status = "invalid_consumer_input"
        reason = "invalid execution consumer input"
    elif not source_valid:
        status = "invalid_execution_summary"
        reason = "invalid execution summary"
    elif downstream_required:
        status = "future_domain_required"
        reason = "downstream handoff requires future domain contract"
    else:
        status = "accepted_for_future_domain"
        reason = None
    accepted = status == "accepted_for_future_domain"
    return {
        "contract": EXECUTION_CONSUMER_OUTPUT_CONTRACT,
        "accepted_for_future_domain": accepted,
        "blocked": not accepted,
        "status": status,
        "reason": reason,
        "execution_request_id": payload.get("execution_request_id"),
        "resume_token": payload.get("resume_token"),
        "snapshot_id": payload.get("snapshot_id"),
        "source_kind": payload.get("source_kind"),
        "downstream_handoff_required": downstream_required if valid_input else False,
        "downstream_handoff_type": payload.get("downstream_handoff_type") if downstream_required and valid_input else None,
        "consumer_boundary": _consumer_boundary_summary(payload.get("consumer_boundary")),
        "descriptive_only": True,
    }


def validate_execution_consumer_output(consumer_output: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a Runtime Resume Execution consumer output descriptor."""

    if not isinstance(consumer_output, Mapping):
        return _report("Execution Consumer Error", "consumer output must be a mapping")
    payload = dict(consumer_output)
    if payload.get("contract") != EXECUTION_CONSUMER_OUTPUT_CONTRACT:
        return _report("Compatibility Error", "invalid execution consumer output contract")
    field_report = _validate_fields(payload, _OUTPUT_REQUIRED_FIELDS, "consumer output")
    if field_report is not None:
        return field_report
    safety_report = _validate_safe_values(payload, "consumer output")
    if safety_report is not None:
        return safety_report
    if not isinstance(payload.get("accepted_for_future_domain"), bool) or not isinstance(payload.get("blocked"), bool):
        return _report("Status Error", "invalid consumer output flags")
    if payload.get("accepted_for_future_domain") == payload.get("blocked"):
        return _report("Status Error", "consumer output flags conflict")
    if payload.get("status") not in _ALLOWED_OUTPUT_STATUSES:
        return _report("Status Error", "invalid consumer output status")
    if payload.get("reason") is not None and not isinstance(payload.get("reason"), str):
        return _report("Status Error", "invalid consumer output reason")
    if (
        not _non_empty_text(payload.get("execution_request_id"))
        and payload.get("source_kind") != "execution_failure"
        and payload.get("status") != "invalid_consumer_input"
    ):
        return _report("Identity Error", "invalid execution request identity")
    if payload.get("resume_token") is not None and not isinstance(payload.get("resume_token"), str):
        return _report("Identity Error", "invalid resume token")
    if payload.get("snapshot_id") is not None and not isinstance(payload.get("snapshot_id"), str):
        return _report("Identity Error", "invalid snapshot identity")
    if (
        payload.get("source_kind") not in _ALLOWED_SOURCE_KINDS
        and payload.get("status") != "invalid_consumer_input"
    ):
        return _report("Compatibility Error", "invalid source kind")
    if not isinstance(payload.get("downstream_handoff_required"), bool):
        return _report("Future Domain Required", "invalid downstream handoff flag")
    handoff_type = payload.get("downstream_handoff_type")
    if handoff_type is not None and handoff_type not in _ALLOWED_HANDOFF_TYPES:
        return _report("Future Domain Required", "invalid downstream handoff type")
    if not _valid_consumer_boundary(payload.get("consumer_boundary")):
        return _report("Execution Boundary Error", "invalid execution consumer boundary")
    if payload.get("descriptive_only") is not True:
        return _report("Execution Boundary Error", "consumer output must be descriptive only")
    return _report(None, None)


def execution_consumer_input_to_summary(consumer_input: Mapping[str, Any]) -> dict[str, Any]:
    """Project consumer input to a stable public summary."""

    payload = _mapping_copy(consumer_input)
    return {
        "contract": EXECUTION_CONSUMER_INPUT_CONTRACT,
        "valid": validate_execution_consumer_input(payload).get("valid") is True,
        "source_contract": payload.get("source_contract"),
        "source_valid": payload.get("source_valid") is True,
        "source_kind": payload.get("source_kind"),
        "execution_request_id": payload.get("execution_request_id"),
        "resume_token": payload.get("resume_token"),
        "snapshot_id": payload.get("snapshot_id"),
        "status": payload.get("status"),
        "downstream_handoff_required": payload.get("downstream_handoff_required") is True,
        "downstream_handoff_type": payload.get("downstream_handoff_type"),
    }


def execution_consumer_output_to_summary(consumer_output: Mapping[str, Any]) -> dict[str, Any]:
    """Project consumer output to a stable public summary."""

    payload = _mapping_copy(consumer_output)
    return {
        "contract": EXECUTION_CONSUMER_OUTPUT_CONTRACT,
        "valid": validate_execution_consumer_output(payload).get("valid") is True,
        "accepted_for_future_domain": payload.get("accepted_for_future_domain") is True,
        "blocked": payload.get("blocked") is True,
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "execution_request_id": payload.get("execution_request_id"),
        "resume_token": payload.get("resume_token"),
        "snapshot_id": payload.get("snapshot_id"),
        "source_kind": payload.get("source_kind"),
        "downstream_handoff_required": payload.get("downstream_handoff_required") is True,
        "downstream_handoff_type": payload.get("downstream_handoff_type"),
    }


def _source_kind(contract: str | None) -> str:
    if contract == EXECUTION_REQUEST_CONTRACT:
        return "execution_request"
    if contract == EXECUTION_RESULT_CONTRACT:
        return "execution_result"
    if contract == EXECUTION_FAILURE_CONTRACT:
        return "execution_failure"
    return "invalid"


def _source_status(source: Mapping[str, Any]) -> str | None:
    if source.get("status") is not None:
        return _text_or_none(source.get("status"))
    if source.get("requested_action") is not None:
        return _text_or_none(source.get("requested_action"))
    if source.get("failure_code") is not None:
        return _text_or_none(source.get("failure_code"))
    return None


def _consumer_boundary() -> dict[str, Any]:
    return {
        "contract": EXECUTION_CONSUMER_BOUNDARY_CONTRACT,
        "future_domain_only": True,
        "execution_allowed": False,
        "downstream_authorized": False,
        "allowed_future_domains": [
            "Future Runtime Resume Execution",
            "Future Recovery",
            "Future Scheduler",
            "Future Dispatcher",
            "Future Operator",
        ],
        "reason": "downstream consumption requires future domain contracts",
    }


def _consumer_boundary_summary(value: Any) -> dict[str, Any]:
    boundary = _mapping_copy(value)
    if _valid_consumer_boundary(boundary):
        return dict(boundary)
    return _consumer_boundary()


def _valid_consumer_boundary(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    payload = dict(value)
    if set(payload) != _BOUNDARY_REQUIRED_FIELDS:
        return False
    if payload.get("contract") != EXECUTION_CONSUMER_BOUNDARY_CONTRACT:
        return False
    if payload.get("future_domain_only") is not True:
        return False
    if payload.get("execution_allowed") is not False:
        return False
    if payload.get("downstream_authorized") is not False:
        return False
    if not _descriptive_string_list(payload.get("allowed_future_domains")):
        return False
    if not _non_empty_text(payload.get("reason")):
        return False
    return not _contains_callable(payload)


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


def _descriptive_string_list(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    return all(isinstance(item, str) and bool(item.strip()) for item in value)


def _mapping_copy(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _text_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    return None


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
