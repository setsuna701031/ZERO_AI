"""Passive Runtime Supervisor-facing Runtime Recovery adapter reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_activation import RECOVERY_ACTIVATION_RESPONSE_CONTRACT
from core.runtime.aer_runtime_recovery_bridge import (
    RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
    RECOVERY_INTENT_RESPONSE_CONTRACT,
    RECOVERY_RUNTIME_BRIDGE_RESPONSE_CONTRACT,
)
from core.runtime.aer_runtime_recovery_executor import RECOVERY_EXECUTOR_REPORT_CONTRACT


RECOVERY_SUPERVISOR_ADAPTER_REPORT_CONTRACT = "aer.runtime.recovery.supervisor_adapter_report.v1"
RECOVERY_SUPERVISOR_ADAPTER_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_SUPERVISOR_ADAPTER_DENIED_CAPABILITIES = (
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
    "RECOVERY_SUPERVISOR_ADAPTER_REPORT_CONTRACT",
    "RECOVERY_SUPERVISOR_ADAPTER_ALLOWED_STATUSES",
    "RECOVERY_SUPERVISOR_ADAPTER_DENIED_CAPABILITIES",
    "prepare_recovery_supervisor_adapter_report",
]


def prepare_recovery_supervisor_adapter_report(
    activation_report: Mapping[str, Any],
    *,
    adapter_id: str | None = None,
    requested_status: str = "prepared",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare deterministic Runtime Supervisor-facing adapter data without runtime effects."""

    activation = _plain_mapping(activation_report)
    authority = _plain_mapping(activation.get("authority_reference"))
    intent = _plain_mapping(activation.get("intent_reference"))
    bridge = _plain_mapping(activation.get("bridge_reference"))
    executor = _plain_mapping(activation.get("executor_report_reference"))
    valid = (
        _valid_activation(activation)
        and _valid_authority(authority)
        and _valid_intent(intent)
        and _valid_bridge(bridge)
        and _valid_executor(executor)
    )
    denied = requested_status == "denied"
    prepared = valid and requested_status == "prepared"
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_SUPERVISOR_ADAPTER_REPORT_CONTRACT,
        "adapter_id": adapter_id,
        "adapter_target": "runtime_supervisor",
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "activation_reference": activation if valid else {},
        "authority_reference": authority if _valid_authority(authority) else {},
        "intent_reference": intent if _valid_intent(intent) else {},
        "bridge_reference": bridge if _valid_bridge(bridge) else {},
        "executor_report_reference": executor if _valid_executor(executor) else {},
        "denied_capabilities": list(RECOVERY_SUPERVISOR_ADAPTER_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid),
        "metadata": _plain_mapping(metadata),
        "adapter_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_activation(value: Mapping[str, Any]) -> bool:
    return (
        value.get("contract") == RECOVERY_ACTIVATION_RESPONSE_CONTRACT
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("activation_state") == "prepared"
        and value.get("activation_only") is True
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _valid_authority(value: Mapping[str, Any]) -> bool:
    return value.get("contract") == RECOVERY_AUTHORITY_RESPONSE_CONTRACT and value.get("executes_recovery") is False


def _valid_intent(value: Mapping[str, Any]) -> bool:
    return value.get("contract") == RECOVERY_INTENT_RESPONSE_CONTRACT and value.get("executes_recovery") is False


def _valid_bridge(value: Mapping[str, Any]) -> bool:
    return value.get("contract") == RECOVERY_RUNTIME_BRIDGE_RESPONSE_CONTRACT and value.get("executes_recovery") is False


def _valid_executor(value: Mapping[str, Any]) -> bool:
    return value.get("contract") == RECOVERY_EXECUTOR_REPORT_CONTRACT and value.get("executes_recovery") is False


def _reason(requested_status: str, valid: bool) -> str | None:
    if requested_status == "denied":
        return "caller requested passive denied adapter status"
    if not valid:
        return "missing or incompatible passive Recovery activation references"
    if requested_status == "blocked":
        return "caller requested passive blocked adapter status"
    if requested_status != "prepared":
        return f"unsupported passive adapter status: {requested_status}"
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
