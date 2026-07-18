from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_bootstrap_configuration import build_capability_strategy_bootstrap_configuration


SCHEMA = "zero.runtime.capability_strategy_bootstrap_decision.v1"
STATUSES = frozenset({"accepted", "degraded", "default_compatible", "rejected"})


def build_capability_strategy_bootstrap_decision(decision: Any) -> dict[str, Any]:
    configuration = build_capability_strategy_bootstrap_configuration(decision)
    status = {"configured": "accepted", "degraded": "degraded", "default_compatible": "default_compatible", "rejected": "rejected"}[configuration["status"]]
    fields = configuration["configuration"]
    fallback = status == "degraded"
    base = {
        "schema": SCHEMA, "status": status,
        "configuration_linkage": {"configuration_id": configuration["configuration_id"], "fingerprint": configuration["fingerprint"]},
        "source_runtime_decision_linkage": deepcopy(configuration["source_runtime_decision_linkage"]),
        "source_strategy_linkage": deepcopy(configuration["source_strategy_linkage"]),
        "accepted_configuration_fields": sorted(fields) if fields is not None else [],
        "rejected_configuration_fields": ["configuration"] if status == "rejected" else [],
        "downgraded_configuration_fields": ["bootstrap_mode", "execution_mode", "worker_limit", "network_mode", "resource_mode", "accelerator_mode"] if fallback else [],
        "configuration": deepcopy(fields), "fallback_applied": fallback,
        "fallback_reasons": deepcopy(configuration["reasons"]) if fallback else [],
        "compatibility_mode": status == "default_compatible", "reasons": deepcopy(configuration["reasons"]),
        "decision_input_only": True, "authority_granted": False, "executor_ownership_changed": False,
    }
    return _identified(base, "decision_id", "capability-strategy-bootstrap-decision-")


decide_capability_strategy_bootstrap = build_capability_strategy_bootstrap_decision
__all__ = ["SCHEMA", "STATUSES", "build_capability_strategy_bootstrap_decision", "decide_capability_strategy_bootstrap"]
