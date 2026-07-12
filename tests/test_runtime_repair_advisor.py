from __future__ import annotations

import copy

import pytest

from core.runtime.runtime_repair_advisor import RuntimeRepairAdvisor


def _advise(runner: dict, observation: dict | None = None, **kwargs: object) -> dict:
    return RuntimeRepairAdvisor().advise(
        goal="keep goal",
        task_id="task-1",
        runner_result=runner,
        workspace_observation=observation or {
            "observer_status": "observed",
            "observation_complete": True,
            "issues": [],
            "evidence_observations": [],
        },
        **kwargs,
    )


def test_success_needs_no_repair_and_has_fixed_safety_fields() -> None:
    result = _advise({"ok": True, "validation_passed": True})

    assert result["schema"] == "zero.runtime.repair_advisor.v1"
    assert result["advisor_status"] == "repair_not_needed"
    assert result["repair_needed"] is False
    assert result["repairability"] == "not_applicable"
    assert result["failure_category"] == "none"
    assert result["recommended_next_action"] == "none"
    assert result["confidence"] == 1.0
    assert result["read_only"] is True
    assert result["repair_execution_allowed"] is False
    assert result["mutation_allowed"] is False
    assert result["decision_authority"] is False
    assert result["requested_changes_modified"] is False
    assert result["autonomous_retry_allowed"] is False
    assert result["patch_generation_allowed"] is False


@pytest.mark.parametrize(
    ("runner", "observation", "category", "repairability"),
    [
        ({"ok": False, "validation_passed": False}, None, "validation_failure", "likely_repairable"),
        ({"ok": False, "mutation_completed": False}, None, "mutation_failure", "likely_repairable"),
        ({"ok": False, "denial_reason": "unsafe_path outside workspace"}, None, "path_safety_failure", "blocked_by_safety_boundary"),
        ({"ok": False, "denial_reason": "mutation adapter unavailable"}, None, "adapter_unavailable", "blocked_by_safety_boundary"),
        ({"ok": False, "denial_reason": "mutation adapter incomplete"}, None, "adapter_incomplete", "manual_only"),
        ({"ok": False, "rollback_required": True, "rollback_completed": False}, None, "rollback_failure", "manual_only"),
        ({"ok": False}, {"observer_status": "observer_error", "observation_complete": False}, "observation_failure", "insufficient_evidence"),
        ({"ok": False}, {"observer_status": "observed", "observation_complete": True, "evidence_observations": [{"parse_error": "JSONDecodeError"}]}, "evidence_parse_failure", "manual_only"),
        ({"ok": False, "error_type": "RuntimeError"}, None, "runner_exception", "likely_repairable"),
        ({"ok": False, "denial_reason": "other"}, None, "unknown_failure", "insufficient_evidence"),
    ],
)
def test_failure_classification(
    runner: dict, observation: dict | None, category: str, repairability: str
) -> None:
    result = _advise(runner, observation)
    assert result["failure_category"] == category
    assert result["repairability"] == repairability
    assert result["repair_needed"] is True


def test_memory_and_planner_only_add_safe_risk_and_hint() -> None:
    result = _advise(
        {"ok": False, "validation_passed": False},
        memory_context={
            "experience_count": 2,
            "prior_denial_reasons": ["validation_failed"],
            "successful_paths": ["do-not-adopt.txt"],
        },
        planner_advisor_bridge={"avoid_risk_flags": ["rollback_risk"]},
    )

    assert result["risk_flags"] == [
        "rollback_risk", "prior_denial_risk:validation_failed"
    ]
    assert "review_prior_denials" in result["repair_hints"]
    assert result["source_summary"]["memory_experience_count"] == 2
    assert "successful_paths" not in result["source_summary"]


def test_inputs_are_unchanged_and_summary_does_not_copy_raw_payload() -> None:
    runner = {
        "ok": False,
        "validation_passed": False,
        "changed_files": ["a.txt"],
        "secret_raw_payload": {"large": [1, 2, 3]},
        "requested_changes": [{"change_id": "one"}],
    }
    observation = {
        "observer_status": "observed", "observation_complete": True,
        "issues": [], "raw_file_content": "secret",
    }
    before = copy.deepcopy((runner, observation))
    result = _advise(runner, observation)

    assert (runner, observation) == before
    assert "secret_raw_payload" not in result["source_summary"]
    assert "raw_file_content" not in result["source_summary"]
    assert result["source_summary"]["changed_files_count"] == 1
    forbidden = ("patch", "diff", "execute_mutation", "file_content")
    assert all(
        not any(term in hint for term in forbidden)
        for hint in result["repair_hints"]
    )


def test_success_without_observation_is_insufficient_evidence() -> None:
    result = _advise({"ok": True}, {})
    assert result["advisor_status"] == "insufficient_evidence"
    assert result["repair_needed"] is False
