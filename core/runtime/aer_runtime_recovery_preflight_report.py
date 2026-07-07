"""Passive Runtime Recovery preflight readiness reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_preflight_eligibility import (
    RECOVERY_PREFLIGHT_ELIGIBILITY_REPORT_CONTRACT,
)

RECOVERY_PREFLIGHT_REPORT_CONTRACT = "aer.runtime.recovery.preflight_report.v1"
RECOVERY_PREFLIGHT_REPORT_ALLOWED_STATUSES = ("prepared", "blocked", "denied")

RECOVERY_PREFLIGHT_DENIED_CAPABILITIES = (
    "runtime_binding",
    "runtime_execution",
    "runtime_mutation",
)

_COMPATIBLE_PREFLIGHT_ELIGIBILITY_CONTRACTS = frozenset(
    {
        RECOVERY_PREFLIGHT_ELIGIBILITY_REPORT_CONTRACT,
        "aer.runtime.recovery.preflight_eligibility.v1",
        "zero.runtime.recovery.preflight_eligibility.v1",
        "zero.runtime.recovery.preflight_eligibility_report.v1",
    }
)

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
    """Prepare a passive, data-only Runtime Recovery preflight report."""

    eligibility = _plain_mapping(preflight_eligibility_report)
    valid = eligibility.get("contract") in _COMPATIBLE_PREFLIGHT_ELIGIBILITY_CONTRACTS
    requested_status_valid = requested_status in RECOVERY_PREFLIGHT_REPORT_ALLOWED_STATUSES

    denied = requested_status == "denied"
    prepared = valid and requested_status == "prepared"
    blocked = not prepared and not denied
    status = "denied" if denied else "prepared" if prepared else "blocked"

    canonical_event = (
        _plain_mapping(eligibility.get("canonical_event"))
        if valid
        else {}
    )
    eligible = bool(prepared and eligibility.get("eligible", True) is not False)
    preflight_reference = eligibility if valid else {}

    return {
        "contract": RECOVERY_PREFLIGHT_REPORT_CONTRACT,
        "report_id": report_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "eligible": eligible,
        "status": status,
        "preflight_report_only": True,
        "preflight_only": True,
        "observe_only": True,
        "dry_run": True,
        "preflight_complete": prepared,
        "preflight_result": (
            "eligible_for_next_non_executing_phase"
            if prepared
            else "blocked"
        ),
        "single_entry_only": prepared,
        "preflight_entry": eligibility.get("preflight_entry") if valid else None,
        "runtime_binding_allowed": False,
        "runtime_mainline_wiring_allowed": False,
        "recovery_execution_allowed": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "runtime_surface_touched": False,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
        "preflight_reference": preflight_reference,
        "preflight_eligibility_reference": preflight_reference,
        "canonical_event": canonical_event,
        "preflight_summary": {
            "preflight_valid": valid,
            "preflight_complete": prepared,
            "single_entry_only": prepared,
            "canonical_event_contract": canonical_event.get("contract", ""),
            "event_emitted": False,
            "runtime_binding_allowed": False,
            "recovery_execution_allowed": False,
            "next_phase": "controlled_non_executing_binding",
        },
        "denied_capabilities": list(RECOVERY_PREFLIGHT_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, requested_status_valid),
        "metadata": _plain_mapping(metadata),
    }


def _reason(requested_status: str, valid: bool, requested_status_valid: bool) -> str | None:
    if not requested_status_valid:
        return f"unsupported passive preflight report status: {requested_status}"
    if requested_status == "denied":
        return "caller requested passive denied preflight report status"
    if not valid:
        return "missing or incompatible passive Recovery preflight eligibility report"
    if requested_status == "blocked":
        return "caller requested passive blocked preflight report status"
    return None


def _plain_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(k): _plain_value(v) for k, v in value.items()}


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _plain_mapping(value)
    if isinstance(value, list):
        return [_plain_value(v) for v in value]
    if isinstance(value, tuple):
        return [_plain_value(v) for v in value]
    return value
