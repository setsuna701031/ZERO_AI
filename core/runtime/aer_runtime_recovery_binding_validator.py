"""Passive Runtime Recovery binding candidate validation reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_binding_candidate import (
    RECOVERY_BINDING_CANDIDATE_CONTRACT,
    RECOVERY_BINDING_CANDIDATE_ENTRY,
)


RECOVERY_BINDING_VALIDATOR_REPORT_CONTRACT = "aer.runtime.recovery.binding_validator_report.v1"
RECOVERY_BINDING_VALIDATOR_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_BINDING_VALIDATOR_DENIED_CAPABILITIES = (
    "recovery_execution",
    "recovery_enablement",
    "runtime_mainline_wiring",
    "binding_application",
    "binding_registration",
    "event_emission",
    "scheduler_call",
    "operator_call",
    "dispatcher_call",
    "supervisor_call",
    "native_runtime_call",
    "runtime_mutation",
    "persistence_write",
    "replay_action",
    "audit_emission",
    "journal_event",
    "subprocess_call",
    "file_io",
)

__all__ = [
    "RECOVERY_BINDING_VALIDATOR_REPORT_CONTRACT",
    "RECOVERY_BINDING_VALIDATOR_ALLOWED_STATUSES",
    "RECOVERY_BINDING_VALIDATOR_DENIED_CAPABILITIES",
    "validate_recovery_binding_candidate_report",
]


def validate_recovery_binding_candidate_report(
    binding_candidate_report: Mapping[str, Any],
    *,
    validator_id: str | None = None,
    requested_status: str = "prepared",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a passive binding candidate without applying it."""

    candidate = _plain_mapping(binding_candidate_report)
    valid_candidate = _valid_candidate(candidate)
    denied = requested_status == "denied"
    prepared = valid_candidate and requested_status == "prepared" and not denied
    blocked = (not valid_candidate and not denied) or (valid_candidate and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_BINDING_VALIDATOR_REPORT_CONTRACT,
        "validator_id": validator_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "single_entry_only": True,
        "candidate_valid": prepared,
        "candidate_entry": RECOVERY_BINDING_CANDIDATE_ENTRY if valid_candidate else None,
        "binding_candidate_reference": candidate if valid_candidate else {},
        "policy_validated": prepared,
        "preflight_validated": prepared,
        "registry_validated": prepared,
        "framework_validated": prepared,
        "approval_required": True,
        "binding_application_allowed": False,
        "binding_registered": False,
        "runtime_bound": False,
        "runtime_mainline_wiring_enabled": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "denied_capabilities": list(RECOVERY_BINDING_VALIDATOR_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid_candidate),
        "metadata": _plain_mapping(metadata),
        "validator_report_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_candidate(value: Mapping[str, Any]) -> bool:
    return (
        value.get("contract") == RECOVERY_BINDING_CANDIDATE_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("single_entry_only") is True
        and value.get("candidate_entry") == RECOVERY_BINDING_CANDIDATE_ENTRY
        and value.get("binding_candidate") is True
        and value.get("binding_application_allowed") is False
        and value.get("binding_registered") is False
        and value.get("runtime_bound") is False
        and value.get("runtime_mainline_wiring_enabled") is False
        and value.get("event_emitted") is False
        and value.get("recovery_enabled") is False
        and value.get("approval_required") is True
        and value.get("candidate_report_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid_candidate: bool) -> str | None:
    if requested_status == "denied":
        return "caller requested passive denied binding validator status"
    if not valid_candidate:
        return "missing or incompatible passive Recovery binding candidate report"
    if requested_status == "blocked":
        return "caller requested passive blocked binding validator status"
    if requested_status != "prepared":
        return f"unsupported passive binding validator status: {requested_status}"
    return None


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
