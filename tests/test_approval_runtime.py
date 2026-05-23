from __future__ import annotations

import pytest

from core.runtime.snapshot_loader.approval_runtime import (
    build_approval_request,
    build_approval_runtime_summary,
    is_execution_approved,
    transition_approval_state,
)


def test_readonly_execution_does_not_require_approval() -> None:
    request = build_approval_request("readonly_execution", request_id="r1")

    assert request["request_id"] == "r1"
    assert request["action"] == "readonly_execution"
    assert request["state"] == "not_required"
    assert request["approval_required"] is False
    assert is_execution_approved(request) is True


def test_mutation_runtime_requires_pending_review() -> None:
    request = build_approval_request("mutation_runtime", request_id="m1")

    assert request["action"] == "mutation_runtime"
    assert request["state"] == "pending_review"
    assert request["approval_required"] is True
    assert request["audit_required"] is True
    assert is_execution_approved(request) is False


def test_patch_apply_requires_pending_review() -> None:
    request = build_approval_request("patch_apply", request_id="p1")

    assert request["action"] == "patch_apply"
    assert request["state"] == "pending_review"
    assert request["approval_required"] is True
    assert request["audit_required"] is True
    assert is_execution_approved(request) is False


def test_unrestricted_shell_is_governance_locked() -> None:
    request = build_approval_request("unrestricted_shell", request_id="s1")

    assert request["action"] == "unrestricted_shell"
    assert request["state"] == "governance_locked"
    assert request["approval_required"] is True
    assert request["audit_required"] is True
    assert is_execution_approved(request) is False


def test_pending_review_can_be_approved() -> None:
    request = build_approval_request("mutation_runtime", request_id="m2")
    transitioned = transition_approval_state(request, "approve")

    assert transitioned["state"] == "approved"
    assert transitioned["transition"] == "approved"
    assert transitioned["final"] is True
    assert is_execution_approved(transitioned) is True


def test_pending_review_can_be_denied() -> None:
    request = build_approval_request("mutation_runtime", request_id="m3")
    transitioned = transition_approval_state(request, "deny")

    assert transitioned["state"] == "denied"
    assert transitioned["transition"] == "denied"
    assert transitioned["final"] is True
    assert is_execution_approved(transitioned) is False


def test_not_required_transition_is_ignored() -> None:
    request = build_approval_request("readonly_execution", request_id="r2")
    transitioned = transition_approval_state(request, "approve")

    assert transitioned["state"] == "not_required"
    assert transitioned["transition"] == "ignored"
    assert transitioned["final"] is True
    assert is_execution_approved(transitioned) is True


def test_governance_locked_cannot_be_approved() -> None:
    request = build_approval_request("unrestricted_shell", request_id="s2")
    transitioned = transition_approval_state(request, "approve")

    assert transitioned["state"] == "governance_locked"
    assert transitioned["transition"] == "blocked"
    assert transitioned["final"] is True
    assert is_execution_approved(transitioned) is False


def test_transition_rejects_invalid_decision() -> None:
    request = build_approval_request("mutation_runtime", request_id="m4")

    with pytest.raises(ValueError):
        transition_approval_state(request, "maybe")


def test_transition_rejects_invalid_state() -> None:
    with pytest.raises(ValueError):
        transition_approval_state(
            {
                "request_id": "bad",
                "action": "mutation_runtime",
                "state": "broken_state",
            },
            "approve",
        )


def test_approval_runtime_summary_contract() -> None:
    summary = build_approval_runtime_summary()

    assert summary["approval_runtime"] == "snapshot_loader_approval_runtime"
    assert summary["not_required_actions"] == ["readonly_execution"]
    assert summary["pending_review_actions"] == [
        "mutation_runtime",
        "patch_apply",
    ]
    assert summary["governance_locked_actions"] == ["unrestricted_shell"]
    assert len(summary["requests"]) == 4