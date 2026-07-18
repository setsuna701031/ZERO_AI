from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.runtime.runtime_capability_strategy_runtime_consumer import _identified, consume_capability_strategy


SCHEMA = "zero.runtime.capability_strategy_runtime_integration.v1"
STATUSES = frozenset({"integrated", "fallback", "default_compatible", "invalid"})


def build_capability_strategy_runtime_integration(strategy: Any = None, *, enabled: bool = True) -> dict[str, Any]:
    consumer = consume_capability_strategy(strategy, enabled=enabled)
    status = {"consumed": "integrated", "fallback": "fallback", "default_compatible": "default_compatible", "invalid": "invalid"}[consumer["status"]]
    base = {
        "schema": SCHEMA, "status": status,
        "consumer_result_linkage": {"consumer_id": consumer["consumer_id"], "fingerprint": consumer["fingerprint"]},
        "source_strategy_linkage": deepcopy(consumer["source_strategy_linkage"]),
        "runtime_directives": deepcopy(consumer["runtime_directives"]),
        "compatibility_mode": consumer["compatibility_mode"], "reasons": deepcopy(consumer["reasons"]),
        "decision_input_only": True, "executor_ownership_changed": False,
    }
    return _identified(base, "integration_id", "capability-strategy-integration-")


integrate_capability_strategy_runtime = build_capability_strategy_runtime_integration
__all__ = ["SCHEMA", "STATUSES", "build_capability_strategy_runtime_integration", "integrate_capability_strategy_runtime"]
