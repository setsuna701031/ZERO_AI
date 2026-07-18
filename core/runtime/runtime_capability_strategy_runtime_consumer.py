from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy import canonical_json
from core.runtime.runtime_capability_strategy_validation import validate_capability_strategy


SCHEMA = "zero.runtime.capability_strategy_runtime_consumer.v1"
STATUSES = frozenset({"consumed", "fallback", "default_compatible", "invalid"})


def _identified(value: dict[str, Any], key: str, prefix: str) -> dict[str, Any]:
    identity = {name: deepcopy(item) for name, item in value.items() if name not in {key, "fingerprint"}}
    fingerprint = hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()
    value["fingerprint"] = fingerprint
    value[key] = prefix + fingerprint[:24]
    return json.loads(canonical_json(value))


def _linkage(strategy: Any) -> dict[str, Any]:
    if not isinstance(strategy, Mapping):
        return {"strategy_id": None, "fingerprint": None, "profile_id": None, "profile_fingerprint": None}
    return {
        "strategy_id": strategy.get("strategy_id"), "fingerprint": strategy.get("fingerprint"),
        "profile_id": strategy.get("profile_id"), "profile_fingerprint": strategy.get("profile_fingerprint"),
    }


def build_runtime_directives(strategy: Mapping[str, Any]) -> dict[str, Any]:
    preferences = strategy["execution_preferences"]
    mode = strategy["recommended_mode"]
    unknown = mode == "unknown_capability"
    compute = preferences["preferred_compute"]
    declared_tools = sorted({str(item["name"]) for item in strategy["tool_preferences"]}, key=str.casefold)
    workers = preferences["parallelism"]["max_workers"]
    network = preferences["network_policy"]["mode"]
    resource_mode = "constrained" if mode in {"memory_constrained", "storage_constrained"} else preferences["memory_policy"]["mode"]
    accelerator = "disabled" if unknown or compute != "accelerator" else (preferences.get("preferred_accelerator_kind") or "available")
    return {
        "execution_mode": "cpu_only" if unknown else mode,
        "worker_limit": 1 if unknown else workers,
        "network_mode": "offline_safe" if unknown else network,
        "resource_mode": "safe_minimum" if unknown else resource_mode,
        "accelerator_mode": accelerator,
        "available_tools": declared_tools,
        "fallback_applied": unknown,
        "source_strategy_id": strategy["strategy_id"],
        "source_strategy_fingerprint": strategy["fingerprint"],
    }


def consume_capability_strategy(strategy: Any = None, *, enabled: bool = True) -> dict[str, Any]:
    linkage = _linkage(strategy)
    if strategy is None or not enabled:
        status, directives, reasons = "default_compatible", None, ["strategy_unavailable" if strategy is None else "consumer_disabled"]
    elif not validate_capability_strategy(strategy).valid:
        status, directives, reasons = "invalid", None, ["invalid_strategy"]
    else:
        directives = build_runtime_directives(strategy)
        status = "fallback" if directives["fallback_applied"] else "consumed"
        reasons = ["unknown_capability_safe_fallback"] if status == "fallback" else ["canonical_strategy_consumed"]
    base = {
        "schema": SCHEMA, "status": status, "source_strategy_linkage": linkage,
        "runtime_directives": directives, "compatibility_mode": status == "default_compatible",
        "reasons": reasons,
        "boundary": {"read_only": True, "execution_authority": False, "mutation_authority": False},
    }
    return _identified(base, "consumer_id", "capability-strategy-consumer-")


__all__ = ["SCHEMA", "STATUSES", "build_runtime_directives", "consume_capability_strategy"]
