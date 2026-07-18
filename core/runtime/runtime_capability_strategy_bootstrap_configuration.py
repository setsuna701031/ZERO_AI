from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_bootstrap_consumer import consume_runtime_strategy_decision


SCHEMA = "zero.runtime.capability_strategy_bootstrap_configuration.v1"
STATUSES = frozenset({"configured", "degraded", "default_compatible", "rejected"})


def build_capability_strategy_bootstrap_configuration(decision: Any) -> dict[str, Any]:
    consumer = consume_runtime_strategy_decision(decision)
    status = {"consumed": "configured", "fallback": "degraded", "default_compatible": "default_compatible", "rejected": "rejected"}[consumer["status"]]
    base = {
        "schema": SCHEMA, "status": status,
        "consumer_linkage": {"consumer_id": consumer["consumer_id"], "fingerprint": consumer["fingerprint"]},
        "source_runtime_decision_linkage": deepcopy(consumer["source_runtime_decision_linkage"]),
        "source_strategy_linkage": deepcopy(consumer["source_strategy_linkage"]),
        "configuration": deepcopy(consumer["configuration_fields"]),
        "compatibility_mode": status == "default_compatible", "reasons": deepcopy(consumer["reasons"]),
        "decision_input_only": True, "authority_granted": False, "executor_ownership_changed": False,
    }
    return _identified(base, "configuration_id", "capability-strategy-bootstrap-configuration-")


configure_capability_strategy_bootstrap = build_capability_strategy_bootstrap_configuration
__all__ = ["SCHEMA", "STATUSES", "build_capability_strategy_bootstrap_configuration", "configure_capability_strategy_bootstrap"]
