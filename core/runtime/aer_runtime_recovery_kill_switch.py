"""Passive Runtime Recovery kill-switch reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_controlled_activation import RECOVERY_CONTROLLED_ACTIVATION_REPORT_CONTRACT


RECOVERY_KILL_SWITCH_REPORT_CONTRACT = "aer.runtime.recovery.kill_switch_report.v1"
RECOVERY_KILL_SWITCH_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_KILL_SWITCH_DENIED_CAPABILITIES = (
    "recovery_enablement",
    "recovery_execution",
    "runtime_mainline_wiring",
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
    "RECOVERY_KILL_SWITCH_REPORT_CONTRACT",
    "RECOVERY_KILL_SWITCH_ALLOWED_STATUSES",
    "RECOVERY_KILL_SWITCH_DENIED_CAPABILITIES",
    "prepare_recovery_kill_switch_report",
]


def prepare_recovery_kill_switch_report(
    controlled_activation_report: Mapping[str, Any],
    *,
    kill_switch_id: str | None = None,
    requested_status: str = "prepared",
    request_enablement: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare passive kill-switch data while keeping Recovery disabled."""

    controlled = _plain_mapping(controlled_activation_report)
    valid = _valid_controlled_activation(controlled)
    denied = request_enablement or requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_KILL_SWITCH_REPORT_CONTRACT,
        "kill_switch_id": kill_switch_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "kill_switch_enabled": False,
        "kill_switch_state": "off",
        "safe_mode": True,
        "recovery_enabled": False,
        "controlled_activation_reference": controlled if valid else {},
        "denied_capabilities": list(RECOVERY_KILL_SWITCH_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, request_enablement),
        "metadata": _plain_mapping(metadata),
        "kill_switch_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_controlled_activation(value: Mapping[str, Any]) -> bool:
    return (
        value.get("contract") == RECOVERY_CONTROLLED_ACTIVATION_REPORT_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("activation_gate_enabled") is False
        and value.get("activation_allowed") is False
        and value.get("runtime_mainline_wiring_allowed") is False
        and value.get("preparation_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_status: str, valid: bool, request_enablement: bool) -> str | None:
    if request_enablement:
        return "Recovery enablement is prohibited by default kill-switch semantics"
    if requested_status == "denied":
        return "caller requested passive denied kill-switch status"
    if not valid:
        return "missing or incompatible controlled activation preparation report"
    if requested_status == "blocked":
        return "caller requested passive blocked kill-switch status"
    if requested_status != "prepared":
        return f"unsupported passive kill-switch status: {requested_status}"
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
