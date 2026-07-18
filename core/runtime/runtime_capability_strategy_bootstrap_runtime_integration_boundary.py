from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_bootstrap_consumption_validation import validate_bootstrap_consumption


SCHEMA = "zero.runtime.capability_strategy_bootstrap_runtime_integration_boundary.v1"
STATUSES = frozenset({"integrated", "default_compatible", "rejected", "invalid"})


def _passive_payload(value: Any) -> bool:
    if callable(value):
        return False
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _passive_payload(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_passive_payload(item) for item in value)
    if isinstance(value, str):
        return not any(marker in value for marker in ("/", "\\", ":", "\n", "\r", ";", "|", "&&", "$(", "`"))
    return value is None or isinstance(value, (bool, int))


def _linkage(consumption: Any) -> dict[str, Any]:
    if not isinstance(consumption, Mapping):
        consumption = {}
    return {
        "source_consumption_id": consumption.get("consumption_id"),
        "source_consumption_fingerprint": consumption.get("fingerprint"),
        "source_wiring_id": consumption.get("source_wiring_id"),
        "source_wiring_fingerprint": consumption.get("source_wiring_fingerprint"),
        "source_bootstrap_configuration_id": consumption.get("source_bootstrap_configuration_id"),
        "source_bootstrap_configuration_fingerprint": consumption.get("source_bootstrap_configuration_fingerprint"),
        "source_runtime_decision_id": consumption.get("source_runtime_decision_id"),
        "source_strategy_id": consumption.get("source_strategy_id"),
        "source_profile_id": consumption.get("source_profile_id"),
    }


def build_bootstrap_runtime_integration_boundary(consumption: Any) -> dict[str, Any]:
    valid = validate_bootstrap_consumption(consumption).valid
    source_status = consumption.get("status") if isinstance(consumption, Mapping) else None
    if not valid:
        status, payload, reasons = "invalid", None, ["invalid_bootstrap_consumption"]
    elif source_status == "consumed" and _passive_payload(consumption.get("consumer_payload")):
        status = "integrated"
        payload = deepcopy(consumption["consumer_payload"])
        reasons = ["validated_consumption_sealed_for_integration"]
    elif source_status == "consumed":
        status, payload, reasons = "invalid", None, ["unsafe_bootstrap_consumption_payload"]
    elif source_status == "default_compatible":
        status, payload, reasons = "default_compatible", None, ["default_compatible_consumption"]
    elif source_status == "rejected":
        status, payload, reasons = "rejected", None, ["bootstrap_consumption_rejected"]
    else:
        status, payload, reasons = "invalid", None, ["invalid_bootstrap_consumption"]
    base = {
        "schema": SCHEMA,
        "status": status,
        **_linkage(consumption),
        "integration_payload": payload,
        "reasons": reasons,
        "boundary": {
            "sealed": True,
            "read_only": True,
            "passive_handoff": True,
            "runtime_activation": False,
            "scope_expansion": False,
        },
    }
    return _identified(base, "boundary_id", "capability-strategy-bootstrap-runtime-integration-boundary-")


integrate_bootstrap_consumption = build_bootstrap_runtime_integration_boundary

__all__ = ["SCHEMA", "STATUSES", "build_bootstrap_runtime_integration_boundary", "integrate_bootstrap_consumption"]
