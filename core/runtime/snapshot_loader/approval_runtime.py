from __future__ import annotations

from typing import Any, Dict

from core.runtime.snapshot_loader.policy_decision import decide_execution_policy


_APPROVAL_STATES = {
    "not_required",
    "pending_review",
    "approved",
    "denied",
    "governance_locked",
}


def build_approval_request(action: str, request_id: str = "approval-request") -> Dict[str, Any]:
    policy = decide_execution_policy(action)

    if policy["decision"] == "allow":
        state = "not_required"
    elif policy["decision"] == "review_required":
        state = "pending_review"
    else:
        state = "governance_locked"

    return {
        "request_id": request_id,
        "action": policy["action"],
        "state": state,
        "policy": policy,
        "approval_required": policy["approval_required"],
        "audit_required": policy["audit_required"],
    }


def transition_approval_state(
    approval_request: Dict[str, Any],
    decision: str,
) -> Dict[str, Any]:
    if not isinstance(approval_request, dict):
        raise TypeError("approval_request must be a dict")
    if decision not in {"approve", "deny"}:
        raise ValueError("decision must be approve or deny")

    current_state = approval_request.get("state")

    if current_state not in _APPROVAL_STATES:
        raise ValueError("approval_request.state is invalid")

    if current_state == "not_required":
        return {
            **approval_request,
            "transition": "ignored",
            "state": "not_required",
            "final": True,
        }

    if current_state == "governance_locked":
        return {
            **approval_request,
            "transition": "blocked",
            "state": "governance_locked",
            "final": True,
        }

    if current_state == "pending_review":
        if decision == "approve":
            return {
                **approval_request,
                "transition": "approved",
                "state": "approved",
                "final": True,
            }

        return {
            **approval_request,
            "transition": "denied",
            "state": "denied",
            "final": True,
        }

    return {
        **approval_request,
        "transition": "already_final",
        "final": True,
    }


def is_execution_approved(approval_request: Dict[str, Any]) -> bool:
    if not isinstance(approval_request, dict):
        raise TypeError("approval_request must be a dict")

    return approval_request.get("state") in {"not_required", "approved"}


def build_approval_runtime_summary() -> Dict[str, Any]:
    actions = [
        "readonly_execution",
        "mutation_runtime",
        "patch_apply",
        "unrestricted_shell",
    ]

    requests = [
        build_approval_request(action, request_id=f"approval-{action}")
        for action in actions
    ]

    return {
        "approval_runtime": "snapshot_loader_approval_runtime",
        "requests": requests,
        "not_required_actions": [
            item["action"]
            for item in requests
            if item["state"] == "not_required"
        ],
        "pending_review_actions": [
            item["action"]
            for item in requests
            if item["state"] == "pending_review"
        ],
        "governance_locked_actions": [
            item["action"]
            for item in requests
            if item["state"] == "governance_locked"
        ],
    }