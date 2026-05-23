from __future__ import annotations

from typing import Any, Dict, List

from core.runtime.snapshot_loader.snapshot_loader import (
    load_runtime_awareness_bundle,
)


def get_runtime_stage() -> Dict[str, Any]:
    bundle = load_runtime_awareness_bundle()

    runtime_state = bundle.get("runtime_state_snapshot", {})
    data = runtime_state.get("data", {})

    return {
        "runtime_stage": data.get("runtime_stage", "unknown"),
        "runtime_identity": data.get("runtime_identity", "unknown"),
    }


def get_enabled_capabilities() -> List[str]:
    bundle = load_runtime_awareness_bundle()

    runtime_state = bundle.get("runtime_state_snapshot", {})
    data = runtime_state.get("data", {})

    capabilities = []

    capability_suffixes = (
        "_enabled",
        "_execution",
        "_evaluation",
        "_registry",
        "_engine",
        "_bridge",
        "_graph",
    )

    for key, value in data.items():
        if (
            isinstance(value, bool)
            and value is True
            and key.endswith(capability_suffixes)
        ):
            capabilities.append(key)

    return sorted(capabilities)


def get_blocked_capabilities() -> List[str]:
    bundle = load_runtime_awareness_bundle()

    runtime_state = bundle.get("runtime_state_snapshot", {})
    data = runtime_state.get("data", {})

    return data.get("blocked_capabilities", [])


def mutation_runtime_enabled() -> bool:
    bundle = load_runtime_awareness_bundle()

    runtime_state = bundle.get("runtime_state_snapshot", {})
    data = runtime_state.get("data", {})

    return bool(data.get("mutation_runtime_enabled", False))


def get_runtime_governance_rules() -> List[str]:
    bundle = load_runtime_awareness_bundle()

    runtime_state = bundle.get("runtime_state_snapshot", {})
    data = runtime_state.get("data", {})

    return data.get("governance_rules", [])


def get_runtime_awareness_summary() -> Dict[str, Any]:
    return {
        "runtime_stage": get_runtime_stage(),
        "enabled_capabilities": get_enabled_capabilities(),
        "blocked_capabilities": get_blocked_capabilities(),
        "mutation_runtime_enabled": mutation_runtime_enabled(),
        "governance_rules": get_runtime_governance_rules(),
    }