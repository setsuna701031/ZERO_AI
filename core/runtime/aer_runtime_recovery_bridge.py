"""Passive Runtime Recovery bridge reports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


RECOVERY_RUNTIME_BRIDGE_RESPONSE_CONTRACT = "aer.runtime.recovery.runtime_bridge_response.v1"
RECOVERY_AUTHORITY_RESPONSE_CONTRACT = "aer.runtime.recovery.execution_authority_response.v1"
RECOVERY_INTENT_RESPONSE_CONTRACT = "aer.runtime.recovery.execution_intent_response.v1"

ALLOWED_RECOVERY_BRIDGE_CONSUMERS = frozenset(
    {
        "runtime_recovery_runtime_bridge",
        "runtime_recovery_executor_boundary",
        "runtime_recovery_bridge_review",
    }
)

RECOVERY_RUNTIME_BRIDGE_SCOPE = "passive_recovery_runtime_bridge"

RECOVERY_RUNTIME_BRIDGE_DENIED_CAPABILITIES = (
    "recovery_execution",
    "scheduler_admission",
    "dispatcher_command",
    "operator_action",
    "runtime_supervision",
    "persistence_write",
    "audit_emission",
    "journal_event",
    "replay_action",
    "runtime_mutation",
    "file_mutation",
    "external_process_call",
)

__all__ = [
    "RECOVERY_RUNTIME_BRIDGE_RESPONSE_CONTRACT",
    "RECOVERY_AUTHORITY_RESPONSE_CONTRACT",
    "RECOVERY_INTENT_RESPONSE_CONTRACT",
    "ALLOWED_RECOVERY_BRIDGE_CONSUMERS",
    "RECOVERY_RUNTIME_BRIDGE_SCOPE",
    "RECOVERY_RUNTIME_BRIDGE_DENIED_CAPABILITIES",
    "build_recovery_runtime_bridge_report",
]


def build_recovery_runtime_bridge_report(
    authority_response: Mapping[str, Any],
    intent_response: Mapping[str, Any],
    *,
    bridge_consumer: str,
    bridge_request_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a passive bridge report from authority and intent response data."""

    authority = _plain_mapping(authority_response)
    intent = _plain_mapping(intent_response)
    authority_valid = _valid_authority_reference(authority)
    intent_valid = _valid_intent_reference(intent)
    consumer_allowed = bridge_consumer in ALLOWED_RECOVERY_BRIDGE_CONSUMERS
    accepted = authority_valid and intent_valid and consumer_allowed

    return {
        "contract": RECOVERY_RUNTIME_BRIDGE_RESPONSE_CONTRACT,
        "bridge_request_id": bridge_request_id,
        "bridge_consumer": bridge_consumer,
        "accepted": accepted,
        "rejected": not accepted,
        "status": _status(authority_valid, intent_valid, consumer_allowed),
        "authority_reference": authority if authority_valid else {},
        "intent_reference": intent if intent_valid else {},
        "bridge_scope": RECOVERY_RUNTIME_BRIDGE_SCOPE if accepted else None,
        "denied_capabilities": list(RECOVERY_RUNTIME_BRIDGE_DENIED_CAPABILITIES),
        "reason": _reason(authority_valid, intent_valid, consumer_allowed),
        "metadata": _plain_mapping(metadata),
        "executes_recovery": False,
        "bridge_only": True,
    }


def _valid_authority_reference(authority: Mapping[str, Any]) -> bool:
    return (
        authority.get("contract") == RECOVERY_AUTHORITY_RESPONSE_CONTRACT
        and authority.get("authorized") is True
        and authority.get("decision") == "authorized_for_future_handoff"
        and authority.get("executes_recovery") is False
        and authority.get("authority_only") is True
    )


def _valid_intent_reference(intent: Mapping[str, Any]) -> bool:
    return (
        intent.get("contract") == RECOVERY_INTENT_RESPONSE_CONTRACT
        and intent.get("accepted") is True
        and intent.get("status") == "accepted_intent_only"
        and intent.get("executes_recovery") is False
        and intent.get("intent_only") is True
        and isinstance(intent.get("intended_actions"), list)
    )


def _status(authority_valid: bool, intent_valid: bool, consumer_allowed: bool) -> str:
    if not authority_valid:
        return "blocked_missing_or_invalid_authority"
    if not intent_valid:
        return "blocked_missing_or_invalid_intent"
    if not consumer_allowed:
        return "denied_forbidden_bridge_consumer"
    return "accepted_bridge_only"


def _reason(authority_valid: bool, intent_valid: bool, consumer_allowed: bool) -> str | None:
    if not authority_valid:
        return "missing or invalid recovery execution authority reference"
    if not intent_valid:
        return "missing or invalid recovery execution intent reference"
    if not consumer_allowed:
        return "forbidden recovery runtime bridge consumer"
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
