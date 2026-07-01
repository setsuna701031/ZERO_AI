"""Passive Runtime Recovery binding approval reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_binding_candidate import RECOVERY_BINDING_CANDIDATE_ENTRY
from core.runtime.aer_runtime_recovery_binding_validator import RECOVERY_BINDING_VALIDATOR_REPORT_CONTRACT


RECOVERY_BINDING_APPROVAL_REPORT_CONTRACT = "aer.runtime.recovery.binding_approval_report.v1"
RECOVERY_BINDING_APPROVAL_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_BINDING_APPROVAL_DENIED_CAPABILITIES = (
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
    "RECOVERY_BINDING_APPROVAL_REPORT_CONTRACT",
    "RECOVERY_BINDING_APPROVAL_ALLOWED_STATUSES",
    "RECOVERY_BINDING_APPROVAL_DENIED_CAPABILITIES",
    "prepare_recovery_binding_approval_report",
]


def prepare_recovery_binding_approval_report(
    binding_validator_report: Mapping[str, Any],
    *,
    approval_id: str | None = None,
    requested_status: str = "prepared",
    approval_granted: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare passive approval data without granting runtime binding authority."""

    validator = _plain_mapping(binding_validator_report)
    valid_validator = _valid_validator(validator)
    denied = approval_granted or requested_status == "denied"
    prepared = valid_validator and requested_status == "prepared" and not denied
    blocked = (not valid_validator and not denied) or (valid_validator and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_BINDING_APPROVAL_REPORT_CONTRACT,
        "approval_id": approval_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "single_entry_only": True,
        "approval_report_prepared": prepared,
        "approval_granted": False,
        "approval_required": True,
        "candidate_entry": RECOVERY_BINDING_CANDIDATE_ENTRY if valid_validator else None,
        "binding_validator_reference": validator if valid_validator else {},
        "binding_application_allowed": False,
        "binding_registered": False,
        "runtime_bound": False,
        "runtime_mainline_wiring_enabled": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "denied_capabilities": list(RECOVERY_BINDING_APPROVAL_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid_validator, approval_granted),
        "metadata": _plain_mapping(metadata),
        "approval_report_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_validator(value: Mapping[str, Any]) -> bool:
    return (
        value.get("contract") == RECOVERY_BINDING_VALIDATOR_REPORT_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("single_entry_only") is True
        and value.get("candidate_valid") is True
        and value.get("candidate_entry") == RECOVERY_BINDING_CANDIDATE_ENTRY
        and value.get("policy_validated") is True
        and value.get("preflight_validated") is True
        and value.get("registry_validated") is True
        and value.get("framework_validated") is True
        and value.get("approval_required") is True
        and value.get("binding_application_allowed") is False
        and value.get("binding_registered") is False
        and value.get("runtime_bound") is False
        and value.get("runtime_mainline_wiring_enabled") is False
        and value.get("event_emitted") is False
        and value.get("recovery_enabled") is False
        and value.get("validator_report_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid_validator: bool, approval_granted: bool) -> str | None:
    if approval_granted:
        return "granting binding approval is prohibited in this package"
    if requested_status == "denied":
        return "caller requested passive denied binding approval status"
    if not valid_validator:
        return "missing or incompatible passive Recovery binding validator report"
    if requested_status == "blocked":
        return "caller requested passive blocked binding approval status"
    if requested_status != "prepared":
        return f"unsupported passive binding approval status: {requested_status}"
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
