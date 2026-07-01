"""Passive Runtime Recovery preflight readiness reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_preflight import (
    RECOVERY_PREFLIGHT_ELIGIBILITY_CONTRACT,
    RECOVERY_PREFLIGHT_DENIED_CAPABILITIES,
)


RECOVERY_PREFLIGHT_REPORT_CONTRACT = "aer.runtime.recovery.preflight_report.v1"
RECOVERY_PREFLIGHT_REPORT_ALLOWED_STATUSES = ("prepared", "blocked", "denied")

__all__ = [
    "RECOVERY_PREFLIGHT_REPORT_CONTRACT",
    "RECOVERY_PREFLIGHT_REPORT_ALLOWED_STATUSES",
    "prepare_recovery_preflight_report",
]


def prepare_recovery_preflight_report(
    preflight_eligibility_report: Mapping[str, Any],
    *,
    report_id: str | None = None,
    requested_status: str = "prepared",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare deterministic non-executing preflight report data."""

    preflight = _plain_mapping(preflight_eligibility_report)
    valid = _valid_preflight(preflight)
    denied = requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_PREFLIGHT_REPORT_CONTRACT,
        "report_id": report_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "preflight_report_only": True,
        "eligible": prepared,
        "eligibility_state": "eligible" if prepared else "denied" if denied else "blocked",
        "observe_only": True,
        "dry_run": True,
        "single_entry_only": True,
        "runtime_binding_allowed": False,
        "runtime_mainline_wiring_allowed": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "canonical_event": _plain_mapping(preflight.get("canonical_event")) if valid else {},
        "preflight_reference": preflight if valid else {},
        "denied_capabilities": list(RECOVERY_PREFLIGHT_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid),
        "metadata": _plain_mapping(metadata),
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_preflight(value: Mapping[str, Any]) -> bool:
    event = _plain_mapping(value.get("canonical_event"))
    return (
        value.get("contract") == RECOVERY_PREFLIGHT_ELIGIBILITY_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("preflight_only") is True
        and value.get("eligible") is True
        and value.get("eligibility_state") == "eligible"
        and value.get("observe_only") is True
        and value.get("dry_run") is True
        and value.get("single_entry_only") is True
        and value.get("runtime_binding_allowed") is False
        and value.get("runtime_mainline_wiring_allowed") is False
        and value.get("event_emitted") is False
        and value.get("recovery_enabled") is False
        and event.get("event_emitted") is False
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid: bool) -> str | None:
    if requested_status == "denied":
        return "caller requested passive denied preflight report status"
    if not valid:
        return "missing or incompatible Recovery preflight eligibility report"
    if requested_status == "blocked":
        return "caller requested passive blocked preflight report status"
    if requested_status != "prepared":
        return f"unsupported passive preflight report status: {requested_status}"
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
