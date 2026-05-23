from __future__ import annotations

from typing import Any, Dict

from core.runtime.snapshot_loader.execution_classification import (
    classify_execution_action,
)


def decide_execution_policy(action: str) -> Dict[str, Any]:
    classification = classify_execution_action(action)

    action_name = classification["action"]
    risk_level = classification["risk_level"]
    mutation_capable = classification["mutation_capable"]
    governance_critical = classification["governance_critical"]
    replay_sensitive = classification["replay_sensitive"]

    if action_name == "readonly_execution":
        decision = "allow"
        reason = "readonly_execution_allowed"
        approval_required = False
        audit_required = False
    elif action_name in {"mutation_runtime", "patch_apply"}:
        decision = "review_required"
        reason = "mutation_surface_requires_review"
        approval_required = True
        audit_required = True
    elif action_name == "unrestricted_shell":
        decision = "deny"
        reason = "unrestricted_shell_denied"
        approval_required = True
        audit_required = True
    else:
        decision = "deny"
        reason = "unknown_action_denied"
        approval_required = True
        audit_required = True

    return {
        "action": action_name,
        "decision": decision,
        "reason": reason,
        "approval_required": approval_required,
        "audit_required": audit_required,
        "classification": classification["classification"],
        "risk_level": risk_level,
        "mutation_capable": mutation_capable,
        "governance_critical": governance_critical,
        "replay_sensitive": replay_sensitive,
    }


def build_policy_decision_summary() -> Dict[str, Any]:
    actions = [
        "readonly_execution",
        "mutation_runtime",
        "patch_apply",
        "unrestricted_shell",
    ]

    decisions = [
        decide_execution_policy(action)
        for action in actions
    ]

    return {
        "policy_layer": "runtime_policy_decision",
        "decisions": decisions,
        "allowed_actions": [
            item["action"]
            for item in decisions
            if item["decision"] == "allow"
        ],
        "review_required_actions": [
            item["action"]
            for item in decisions
            if item["decision"] == "review_required"
        ],
        "denied_actions": [
            item["action"]
            for item in decisions
            if item["decision"] == "deny"
        ],
    }