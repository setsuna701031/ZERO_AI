from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_bootstrap_runtime_integration_boundary_validation import validate_bootstrap_runtime_integration_boundary


SCHEMA = "zero.runtime.capability_strategy_runtime_integration_consumer.v1"
STATUSES = frozenset({"consumed", "default_compatible", "rejected", "invalid"})


def _linkage(boundary: Any) -> dict[str, Any]:
    if not isinstance(boundary, Mapping):
        boundary = {}
    return {
        "source_integration_boundary_id": boundary.get("boundary_id"),
        "source_integration_boundary_fingerprint": boundary.get("fingerprint"),
        "source_consumption_id": boundary.get("source_consumption_id"),
        "source_consumption_fingerprint": boundary.get("source_consumption_fingerprint"),
        "source_wiring_id": boundary.get("source_wiring_id"),
        "source_wiring_fingerprint": boundary.get("source_wiring_fingerprint"),
        "source_bootstrap_configuration_id": boundary.get("source_bootstrap_configuration_id"),
        "source_bootstrap_configuration_fingerprint": boundary.get("source_bootstrap_configuration_fingerprint"),
        "source_runtime_decision_id": boundary.get("source_runtime_decision_id"),
        "source_strategy_id": boundary.get("source_strategy_id"),
        "source_profile_id": boundary.get("source_profile_id"),
    }


def consume_runtime_integration_boundary(boundary: Any) -> dict[str, Any]:
    valid = validate_bootstrap_runtime_integration_boundary(boundary).valid
    source_status = boundary.get("status") if isinstance(boundary, Mapping) else None
    if not valid:
        status, payload, reasons = "invalid", None, ["invalid_runtime_integration_boundary"]
    elif source_status == "integrated":
        status, payload, reasons = "consumed", deepcopy(boundary["integration_payload"]), ["sealed_integration_boundary_consumed"]
    elif source_status == "default_compatible":
        status, payload, reasons = "default_compatible", None, ["default_compatible_integration_boundary"]
    elif source_status == "rejected":
        status, payload, reasons = "rejected", None, ["runtime_integration_boundary_rejected"]
    else:
        status, payload, reasons = "invalid", None, ["invalid_runtime_integration_boundary"]
    base = {
        "schema": SCHEMA,
        "status": status,
        **_linkage(boundary),
        "consumer_payload": payload,
        "reasons": reasons,
        "boundary": {
            "sealed": True,
            "read_only": True,
            "passive_consumer": True,
            "runtime_activation": False,
            "scope_expansion": False,
        },
    }
    return _identified(base, "consumer_id", "capability-strategy-runtime-integration-consumer-")


build_runtime_integration_consumer = consume_runtime_integration_boundary

__all__ = ["SCHEMA", "STATUSES", "build_runtime_integration_consumer", "consume_runtime_integration_boundary"]
