"""Passive Runtime Recovery binding candidate reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


RECOVERY_BINDING_CANDIDATE_CONTRACT = "aer.runtime.recovery.binding_candidate.v1"
RECOVERY_BINDING_CANDIDATE_ENTRY = "runtime_recovery_single_entry"
RECOVERY_BINDING_CANDIDATE_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_BINDING_CANDIDATE_DENIED_CAPABILITIES = (
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
    "RECOVERY_BINDING_CANDIDATE_CONTRACT",
    "RECOVERY_BINDING_CANDIDATE_ENTRY",
    "RECOVERY_BINDING_CANDIDATE_ALLOWED_STATUSES",
    "RECOVERY_BINDING_CANDIDATE_DENIED_CAPABILITIES",
    "prepare_recovery_binding_candidate_report",
]


def prepare_recovery_binding_candidate_report(
    binding_plan_report: Mapping[str, Any],
    *,
    candidate_id: str | None = None,
    requested_status: str = "prepared",
    requested_entry: str = RECOVERY_BINDING_CANDIDATE_ENTRY,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare a passive binding candidate without applying any binding."""

    plan = _plain_mapping(binding_plan_report)
    single_entry = requested_entry == RECOVERY_BINDING_CANDIDATE_ENTRY
    valid_plan = _valid_binding_plan(plan)
    valid = valid_plan and single_entry
    denied = requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_BINDING_CANDIDATE_CONTRACT,
        "candidate_id": candidate_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "single_entry_only": True,
        "candidate_entry": RECOVERY_BINDING_CANDIDATE_ENTRY if single_entry else None,
        "candidate_created": prepared,
        "binding_candidate": True,
        "binding_plan_required": True,
        "binding_plan_reference": plan if valid_plan else {},
        "binding_application_allowed": False,
        "binding_registered": False,
        "runtime_bound": False,
        "runtime_mainline_wiring_enabled": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "approval_required": True,
        "denied_capabilities": list(RECOVERY_BINDING_CANDIDATE_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, single_entry, valid_plan),
        "metadata": _plain_mapping(metadata),
        "candidate_report_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_binding_plan(value: Mapping[str, Any]) -> bool:
    return (
        value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("single_entry_only") is True
        and value.get("event_emitted") is False
        and value.get("recovery_enabled") is False
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
        and value.get("runtime_mainline_wiring_enabled") is False
    )


def _reason(requested_status: str, valid: bool, single_entry: bool, valid_plan: bool) -> str | None:
    if requested_status == "denied":
        return "caller requested passive denied binding candidate status"
    if not single_entry:
        return "binding candidate allows only runtime_recovery_single_entry"
    if not valid_plan:
        return "missing or incompatible passive Recovery binding plan report"
    if requested_status == "blocked":
        return "caller requested passive blocked binding candidate status"
    if requested_status != "prepared":
        return f"unsupported passive binding candidate status: {requested_status}"
    if not valid:
        return "binding candidate could not be prepared"
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
