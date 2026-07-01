"""Passive Runtime Recovery runtime integration pipeline."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.runtime.aer_runtime_recovery_bridge import build_recovery_runtime_bridge_report as _build_bridge_report
from core.runtime.aer_runtime_recovery_executor import (
    RECOVERY_EXECUTOR_BOUNDARY_INPUT_CONTRACT,
    build_recovery_executor_report as _build_executor_report,
)


RECOVERY_RUNTIME_INTEGRATION_REPORT_CONTRACT = "aer.runtime.recovery.runtime_integration_report.v1"

__all__ = [
    "RECOVERY_RUNTIME_INTEGRATION_REPORT_CONTRACT",
    "coordinate_recovery_runtime_integration",
]


def coordinate_recovery_runtime_integration(
    authority_response: Mapping[str, Any],
    intent_response: Mapping[str, Any],
    *,
    integration_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Coordinate authority, intent, bridge, and executor into passive report data."""

    bridge = _build_bridge_report(
        authority_response,
        intent_response,
        bridge_consumer="runtime_recovery_runtime_bridge",
        bridge_request_id=integration_id,
        metadata={"integration_id": integration_id},
    )
    boundary = {
        "contract": RECOVERY_EXECUTOR_BOUNDARY_INPUT_CONTRACT,
        "executor_boundary_id": integration_id,
        "bridge_reference": bridge,
        "authority_reference": bridge.get("authority_reference", {}),
        "intent_reference": bridge.get("intent_reference", {}),
        "requested_executor_scope": "executor_boundary_review_only",
        "metadata": {},
        "boundary_only": True,
    }
    executor = _build_executor_report(
        bridge,
        boundary,
        executor_id=integration_id,
        metadata={"integration_id": integration_id},
    )
    accepted = bridge.get("accepted") is True and executor.get("accepted") is True

    return {
        "contract": RECOVERY_RUNTIME_INTEGRATION_REPORT_CONTRACT,
        "integration_id": integration_id,
        "accepted": accepted,
        "status": "integrated_no_side_effects" if accepted else "blocked_runtime_integration",
        "authority_reference": _plain_mapping(authority_response),
        "intent_reference": _plain_mapping(intent_response),
        "bridge_report": bridge,
        "executor_boundary": boundary,
        "executor_report": executor,
        "metadata": _plain_mapping(metadata),
        "external_runtime_invoked": False,
        "side_effects_performed": False,
        "executes_recovery": False,
        "plain_dict_only": True,
    }


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
