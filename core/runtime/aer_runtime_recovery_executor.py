"""Controlled Runtime Recovery executor reports without side effects."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_bridge import (
    RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
    RECOVERY_INTENT_RESPONSE_CONTRACT,
    RECOVERY_RUNTIME_BRIDGE_RESPONSE_CONTRACT,
)


RECOVERY_EXECUTOR_REPORT_CONTRACT = "aer.runtime.recovery.executor_report.v1"
RECOVERY_EXECUTOR_BOUNDARY_INPUT_CONTRACT = "aer.runtime.recovery.executor_boundary_input.v1"

RECOVERY_EXECUTOR_ALLOWED_STATUS = "prepared_no_side_effects"

RECOVERY_EXECUTOR_DENIED_CAPABILITIES = (
    "scheduler_admission",
    "dispatcher_command",
    "operator_action",
    "runtime_supervision",
    "subprocess_call",
    "repository_mutation",
    "persistence_write",
    "replay_action",
    "audit_emission",
    "journal_event",
    "runtime_mutation",
)

__all__ = [
    "RECOVERY_EXECUTOR_REPORT_CONTRACT",
    "RECOVERY_EXECUTOR_BOUNDARY_INPUT_CONTRACT",
    "RECOVERY_EXECUTOR_ALLOWED_STATUS",
    "RECOVERY_EXECUTOR_DENIED_CAPABILITIES",
    "build_recovery_executor_report",
]


def build_recovery_executor_report(
    bridge_payload: Mapping[str, Any],
    executor_boundary: Mapping[str, Any],
    *,
    executor_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic executor report from passive bridge and boundary data."""

    bridge = _plain_mapping(bridge_payload)
    boundary = _plain_mapping(executor_boundary)
    bridge_valid = _valid_bridge(bridge)
    authority_valid = _valid_authority_reference(bridge.get("authority_reference"))
    intent_valid = _valid_intent_reference(bridge.get("intent_reference"))
    boundary_valid = _valid_executor_boundary(boundary, bridge)
    accepted = bridge_valid and authority_valid and intent_valid and boundary_valid

    return {
        "contract": RECOVERY_EXECUTOR_REPORT_CONTRACT,
        "executor_id": executor_id,
        "accepted": accepted,
        "rejected": not accepted,
        "status": _status(bridge_valid, authority_valid, intent_valid, boundary_valid),
        "bridge_reference": bridge if bridge_valid else {},
        "authority_reference": _plain_mapping(bridge.get("authority_reference")) if authority_valid else {},
        "intent_reference": _plain_mapping(bridge.get("intent_reference")) if intent_valid else {},
        "executor_boundary_reference": boundary if boundary_valid else {},
        "execution_report": {
            "prepared": accepted,
            "performed_side_effects": False,
            "scheduled": False,
            "dispatched": False,
            "persisted": False,
            "replayed": False,
            "audited": False,
            "journaled": False,
        },
        "denied_capabilities": list(RECOVERY_EXECUTOR_DENIED_CAPABILITIES),
        "reason": _reason(bridge_valid, authority_valid, intent_valid, boundary_valid),
        "metadata": _plain_mapping(metadata),
        "side_effects_performed": False,
        "executes_recovery": False,
        "plain_dict_only": True,
    }


def _valid_bridge(value: Mapping[str, Any]) -> bool:
    return (
        value.get("contract") == RECOVERY_RUNTIME_BRIDGE_RESPONSE_CONTRACT
        and value.get("accepted") is True
        and value.get("status") == "accepted_bridge_only"
        and value.get("executes_recovery") is False
        and value.get("bridge_only") is True
    )


def _valid_authority_reference(value: Any) -> bool:
    authority = _plain_mapping(value)
    return (
        authority.get("contract") == RECOVERY_AUTHORITY_RESPONSE_CONTRACT
        and authority.get("authorized") is True
        and authority.get("decision") == "authorized_for_future_handoff"
        and authority.get("executes_recovery") is False
        and authority.get("authority_only") is True
    )


def _valid_intent_reference(value: Any) -> bool:
    intent = _plain_mapping(value)
    return (
        intent.get("contract") == RECOVERY_INTENT_RESPONSE_CONTRACT
        and intent.get("accepted") is True
        and intent.get("status") == "accepted_intent_only"
        and intent.get("executes_recovery") is False
        and intent.get("intent_only") is True
    )


def _valid_executor_boundary(boundary: Mapping[str, Any], bridge: Mapping[str, Any]) -> bool:
    return (
        boundary.get("contract") == RECOVERY_EXECUTOR_BOUNDARY_INPUT_CONTRACT
        and boundary.get("bridge_reference") == bridge
        and boundary.get("authority_reference") == _plain_mapping(bridge.get("authority_reference"))
        and boundary.get("intent_reference") == _plain_mapping(bridge.get("intent_reference"))
        and boundary.get("boundary_only") is True
    )


def _status(
    bridge_valid: bool,
    authority_valid: bool,
    intent_valid: bool,
    boundary_valid: bool,
) -> str:
    if not bridge_valid:
        return "blocked_invalid_bridge"
    if not authority_valid:
        return "blocked_invalid_authority"
    if not intent_valid:
        return "blocked_invalid_intent"
    if not boundary_valid:
        return "blocked_invalid_executor_boundary"
    return RECOVERY_EXECUTOR_ALLOWED_STATUS


def _reason(
    bridge_valid: bool,
    authority_valid: bool,
    intent_valid: bool,
    boundary_valid: bool,
) -> str | None:
    if not bridge_valid:
        return "invalid recovery runtime bridge payload"
    if not authority_valid:
        return "invalid recovery execution authority reference"
    if not intent_valid:
        return "invalid recovery execution intent reference"
    if not boundary_valid:
        return "invalid recovery executor boundary requirements"
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
