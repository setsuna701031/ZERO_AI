from __future__ import annotations

from typing import Any, Dict

from core.runtime.snapshot_loader.capability_gate import (
    can_apply_patch,
    can_use_controlled_execution_bridge,
    can_use_mutation_runtime,
    can_use_network_install,
    can_use_readonly_execution,
    can_write_repo,
    evaluate_capability_request,
    get_runtime_capability_gate_state,
)


def normalize_runtime_action(action: str) -> str:
    return str(action or "").strip().lower().replace("-", "_").replace(" ", "_")


def route_runtime_action(action: str) -> Dict[str, Any]:
    normalized = normalize_runtime_action(action)
    gate_state = get_runtime_capability_gate_state()

    action_to_capability = {
        "readonly_execution": "readonly_execution",
        "execute_readonly": "readonly_execution",
        "controlled_execution": "controlled_execution_bridge",
        "controlled_execution_bridge": "controlled_execution_bridge",
        "replay": "execution_replay_engine",
        "runtime_replay": "execution_replay_engine",
        "evidence_registry": "runtime_evidence_registry",
        "lineage_graph": "execution_lineage_graph",
        "governance_evaluation": "runtime_governance_evaluation",
        "health_evaluation": "runtime_health_evaluation",
        "mutation_readiness": "mutation_readiness_evaluation",
        "mutation_runtime": "mutation_runtime",
        "mutation": "mutation_runtime",
        "patch_apply": "patch_apply",
        "repo_write": "repo_write",
        "network_install": "network_install",
        "unrestricted_shell": "shell",
    }

    capability = action_to_capability.get(normalized, normalized)
    evaluation = evaluate_capability_request(capability)

    allowed = bool(evaluation.get("allowed", False))
    reason = evaluation.get("reason", "capability blocked or not enabled")

    if normalized in {"readonly_execution", "execute_readonly"}:
        allowed = can_use_readonly_execution()
        reason = "readonly execution allowed" if allowed else "readonly execution not enabled"

    elif normalized in {"controlled_execution", "controlled_execution_bridge"}:
        allowed = can_use_controlled_execution_bridge()
        reason = (
            "controlled execution bridge allowed"
            if allowed
            else "controlled execution bridge not enabled"
        )

    elif normalized in {"mutation", "mutation_runtime"}:
        allowed = can_use_mutation_runtime()
        reason = (
            "mutation runtime allowed"
            if allowed
            else "mutation runtime disabled or blocked"
        )

    elif normalized == "patch_apply":
        allowed = can_apply_patch()
        reason = "patch apply allowed" if allowed else "patch apply blocked"

    elif normalized == "repo_write":
        allowed = can_write_repo()
        reason = "repo write allowed" if allowed else "repo write blocked"

    elif normalized == "network_install":
        allowed = can_use_network_install()
        reason = "network install allowed" if allowed else "network install blocked"

    elif normalized == "unrestricted_shell":
        allowed = False
        reason = "unrestricted shell blocked"

    return {
        "route_type": "runtime_governed_execution_route",
        "action": action,
        "normalized_action": normalized,
        "capability": capability,
        "allowed": allowed,
        "blocked": not allowed,
        "reason": reason,
        "capability_evaluation": evaluation,
        "gate_state": gate_state,
    }


def route_readonly_execution() -> Dict[str, Any]:
    return route_runtime_action("readonly_execution")


def route_controlled_execution_bridge() -> Dict[str, Any]:
    return route_runtime_action("controlled_execution_bridge")


def route_mutation_runtime() -> Dict[str, Any]:
    return route_runtime_action("mutation_runtime")


def route_patch_apply() -> Dict[str, Any]:
    return route_runtime_action("patch_apply")


def route_repo_write() -> Dict[str, Any]:
    return route_runtime_action("repo_write")


def route_network_install() -> Dict[str, Any]:
    return route_runtime_action("network_install")


def route_unrestricted_shell() -> Dict[str, Any]:
    return route_runtime_action("unrestricted_shell")


def build_runtime_routing_summary() -> Dict[str, Any]:
    actions = [
        "readonly_execution",
        "controlled_execution_bridge",
        "runtime_replay",
        "evidence_registry",
        "lineage_graph",
        "governance_evaluation",
        "health_evaluation",
        "mutation_readiness",
        "mutation_runtime",
        "patch_apply",
        "repo_write",
        "network_install",
        "unrestricted_shell",
    ]

    routes = [route_runtime_action(action) for action in actions]

    return {
        "summary_type": "runtime_governed_execution_routing_summary",
        "routes": routes,
        "allowed_actions": [
            item["normalized_action"] for item in routes if item.get("allowed")
        ],
        "blocked_actions": [
            item["normalized_action"] for item in routes if not item.get("allowed")
        ],
    }