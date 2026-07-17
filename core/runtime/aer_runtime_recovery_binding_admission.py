"""Disabled Runtime Recovery binding admission evaluation reports.

Package 204 evaluates whether a disabled Runtime Recovery binding skeleton may be
considered by Runtime. It is an admission data surface only: it never admits,
registers, applies, emits, mutates, or executes Recovery.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


RECOVERY_BINDING_ADMISSION_EVALUATION_CONTRACT = (
    "aer.runtime.recovery.binding_admission_evaluation.v1"
)
RECOVERY_BINDING_ADMISSION_ENTRY = "runtime_recovery_single_entry"
RECOVERY_BINDING_ADMISSION_ALLOWED_STATUSES = ("prepared", "blocked", "denied")
RECOVERY_BINDING_ADMISSION_DENIED_CAPABILITIES = (
    "recovery_execution",
    "recovery_enablement",
    "runtime_mainline_wiring",
    "runtime_hook_registration",
    "runtime_binding_application",
    "binding_admission_grant",
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
    "RECOVERY_BINDING_ADMISSION_EVALUATION_CONTRACT",
    "RECOVERY_BINDING_ADMISSION_ENTRY",
    "RECOVERY_BINDING_ADMISSION_ALLOWED_STATUSES",
    "RECOVERY_BINDING_ADMISSION_DENIED_CAPABILITIES",
    "prepare_recovery_binding_admission_evaluation",
]


def prepare_recovery_binding_admission_evaluation(
    disabled_binding_report: Mapping[str, Any],
    runtime_binding_points_report: Mapping[str, Any],
    *,
    admission_id: str | None = None,
    requested_status: str = "prepared",
    requested_entry: str = RECOVERY_BINDING_ADMISSION_ENTRY,
    request_admission: bool = False,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare disabled binding admission data without admitting runtime binding."""

    binding = _plain_mapping(disabled_binding_report)
    points = _plain_mapping(runtime_binding_points_report)
    single_entry = requested_entry == RECOVERY_BINDING_ADMISSION_ENTRY
    valid = _valid_disabled_binding(binding) and _valid_binding_points(points) and single_entry
    denied = request_admission or requested_status == "denied"
    prepared = valid and requested_status == "prepared" and not denied
    blocked = (not valid and not denied) or (valid and requested_status == "blocked")
    status = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_BINDING_ADMISSION_EVALUATION_CONTRACT,
        "admission_id": admission_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "status": status,
        "single_entry_only": True,
        "binding_entry": RECOVERY_BINDING_ADMISSION_ENTRY if single_entry else None,
        "admission_evaluated": prepared,
        "admission_allowed": False,
        "binding_admitted": False,
        "runtime_accepts_binding": False,
        "runtime_hook_registered": False,
        "runtime_binding_applied": False,
        "binding_enabled": False,
        "recovery_enabled": False,
        "event_emitted": False,
        "canonical_event": _plain_mapping(binding.get("canonical_event")) if _valid_disabled_binding(binding) else {},
        "disabled_binding_reference": binding if _valid_disabled_binding(binding) else {},
        "runtime_binding_points_reference": points if _valid_binding_points(points) else {},
        "denied_capabilities": list(RECOVERY_BINDING_ADMISSION_DENIED_CAPABILITIES),
        "reason": _reason(requested_status, valid, single_entry, request_admission),
        "metadata": _plain_mapping(metadata),
        "admission_evaluation_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_disabled_binding(value: Mapping[str, Any]) -> bool:
    event = _plain_mapping(value.get("canonical_event"))
    return (
        value.get("contract") == "aer.runtime.recovery.disabled_runtime_binding_report.v1"
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("single_entry_only") is True
        and value.get("binding_entry") == RECOVERY_BINDING_ADMISSION_ENTRY
        and value.get("binding_skeleton") is True
        and value.get("binding_enabled") is False
        and value.get("bound_to_runtime") is False
        and value.get("runtime_hook_registered") is False
        and value.get("runtime_binding_applied") is False
        and value.get("recovery_enabled") is False
        and value.get("event_emitted") is False
        and event.get("contract") == "aer.runtime.recovery.event.v1"
        and event.get("entry_id") == RECOVERY_BINDING_ADMISSION_ENTRY
        and event.get("event_emitted") is False
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _valid_binding_points(value: Mapping[str, Any]) -> bool:
    event = _plain_mapping(value.get("canonical_event"))
    return (
        value.get("contract") == "aer.runtime.recovery.runtime_binding_points_report.v1"
        and value.get("prepared") is True
        and value.get("blocked") is False
        and value.get("denied") is False
        and value.get("status") == "prepared"
        and value.get("single_entry_only") is True
        and value.get("binding_entry") == RECOVERY_BINDING_ADMISSION_ENTRY
        and value.get("binding_points_declared") is True
        and value.get("binding_points_registered") is False
        and value.get("runtime_hook_registered") is False
        and value.get("runtime_binding_applied") is False
        and value.get("runtime_surface_touched") is False
        and value.get("binding_enabled") is False
        and value.get("recovery_enabled") is False
        and value.get("event_emitted") is False
        and event.get("contract") == "aer.runtime.recovery.event.v1"
        and event.get("entry_id") == RECOVERY_BINDING_ADMISSION_ENTRY
        and event.get("event_emitted") is False
        and value.get("executes_recovery") is False
        and value.get("side_effects_performed") is False
        and value.get("plain_dict_only") is True
    )


def _reason(
    requested_status: str,
    valid: bool,
    single_entry: bool,
    request_admission: bool,
) -> str | None:
    if request_admission:
        return "binding admission grants are prohibited in the disabled admission layer"
    if requested_status == "denied":
        return "caller requested passive denied binding admission status"
    if not single_entry:
        return "binding admission allows only runtime_recovery_single_entry"
    if not valid:
        return "missing or incompatible disabled binding or binding points report"
    if requested_status == "blocked":
        return "caller requested passive blocked binding admission status"
    if requested_status != "prepared":
        return f"unsupported passive binding admission status: {requested_status}"
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
