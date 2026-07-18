from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified
from core.runtime.runtime_capability_strategy_runtime_integration import build_capability_strategy_runtime_integration


SCHEMA = "zero.runtime.capability_strategy_runtime_decision.v1"
STATUSES = frozenset({"accepted", "degraded", "default_compatible", "rejected"})


def build_capability_strategy_runtime_decision(strategy: Any = None, *, enabled: bool = True) -> dict[str, Any]:
    integration = build_capability_strategy_runtime_integration(strategy, enabled=enabled)
    status = {"integrated": "accepted", "fallback": "degraded", "default_compatible": "default_compatible", "invalid": "rejected"}[integration["status"]]
    directives = integration["runtime_directives"]
    fallback = status == "degraded"
    base = {
        "schema": SCHEMA, "status": status,
        "integration_linkage": {"integration_id": integration["integration_id"], "fingerprint": integration["fingerprint"]},
        "consumer_result_linkage": deepcopy(integration["consumer_result_linkage"]),
        "strategy_linkage": deepcopy(integration["source_strategy_linkage"]),
        "profile_linkage": {"profile_id": integration["source_strategy_linkage"]["profile_id"], "fingerprint": integration["source_strategy_linkage"]["profile_fingerprint"]},
        "accepted_directives": deepcopy(directives) if directives is not None else {},
        "rejected_directives": [] if status in {"accepted", "degraded"} else (["strategy_input"] if status == "rejected" else []),
        "degraded_directives": ["execution_mode", "worker_limit", "network_mode", "resource_mode", "accelerator_mode"] if fallback else [],
        "fallback_applied": fallback, "fallback_reason": "unknown_capability" if fallback else None,
        "compatibility_mode": integration["compatibility_mode"], "reasons": deepcopy(integration["reasons"]),
        "decision_input_only": True, "authority_granted": False,
    }
    return _identified(base, "decision_id", "capability-strategy-decision-")


decide_capability_strategy_runtime = build_capability_strategy_runtime_decision
__all__ = ["SCHEMA", "STATUSES", "build_capability_strategy_runtime_decision", "decide_capability_strategy_runtime"]
