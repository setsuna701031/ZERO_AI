from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_integration_decision_validation import validate_runtime_integration_decision

SCHEMA = "zero.runtime.capability_strategy_runtime_integration_wiring.v1"
STATUSES = frozenset({"wired", "default_compatible", "rejected", "invalid"})


def _linkage(source: Any) -> dict[str, Any]:
    value = source if isinstance(source, Mapping) else {}
    result = {"source_decision_id": value.get("decision_id"), "source_decision_fingerprint": value.get("fingerprint")}
    for key in value:
        if key.startswith("source_"):
            result[key] = value.get(key)
    return result


def wire_runtime_integration(decision: Any) -> dict[str, Any]:
    valid = validate_runtime_integration_decision(decision).valid
    source_status = decision.get("status") if isinstance(decision, Mapping) else None
    status = ({"decided": "wired", "default_compatible": "default_compatible", "rejected": "rejected", "invalid": "invalid"}.get(source_status, "invalid") if valid else "invalid")
    payload = deepcopy(decision["decision_payload"]) if status == "wired" else None
    reasons = {"wired": ["verified_decision_passively_wired"], "default_compatible": ["default_compatible_decision"],
               "rejected": ["runtime_integration_decision_rejected"], "invalid": ["invalid_runtime_integration_decision"]}[status]
    base = {
        "schema": SCHEMA, "status": status, **_linkage(decision), "wiring_payload": payload, "reasons": reasons,
        "boundary": {"sealed": True, "read_only": True, "passive_wiring": True, "runtime_activation": False,
                     "scope_expansion": False, "constraint_weakening": False, "authority_granted": False,
                     "live_binding": False},
    }
    return _identified(base, "wiring_id", "capability-strategy-runtime-integration-wiring-")


build_runtime_integration_wiring = wire_runtime_integration
__all__ = ["SCHEMA", "STATUSES", "build_runtime_integration_wiring", "wire_runtime_integration"]
