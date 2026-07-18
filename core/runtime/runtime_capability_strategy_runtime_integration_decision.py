from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_integration_configuration_validation import validate_runtime_integration_configuration

SCHEMA = "zero.runtime.capability_strategy_runtime_integration_decision.v1"
STATUSES = frozenset({"decided", "default_compatible", "rejected", "invalid"})


def _linkage(source: Any) -> dict[str, Any]:
    value = source if isinstance(source, Mapping) else {}
    result = {"source_configuration_id": value.get("configuration_id"), "source_configuration_fingerprint": value.get("fingerprint")}
    for key in (
        "source_integration_consumer_id", "source_integration_consumer_fingerprint",
        "source_integration_boundary_id", "source_integration_boundary_fingerprint",
        "source_consumption_id", "source_consumption_fingerprint", "source_wiring_id",
        "source_wiring_fingerprint", "source_bootstrap_configuration_id",
        "source_bootstrap_configuration_fingerprint", "source_runtime_decision_id",
        "source_strategy_id", "source_profile_id",
    ):
        result[key] = value.get(key)
    return result


def decide_runtime_integration(configuration: Any) -> dict[str, Any]:
    valid = validate_runtime_integration_configuration(configuration).valid
    source_status = configuration.get("status") if isinstance(configuration, Mapping) else None
    mapping = {"configured": "decided", "default_compatible": "default_compatible", "rejected": "rejected", "invalid": "invalid"}
    status = mapping.get(source_status, "invalid") if valid else "invalid"
    payload = deepcopy(configuration["configuration_payload"]) if status == "decided" else None
    reasons = {
        "decided": ["verified_configuration_decided"], "default_compatible": ["default_compatible_configuration"],
        "rejected": ["runtime_integration_configuration_rejected"], "invalid": ["invalid_runtime_integration_configuration"],
    }[status]
    base = {
        "schema": SCHEMA, "status": status, **_linkage(configuration),
        "decision_payload": payload, "reasons": reasons,
        "boundary": {"sealed": True, "read_only": True, "passive_decision": True,
                     "runtime_activation": False, "scope_expansion": False,
                     "constraint_weakening": False, "authority_granted": False},
    }
    return _identified(base, "decision_id", "capability-strategy-runtime-integration-decision-")


build_runtime_integration_decision = decide_runtime_integration
__all__ = ["SCHEMA", "STATUSES", "build_runtime_integration_decision", "decide_runtime_integration"]
