"""Passive Runtime Recovery preflight eligibility reports.

The helper consumes an observe-only Recovery observation report and returns
eligibility data for future integration planning. It never executes Recovery,
emits events, mutates runtime state, binds runtime, or calls runtime surfaces.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_observation_report import (
    RECOVERY_OBSERVATION_REPORT_CONTRACT,
)


RECOVERY_PREFLIGHT_ELIGIBILITY_CONTRACT = "aer.runtime.recovery.preflight_eligibility.v1"
RECOVERY_PREFLIGHT_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_PREFLIGHT_DENIED_CAPABILITIES = (
    "recovery_execution",
    "recovery_enablement",
    "runtime_mainline_wiring",
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
    "RECOVERY_PREFLIGHT_ELIGIBILITY_CONTRACT",
    "RECOVERY_PREFLIGHT_ALLOWED_STATUSES",
    "RECOVERY_PREFLIGHT_DENIED_CAPABILITIES",
    "prepare_recovery_preflight_eligibility",
]


def prepare_recovery_preflight_eligibility(
    observation_report: Mapping[str, Any],
    *,
    preflight_id: str | None = None,
    requested_status: str = "prepared",
    request_enablement: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare non-executing Recovery preflight eligibility data."""

    observation = _plain_mapping(observation_report)
    valid = _valid_observation(observation)
    denied = request_enablement or requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_PREFLIGHT_ELIGIBILITY_CONTRACT,
        "preflight_id": preflight_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "preflight_only": True,
        "eligible": prepared,
        "eligibility_state": "eligible" if prepared else "denied" if denied else "blocked",
        "observe_only": True,
        "dry_run": True,
        "single_entry_only": True,
        "runtime_binding_allowed": False,
        "runtime_mainline_wiring_allowed": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "canonical_event": _plain_mapping(observation.get("canonical_event")) if valid else {},
        "observation_reference": observation if valid else {},
        "denied_capabilities": list(RECOVERY_PREFLIGHT_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, request_enablement),
        "metadata": _plain_mapping(metadata),
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
        and value.get("single_entry_only") is True
        and value.get("runtime_surface_touched") is False
        and value.get("surface_probe_executed") is False
        and value.get("event_emitted") is False
        and value.get("recovery_enabled") is False
        and event.get("event_emitted") is False
        and value.get("observation_report_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid: bool, request_enablement: bool) -> str | None:
    if request_enablement:
        return "Recovery enablement is prohibited during preflight eligibility"
    if requested_status == "denied":
        return "caller requested passive denied preflight status"
    if not valid:
        return "missing or incompatible observe-only Recovery observation report"
    if requested_status == "blocked":
        return "caller requested passive blocked preflight status"
    if requested_status != "prepared":
        return f"unsupported passive preflight status: {requested_status}"
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
