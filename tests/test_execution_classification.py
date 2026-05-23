from __future__ import annotations

import pytest

from core.runtime.snapshot_loader.execution_classification import (
    build_execution_classification_summary,
    classify_execution_action,
)


def test_classify_readonly_execution() -> None:
    result = classify_execution_action("readonly_execution")

    assert result["classification"] == "readonly"
    assert result["risk_level"] == "low"
    assert result["mutation_capable"] is False
    assert result["replay_sensitive"] is False
    assert result["governance_critical"] is False


def test_classify_mutation_runtime() -> None:
    result = classify_execution_action("mutation_runtime")

    assert result["classification"] == "mutation"
    assert result["risk_level"] == "high"
    assert result["mutation_capable"] is True
    assert result["replay_sensitive"] is True
    assert result["governance_critical"] is True


def test_classify_patch_apply() -> None:
    result = classify_execution_action("patch_apply")

    assert result["classification"] == "patch"
    assert result["risk_level"] == "high"
    assert result["mutation_capable"] is True


def test_classify_unrestricted_shell() -> None:
    result = classify_execution_action("unrestricted_shell")

    assert result["classification"] == "shell"
    assert result["risk_level"] == "critical"
    assert result["mutation_capable"] is True
    assert result["governance_critical"] is True


def test_unknown_action_classification() -> None:
    result = classify_execution_action("future_unknown_action")

    assert result["classification"] == "unknown"
    assert result["risk_level"] == "unknown"
    assert result["mutation_capable"] is False
    assert result["replay_sensitive"] is True
    assert result["governance_critical"] is True


def test_classification_rejects_empty_action() -> None:
    with pytest.raises(ValueError):
        classify_execution_action("   ")


def test_execution_classification_summary_contract() -> None:
    summary = build_execution_classification_summary()

    assert summary["classification_layer"] == "runtime_execution_classification"

    known_actions = summary["known_actions"]

    assert "readonly_execution" in known_actions
    assert "mutation_runtime" in known_actions
    assert "patch_apply" in known_actions
    assert "unrestricted_shell" in known_actions

    assert len(summary["classifications"]) == 4