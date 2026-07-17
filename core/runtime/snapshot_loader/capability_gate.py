from __future__ import annotations

from typing import Any, Dict, List

from core.runtime.snapshot_loader.awareness_query import (
    get_blocked_capabilities,
    get_enabled_capabilities,
    get_runtime_awareness_summary,
    mutation_runtime_enabled,
)


def _normalize_capability_name(capability: str) -> str:
    return str(capability or "").strip().lower().replace("-", "_").replace(" ", "_")


def get_runtime_capability_gate_state() -> Dict[str, Any]:
    summary = get_runtime_awareness_summary()

    enabled = [_normalize_capability_name(item) for item in get_enabled_capabilities()]
    blocked = [_normalize_capability_name(item) for item in get_blocked_capabilities()]

    return {
        "gate_type": "runtime_capability_gate_state",
        "runtime_stage": summary.get("runtime_stage", {}),
        "enabled_capabilities": sorted(enabled),
        "blocked_capabilities": sorted(blocked),
        "mutation_runtime_enabled": mutation_runtime_enabled(),
        "governance_rules": summary.get("governance_rules", []),
    }


def is_capability_enabled(capability: str) -> bool:
    normalized = _normalize_capability_name(capability)
    state = get_runtime_capability_gate_state()
    return normalized in state.get("enabled_capabilities", [])


def is_capability_blocked(capability: str) -> bool:
    normalized = _normalize_capability_name(capability)
    state = get_runtime_capability_gate_state()

    blocked = state.get("blocked_capabilities", [])

    if normalized in blocked:
        return True

    blocked_aliases = {
        "mutation": ["repo_mutation", "direct_repo_mutation", "direct_repo_write"],
        "repo_write": ["repo_mutation", "direct_repo_write", "direct_file_overwrite"],
        "patch_apply": ["patch_apply"],
        "git_commit": ["git_commit", "git_commit"],
        "git_push": ["git_push"],
        "network": ["network_install", "network"],
        "install": ["network_install", "pip_install", "npm_install"],
        "shell": ["unrestricted_shell", "arbitrary_subprocess", "shell_chaining"],
        "auto_rollback": ["auto_rollback"],
    }

    for alias in blocked_aliases.get(normalized, []):
        if alias in blocked:
            return True

    return False


def can_use_readonly_execution() -> bool:
    return is_capability_enabled("readonly_execution")


def can_use_controlled_execution_bridge() -> bool:
    return is_capability_enabled("controlled_execution_bridge")


def can_use_replay_engine() -> bool:
    return is_capability_enabled("execution_replay_engine")


def can_use_runtime_evidence_registry() -> bool:
    return is_capability_enabled("runtime_evidence_registry")


def can_use_execution_lineage_graph() -> bool:
    return is_capability_enabled("execution_lineage_graph")


def can_use_runtime_governance_evaluation() -> bool:
    return is_capability_enabled("runtime_governance_evaluation")


def can_use_mutation_runtime() -> bool:
    return mutation_runtime_enabled() and not is_capability_blocked("mutation")


def can_apply_patch() -> bool:
    return False if is_capability_blocked("patch_apply") else is_capability_enabled("patch_apply")


def can_write_repo() -> bool:
    return False if is_capability_blocked("repo_write") else is_capability_enabled("repo_write")


def can_use_network_install() -> bool:
    return False if is_capability_blocked("network") else is_capability_enabled("network_install")


def evaluate_capability_request(capability: str) -> Dict[str, Any]:
    normalized = _normalize_capability_name(capability)

    enabled = is_capability_enabled(normalized)
    blocked = is_capability_blocked(normalized)

    allowed = enabled and not blocked

    if normalized == "mutation_runtime":
        allowed = can_use_mutation_runtime()
        blocked = not allowed

    return {
        "gate_type": "runtime_capability_request_evaluation",
        "capability": capability,
        "normalized_capability": normalized,
        "enabled": enabled,
        "blocked": blocked,
        "allowed": allowed,
        "reason": (
            "capability allowed"
            if allowed
            else "capability blocked or not enabled"
        ),
    }


def evaluate_capability_requests(capabilities: List[str]) -> Dict[str, Any]:
    evaluations = [evaluate_capability_request(item) for item in capabilities]

    return {
        "gate_type": "runtime_capability_batch_evaluation",
        "evaluations": evaluations,
        "all_allowed": all(item.get("allowed", False) for item in evaluations),
        "any_blocked": any(item.get("blocked", False) for item in evaluations),
    }