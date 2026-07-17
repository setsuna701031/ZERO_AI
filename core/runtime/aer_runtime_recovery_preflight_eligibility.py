"""Non-executing Runtime Recovery preflight eligibility reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_dry_run_binding import RECOVERY_DRY_RUN_BINDING_ENTRY
from core.runtime.aer_runtime_recovery_event_route import RECOVERY_CANONICAL_EVENT_CONTRACT
from core.runtime.aer_runtime_recovery_observation_report import RECOVERY_OBSERVATION_REPORT_CONTRACT


RECOVERY_PREFLIGHT_ELIGIBILITY_REPORT_CONTRACT = "aer.runtime.recovery.preflight_eligibility_report.v1"
RECOVERY_PREFLIGHT_ELIGIBILITY_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_PREFLIGHT_ELIGIBILITY_DENIED_CAPABILITIES = (
    "recovery_execution",
    "recovery_enablement",
    "runtime_mainline_wiring",
    "runtime_binding",
    "route_activation",
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
    "RECOVERY_PREFLIGHT_ELIGIBILITY_REPORT_CONTRACT",
    "RECOVERY_PREFLIGHT_ELIGIBILITY_ALLOWED_STATUSES",
    "RECOVERY_PREFLIGHT_ELIGIBILITY_DENIED_CAPABILITIES",
    "prepare_recovery_preflight_eligibility_report",
]


def prepare_recovery_preflight_eligibility_report(
    observation_report: Mapping[str, Any],
    *,
    preflight_id: str | None = None,
    requested_status: str = "prepared",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare passive preflight eligibility data without binding or running Recovery."""

    observation = _plain_mapping(observation_report)
    valid = _valid_observation(observation)
    denied = requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"
    canonical_event = _plain_mapping(observation.get("canonical_event")) if valid else {}

    return {
        "contract": RECOVERY_PREFLIGHT_ELIGIBILITY_REPORT_CONTRACT,
        "preflight_id": preflight_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "preflight_only": True,
        "eligibility_checked": prepared,
        "eligibility_level": "non_executing_preflight",
        "single_entry_only": True,
        "preflight_entry": RECOVERY_DRY_RUN_BINDING_ENTRY if valid else None,
        "eligible_for_next_non_executing_phase": prepared,
        "eligible_for_runtime_binding": False,
        "eligible_for_recovery_execution": False,
        "runtime_binding_allowed": False,
        "recovery_execution_allowed": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "runtime_surface_touched": False,
        "canonical_event": canonical_event,
        "observation_reference": observation if valid else {},
        "preflight_requirements": _requirements(valid, observation, canonical_event),
        "denied_capabilities": list(RECOVERY_PREFLIGHT_ELIGIBILITY_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid),
        "metadata": _plain_mapping(metadata),
        "preflight_report_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_observation(value: Mapping[str, Any]) -> bool:
    event = _plain_mapping(value.get("canonical_event"))
    return (
        value.get("contract") == RECOVERY_OBSERVATION_REPORT_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("observe_only") is True
        and value.get("dry_run") is True
        and value.get("observation_complete") is True
        and value.get("single_entry_only") is True
        and value.get("observation_entry") == RECOVERY_DRY_RUN_BINDING_ENTRY
        and value.get("runtime_surface_touched") is False
        and value.get("surface_probe_executed") is False
        and value.get("event_emitted") is False
        and value.get("recovery_enabled") is False
        and event.get("contract") == RECOVERY_CANONICAL_EVENT_CONTRACT
        and event.get("entry_id") == RECOVERY_DRY_RUN_BINDING_ENTRY
        and event.get("event_emitted") is False
        and value.get("observation_report_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _requirements(
    valid: bool,
    observation: Mapping[str, Any],
    canonical_event: Mapping[str, Any],
) -> dict[str, bool]:
    return {
        "observation_report_valid": valid,
        "single_entry_preserved": observation.get("observation_entry") == RECOVERY_DRY_RUN_BINDING_ENTRY,
        "canonical_event_preserved": canonical_event.get("contract") == RECOVERY_CANONICAL_EVENT_CONTRACT,
        "event_not_emitted": observation.get("event_emitted") is False and canonical_event.get("event_emitted") is False,
        "runtime_surface_not_touched": observation.get("runtime_surface_touched") is False,
        "recovery_disabled": observation.get("recovery_enabled") is False,
        "execution_denied": observation.get("executes_recovery") is False,
        "plain_dict_preserved": observation.get("plain_dict_only") is True,
    }


def _reason(requested_status: str, valid: bool) -> str | None:
    if requested_status == "denied":
        return "caller requested passive denied preflight eligibility status"
    if not valid:
        return "missing or incompatible passive Recovery observation report"
    if requested_status == "blocked":
        return "caller requested passive blocked preflight eligibility status"
    if requested_status != "prepared":
        return f"unsupported passive preflight eligibility status: {requested_status}"
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
