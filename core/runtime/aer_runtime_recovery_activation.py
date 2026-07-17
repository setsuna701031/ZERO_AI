"""Passive Runtime Recovery activation preparation reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_bridge import (
    RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
    RECOVERY_INTENT_RESPONSE_CONTRACT,
    RECOVERY_RUNTIME_BRIDGE_RESPONSE_CONTRACT,
)
from core.runtime.aer_runtime_recovery_executor import (
    RECOVERY_EXECUTOR_ALLOWED_STATUS,
    RECOVERY_EXECUTOR_REPORT_CONTRACT,
)
from core.runtime.aer_runtime_recovery_runtime_integration import RECOVERY_RUNTIME_INTEGRATION_REPORT_CONTRACT


RECOVERY_ACTIVATION_REQUEST_CONTRACT = "aer.runtime.recovery.activation_request.v1"
RECOVERY_ACTIVATION_RESPONSE_CONTRACT = "aer.runtime.recovery.activation_response.v1"

RECOVERY_ACTIVATION_ALLOWED_STATES = ("prepared", "blocked", "denied")
RECOVERY_ACTIVATION_FORBIDDEN_STATES = (
    "activated",
    "activating",
    "running",
    "scheduled",
    "dispatched",
    "operator_started",
    "supervised",
    "executed",
    "persisted",
    "replayed",
    "audited",
    "journaled",
    "mutated",
)
RECOVERY_ACTIVATION_DENIED_RUNTIME_HOOKS = (
    "scheduler_admission",
    "dispatcher_command",
    "operator_runtime_action",
    "runtime_supervisor",
    "native_runtime_execution",
    "persistence_write",
    "replay_action",
    "audit_emission",
    "journal_event",
    "subprocess_call",
    "file_io",
    "runtime_mutation",
)

__all__ = [
    "RECOVERY_ACTIVATION_REQUEST_CONTRACT",
    "RECOVERY_ACTIVATION_RESPONSE_CONTRACT",
    "RECOVERY_ACTIVATION_ALLOWED_STATES",
    "RECOVERY_ACTIVATION_FORBIDDEN_STATES",
    "RECOVERY_ACTIVATION_DENIED_RUNTIME_HOOKS",
    "prepare_recovery_runtime_activation",
]


def prepare_recovery_runtime_activation(
    recovery_integration_report: Mapping[str, Any],
    *,
    activation_id: str | None = None,
    requested_state: str = "prepared",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare a deterministic activation report from passive Recovery integration data."""

    integration = _plain_mapping(recovery_integration_report)
    authority = _plain_mapping(integration.get("authority_reference"))
    intent = _plain_mapping(integration.get("intent_reference"))
    bridge = _plain_mapping(integration.get("bridge_report"))
    executor = _plain_mapping(integration.get("executor_report"))

    forbidden_state = requested_state in RECOVERY_ACTIVATION_FORBIDDEN_STATES
    references_valid = (
        _valid_integration(integration)
        and _valid_authority(authority)
        and _valid_intent(intent, authority)
        and _valid_bridge(bridge, authority, intent)
        and _valid_executor(executor, bridge, authority, intent)
    )
    prepared = references_valid and not forbidden_state and requested_state == "prepared"
    denied = forbidden_state or (references_valid and requested_state == "denied")
    blocked = (not references_valid and not denied) or (references_valid and requested_state == "blocked")
    activation_state = "denied" if denied else "prepared" if prepared else "blocked"

    return {
        "contract": RECOVERY_ACTIVATION_RESPONSE_CONTRACT,
        "activation_id": activation_id,
        "prepared": prepared,
        "blocked": blocked,
        "denied": denied,
        "activation_state": activation_state,
        "activation_request": {
            "contract": RECOVERY_ACTIVATION_REQUEST_CONTRACT,
            "activation_id": activation_id,
            "requested_state": requested_state,
            "integration_report_reference": integration,
            "authority_reference": authority,
            "intent_reference": intent,
            "bridge_reference": bridge,
            "executor_report_reference": executor,
            "metadata": _plain_mapping(metadata),
            "activation_only": True,
        },
        "integration_report_reference": integration if references_valid else {},
        "authority_reference": authority if _valid_authority(authority) else {},
        "intent_reference": intent if _valid_intent(intent, authority) else {},
        "bridge_reference": bridge if _valid_bridge(bridge, authority, intent) else {},
        "executor_report_reference": executor if _valid_executor(executor, bridge, authority, intent) else {},
        "allowed_activation_states": list(RECOVERY_ACTIVATION_ALLOWED_STATES),
        "forbidden_activation_states": list(RECOVERY_ACTIVATION_FORBIDDEN_STATES),
        "denied_runtime_hooks": list(RECOVERY_ACTIVATION_DENIED_RUNTIME_HOOKS),
        "reason": _reason(requested_state, references_valid, forbidden_state),
        "metadata": _plain_mapping(metadata),
        "activation_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _valid_integration(value: Mapping[str, Any]) -> bool:
    return (
        value.get("contract") == RECOVERY_RUNTIME_INTEGRATION_REPORT_CONTRACT
        and value.get("accepted") is True
        and value.get("status") == "integrated_no_side_effects"
        and value.get("external_runtime_invoked") is False
        and value.get("side_effects_performed") is False
        and value.get("executes_recovery") is False
        and value.get("plain_dict_only") is True
    )


def _valid_authority(value: Mapping[str, Any]) -> bool:
    return (
        value.get("contract") == RECOVERY_AUTHORITY_RESPONSE_CONTRACT
        and value.get("authorized") is True
        and value.get("decision") == "authorized_for_future_handoff"
        and value.get("executes_recovery") is False
        and value.get("authority_only") is True
    )


def _valid_intent(value: Mapping[str, Any], authority: Mapping[str, Any]) -> bool:
    return (
        value.get("contract") == RECOVERY_INTENT_RESPONSE_CONTRACT
        and value.get("accepted") is True
        and value.get("status") == "accepted_intent_only"
        and value.get("authority_reference") == authority
        and value.get("executes_recovery") is False
        and value.get("intent_only") is True
    )


def _valid_bridge(
    value: Mapping[str, Any],
    authority: Mapping[str, Any],
    intent: Mapping[str, Any],
) -> bool:
    return (
        value.get("contract") == RECOVERY_RUNTIME_BRIDGE_RESPONSE_CONTRACT
        and value.get("accepted") is True
        and value.get("status") == "accepted_bridge_only"
        and value.get("authority_reference") == authority
        and value.get("intent_reference") == intent
        and value.get("executes_recovery") is False
        and value.get("bridge_only") is True
    )


def _valid_executor(
    value: Mapping[str, Any],
    bridge: Mapping[str, Any],
    authority: Mapping[str, Any],
    intent: Mapping[str, Any],
) -> bool:
    execution_report = _plain_mapping(value.get("execution_report"))
    return (
        value.get("contract") == RECOVERY_EXECUTOR_REPORT_CONTRACT
        and value.get("accepted") is True
        and value.get("status") == RECOVERY_EXECUTOR_ALLOWED_STATUS
        and value.get("bridge_reference") == bridge
        and value.get("authority_reference") == authority
        and value.get("intent_reference") == intent
        and execution_report.get("performed_side_effects") is False
        and execution_report.get("scheduled") is False
        and execution_report.get("dispatched") is False
        and value.get("side_effects_performed") is False
        and value.get("executes_recovery") is False
        and value.get("plain_dict_only") is True
    )


def _reason(requested_state: str, references_valid: bool, forbidden_state: bool) -> str | None:
    if forbidden_state:
        return f"forbidden activation state: {requested_state}"
    if not references_valid:
        return "missing or incompatible passive Recovery activation references"
    if requested_state == "blocked":
        return "caller requested passive blocked activation state"
    if requested_state == "denied":
        return "caller requested passive denied activation state"
    if requested_state != "prepared":
        return f"unsupported passive activation request state: {requested_state}"
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
