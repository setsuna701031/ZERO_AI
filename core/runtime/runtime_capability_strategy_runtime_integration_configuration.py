from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_integration_consumer_validation import validate_runtime_integration_consumer


SCHEMA = "zero.runtime.capability_strategy_runtime_integration_configuration.v1"
STATUSES = frozenset({"configured", "default_compatible", "rejected", "invalid"})


def _linkage(consumer: Any) -> dict[str, Any]:
    if not isinstance(consumer, Mapping):
        consumer = {}
    return {
        "source_integration_consumer_id": consumer.get("consumer_id"),
        "source_integration_consumer_fingerprint": consumer.get("fingerprint"),
        "source_integration_boundary_id": consumer.get("source_integration_boundary_id"),
        "source_integration_boundary_fingerprint": consumer.get("source_integration_boundary_fingerprint"),
        "source_consumption_id": consumer.get("source_consumption_id"),
        "source_consumption_fingerprint": consumer.get("source_consumption_fingerprint"),
        "source_wiring_id": consumer.get("source_wiring_id"),
        "source_wiring_fingerprint": consumer.get("source_wiring_fingerprint"),
        "source_bootstrap_configuration_id": consumer.get("source_bootstrap_configuration_id"),
        "source_bootstrap_configuration_fingerprint": consumer.get("source_bootstrap_configuration_fingerprint"),
        "source_runtime_decision_id": consumer.get("source_runtime_decision_id"),
        "source_strategy_id": consumer.get("source_strategy_id"),
        "source_profile_id": consumer.get("source_profile_id"),
    }


def configure_runtime_integration(consumer: Any) -> dict[str, Any]:
    valid = validate_runtime_integration_consumer(consumer).valid
    source_status = consumer.get("status") if isinstance(consumer, Mapping) else None
    if not valid:
        status, payload, reasons = "invalid", None, ["invalid_runtime_integration_consumer"]
    elif source_status == "consumed":
        status, payload, reasons = "configured", deepcopy(consumer["consumer_payload"]), ["verified_consumer_payload_configured"]
    elif source_status == "default_compatible":
        status, payload, reasons = "default_compatible", None, ["default_compatible_integration_consumer"]
    elif source_status == "rejected":
        status, payload, reasons = "rejected", None, ["runtime_integration_consumer_rejected"]
    else:
        status, payload, reasons = "invalid", None, ["invalid_runtime_integration_consumer"]
    base = {
        "schema": SCHEMA,
        "status": status,
        **_linkage(consumer),
        "configuration_payload": payload,
        "reasons": reasons,
        "boundary": {
            "sealed": True,
            "read_only": True,
            "passive_configuration": True,
            "runtime_activation": False,
            "scope_expansion": False,
            "constraint_weakening": False,
        },
    }
    return _identified(base, "configuration_id", "capability-strategy-runtime-integration-configuration-")


build_runtime_integration_configuration = configure_runtime_integration

__all__ = ["SCHEMA", "STATUSES", "build_runtime_integration_configuration", "configure_runtime_integration"]
