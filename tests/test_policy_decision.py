from __future__ import annotations

from core.runtime.snapshot_loader.policy_decision import (
    build_policy_decision_summary,
    decide_execution_policy,
)


def test_policy_allows_readonly_execution() -> None:
    decision = decide_execution_policy("readonly_execution")

    assert decision["decision"] == "allow"
    assert decision["reason"] == "readonly_execution_allowed"
    assert decision["approval_required"] is False
    assert decision["audit_required"] is False
    assert decision["classification"] == "readonly"
    assert decision["risk_level"] == "low"


def test_policy_marks_mutation_runtime_review_required() -> None:
    decision = decide_execution_policy("mutation_runtime")

    assert decision["decision"] == "review_required"
    assert decision["reason"] == "mutation_surface_requires_review"
    assert decision["approval_required"] is True
    assert decision["audit_required"] is True
    assert decision["classification"] == "mutation"
    assert decision["mutation_capable"] is True


def test_policy_marks_patch_apply_review_required() -> None:
    decision = decide_execution_policy("patch_apply")

    assert decision["decision"] == "review_required"
    assert decision["reason"] == "mutation_surface_requires_review"
    assert decision["approval_required"] is True
    assert decision["audit_required"] is True
    assert decision["classification"] == "patch"
    assert decision["mutation_capable"] is True


def test_policy_denies_unrestricted_shell() -> None:
    decision = decide_execution_policy("unrestricted_shell")

    assert decision["decision"] == "deny"
    assert decision["reason"] == "unrestricted_shell_denied"
    assert decision["approval_required"] is True
    assert decision["audit_required"] is True
    assert decision["classification"] == "shell"
    assert decision["risk_level"] == "critical"


def test_policy_denies_unknown_action() -> None:
    decision = decide_execution_policy("future_unknown_action")

    assert decision["decision"] == "deny"
    assert decision["reason"] == "unknown_action_denied"
    assert decision["approval_required"] is True
    assert decision["audit_required"] is True
    assert decision["classification"] == "unknown"
    assert decision["risk_level"] == "unknown"


def test_policy_decision_summary_contract() -> None:
    summary = build_policy_decision_summary()

    assert summary["policy_layer"] == "runtime_policy_decision"
    assert summary["allowed_actions"] == ["readonly_execution"]
    assert summary["review_required_actions"] == [
        "mutation_runtime",
        "patch_apply",
    ]
    assert summary["denied_actions"] == ["unrestricted_shell"]
    assert len(summary["decisions"]) == 4