from __future__ import annotations

from core.runtime.runtime_decision_advisor import RuntimeDecisionAdvisor


def test_successes_and_denials_become_read_only_advice() -> None:
    result = RuntimeDecisionAdvisor().advise("create example", {
        "completed_experiences": [{"record": {"status": "completed"}}],
        "successful_paths": ["workspace/a.txt", "workspace/a.txt", "workspace/b.txt"],
        "prior_denial_reasons": [
            "safe_no_mutation_adapter_unavailable",
            "safe_no_mutation_adapter_incomplete",
            "validation_failed",
            "unsafe_path",
            "rollback_required",
        ],
    })

    assert result["schema"] == "zero.runtime.decision_advisor.v1"
    assert result["ok"] is True
    assert result["previous_success_available"] is True
    assert result["recommended_paths"] == ["workspace/a.txt", "workspace/b.txt"]
    assert set(result["risk_flags"]) == {
        "mutation_adapter_unavailable_risk",
        "mutation_adapter_incomplete_risk",
        "validation_failure_risk",
        "unsafe_path_risk",
        "rollback_risk",
    }
    assert result["read_only"] is True
    assert result["decision_authority"] is False
    assert result["requested_changes_modified"] is False
    assert all(hint["advisory_only"] is True for hint in result["planner_hints"])


def test_empty_memory_is_safe_and_deterministic() -> None:
    advisor = RuntimeDecisionAdvisor()
    first = advisor.advise("new task", {})
    second = advisor.advise("new task", {})

    assert first == second
    assert first["advisor_status"] == "no_advice"
    assert first["previous_success_available"] is False
    assert first["recommended_paths"] == []
    assert first["risk_flags"] == []
    assert first["planner_hints"] == []
