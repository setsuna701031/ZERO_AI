from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from core.runtime.runtime_capability_profile import RuntimeCapabilityProfile
from core.runtime.runtime_capability_strategy import LOW_MEMORY_AVAILABLE_BYTES, LOW_STORAGE_FREE_BYTES, MAX_WORKERS_HARD_CAP, RuntimeCapabilityStrategy
from core.runtime.runtime_capability_validation import validate_capability_profile


def _snapshot(profile: Any) -> dict[str, Any] | None:
    try:
        value = profile.to_dict() if isinstance(profile, RuntimeCapabilityProfile) else deepcopy(dict(profile))
        return value
    except (TypeError, ValueError, AttributeError):
        return None


def _record(code: str) -> dict[str, str]:
    return {"code": code}


def _fail_safe() -> RuntimeCapabilityStrategy:
    return RuntimeCapabilityStrategy.create({
        "profile_id": "invalid-profile", "profile_fingerprint": "invalid-profile",
        "recommended_mode": "unknown_capability",
        "execution_preferences": {
            "preferred_compute": "cpu", "preferred_accelerator_kind": None,
            "parallelism": {"max_workers": 1, "reason": "unknown_capability"},
            "memory_policy": {"mode": "conservative", "reason": "invalid_profile"},
            "storage_policy": {"mode": "bounded", "minimum_free_bytes": None},
            "network_policy": {"mode": "offline_safe", "outbound_required": False},
        },
        "tool_preferences": [], "model_preferences": [], "constraints": [_record("invalid_profile")],
        "reasons": [_record("fail_safe_default")], "diagnostics": [_record("profile_validation_failed")],
    })


def select_capability_strategy(profile: Any) -> RuntimeCapabilityStrategy:
    value = _snapshot(profile)
    if value is None or not validate_capability_profile(value).valid:
        return _fail_safe()

    constraints: list[dict[str, str]] = []
    reasons: list[dict[str, str]] = []
    diagnostics: list[dict[str, str]] = []
    cores = value.get("cpu", {}).get("logical_cores")
    workers = min(cores, MAX_WORKERS_HARD_CAP) if isinstance(cores, int) and not isinstance(cores, bool) and cores > 0 else 1
    worker_reason = "bounded_by_logical_cores" if workers > 1 else "bounded_default"

    memory = value.get("memory", {}).get("available_bytes")
    memory_low = isinstance(memory, int) and not isinstance(memory, bool) and memory < LOW_MEMORY_AVAILABLE_BYTES
    memory_mode = "constrained" if memory_low else "balanced" if isinstance(memory, int) else "conservative"
    memory_reason = "low_available_memory" if memory_low else "known_memory" if isinstance(memory, int) else "unknown_or_limited_memory"

    known_free = [item.get("free_bytes") for item in value.get("storage", []) if isinstance(item, Mapping) and isinstance(item.get("free_bytes"), int) and not isinstance(item.get("free_bytes"), bool)]
    storage_low = bool(known_free) and min(known_free) < LOW_STORAGE_FREE_BYTES
    storage_mode = "constrained" if storage_low else "bounded"
    minimum_free = min(known_free) if known_free else None

    accelerators = [item for item in value.get("accelerators", []) if isinstance(item, Mapping) and item.get("available") is True]
    accelerator = accelerators[0] if accelerators else None
    power_constrained = value.get("power", {}).get("constrained") is True
    preferred_compute = "accelerator" if accelerator else "cpu"
    accelerator_kind = str(accelerator.get("kind")) if accelerator and accelerator.get("kind") else None
    if power_constrained:
        preferred_compute, accelerator_kind, workers = "cpu", None, min(workers, 2)
        constraints.append(_record("power_constrained")); reasons.append(_record("power_conservative"))

    available_tools = sorted({str(item.get("name")) for item in value.get("available_tools", []) if isinstance(item, Mapping) and item.get("available") is True and item.get("name")})
    if not available_tools: constraints.append(_record("limited_tools"))
    elif any(isinstance(item, Mapping) and item.get("available") is not True for item in value.get("available_tools", [])):
        constraints.append(_record("unavailable_tools"))
    models = sorted(
        ({"provider": str(item.get("provider") or "unknown"), "name": str(item.get("name"))} for item in value.get("installed_models", []) if isinstance(item, Mapping) and item.get("name")),
        key=lambda item: (item["provider"].casefold(), item["name"].casefold()),
    )
    if memory_low:
        mode = "memory_constrained"; constraints.append(_record("memory_constrained"))
    elif storage_low:
        mode = "storage_constrained"; constraints.append(_record("storage_constrained"))
    elif accelerator and not power_constrained:
        mode = "accelerator_available"; reasons.append(_record("available_accelerator"))
    else:
        mode = "cpu_only"; reasons.append(_record("safe_cpu_fallback"))
    if value.get("network", {}).get("outbound_connectivity_tested") is not True:
        constraints.append(_record("offline_safe"))

    return RuntimeCapabilityStrategy.create({
        "profile_id": str(value["profile_id"]), "profile_fingerprint": str(value["fingerprint"]),
        "recommended_mode": mode,
        "execution_preferences": {
            "preferred_compute": preferred_compute, "preferred_accelerator_kind": accelerator_kind,
            "parallelism": {"max_workers": workers, "reason": worker_reason},
            "memory_policy": {"mode": memory_mode, "reason": memory_reason},
            "storage_policy": {"mode": storage_mode, "minimum_free_bytes": minimum_free},
            "network_policy": {"mode": "offline_safe", "outbound_required": False},
        },
        "tool_preferences": [{"name": name} for name in available_tools], "model_preferences": models,
        "constraints": constraints, "reasons": reasons, "diagnostics": diagnostics,
    })


class RuntimeCapabilityStrategySelector:
    def select(self, profile: Any) -> RuntimeCapabilityStrategy:
        return select_capability_strategy(profile)


__all__ = ["RuntimeCapabilityStrategySelector", "select_capability_strategy"]
