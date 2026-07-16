from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from core.runtime.runtime_capability_strategy import MAX_WORKERS_HARD_CAP, SCHEMA, STRATEGY_VERSION, compute_strategy_fingerprint, compute_strategy_id


MODES = frozenset({"cpu_only", "accelerator_available", "memory_constrained", "storage_constrained", "offline_safe", "limited_tools", "unknown_capability"})
COMPUTE = frozenset({"cpu", "accelerator", "auto"})
REQUIRED = frozenset({"schema", "strategy_id", "fingerprint", "profile_id", "profile_fingerprint", "strategy_version", "recommended_mode", "execution_preferences", "tool_preferences", "model_preferences", "constraints", "reasons", "diagnostics"})
_SENSITIVE_KEYS = frozenset({"hostname", "username", "home", "environment", "executable", "credential", "credentials", "token", "ip", "mac", "path", "traceback", "exception"})


@dataclass(frozen=True)
class StrategyValidationResult:
    valid: bool
    errors: tuple[str, ...]


def validate_capability_strategy(strategy: Any) -> StrategyValidationResult:
    if not isinstance(strategy, Mapping): return StrategyValidationResult(False, ("strategy_not_object",))
    errors: list[str] = []
    missing = sorted(REQUIRED - set(strategy)); errors.extend(f"missing:{key}" for key in missing)
    errors.extend(f"unexpected:{key}" for key in sorted(set(strategy) - REQUIRED))
    if strategy.get("schema") != SCHEMA: errors.append("invalid_schema")
    if strategy.get("strategy_version") != STRATEGY_VERSION: errors.append("invalid_strategy_version")
    if not strategy.get("strategy_id"): errors.append("invalid_strategy_id")
    if not strategy.get("fingerprint"): errors.append("invalid_fingerprint")
    if not strategy.get("profile_id"): errors.append("invalid_profile_id")
    if not strategy.get("profile_fingerprint"): errors.append("invalid_profile_fingerprint")
    if strategy.get("recommended_mode") not in MODES: errors.append("invalid_recommended_mode")
    preferences = strategy.get("execution_preferences")
    if not isinstance(preferences, Mapping): errors.append("invalid_execution_preferences")
    else:
        if preferences.get("preferred_compute") not in COMPUTE: errors.append("invalid_preferred_compute")
        workers = preferences.get("parallelism", {}).get("max_workers") if isinstance(preferences.get("parallelism"), Mapping) else None
        if not isinstance(workers, int) or isinstance(workers, bool) or not 1 <= workers <= MAX_WORKERS_HARD_CAP: errors.append("invalid_max_workers")
    for section in ("tool_preferences", "model_preferences", "constraints", "reasons", "diagnostics"):
        values = strategy.get(section)
        if not isinstance(values, list): errors.append(f"invalid_section:{section}")
        elif any(not isinstance(item, Mapping) for item in values): errors.append(f"invalid_entry:{section}")
    for section, fields in (("tool_preferences", ("name",)), ("model_preferences", ("provider", "name"))):
        values = strategy.get(section, [])
        if isinstance(values, list):
            keys = [tuple(str(item.get(field, "")) for field in fields) for item in values if isinstance(item, Mapping)]
            if len(keys) != len(set(keys)): errors.append(f"duplicate_entries:{section}")
            if any(not all(key) for key in keys): errors.append(f"invalid_entry:{section}")
    for section in ("constraints", "reasons", "diagnostics"):
        values = strategy.get(section, [])
        if isinstance(values, list) and any(set(item) != {"code"} or not isinstance(item.get("code"), str) or not 1 <= len(item["code"]) <= 64 for item in values if isinstance(item, Mapping)): errors.append(f"unsafe_record:{section}")
    try: json.dumps(strategy, allow_nan=False)
    except (TypeError, ValueError): errors.append("not_json_serializable")
    def contains_sensitive_key(value: Any) -> bool:
        if isinstance(value, Mapping):
            return any(str(key).casefold() in _SENSITIVE_KEYS or contains_sensitive_key(item) for key, item in value.items())
        if isinstance(value, list): return any(contains_sensitive_key(item) for item in value)
        return False
    if contains_sensitive_key(strategy): errors.append("sensitive_field")
    if not missing:
        try:
            if strategy.get("fingerprint") != compute_strategy_fingerprint(strategy): errors.append("fingerprint_mismatch")
            if strategy.get("strategy_id") != compute_strategy_id(strategy): errors.append("strategy_id_mismatch")
        except (TypeError, ValueError): pass
    return StrategyValidationResult(not errors, tuple(errors))


__all__ = ["MODES", "COMPUTE", "REQUIRED", "StrategyValidationResult", "validate_capability_strategy"]
