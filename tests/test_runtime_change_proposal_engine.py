from __future__ import annotations

import copy

import pytest

from core.runtime.runtime_change_proposal_engine import (
    RuntimeChangeProposalEngine,
)


def _propose(
    repair: dict,
    *,
    runner: dict | None = None,
    observation: dict | None = None,
    memory: dict | None = None,
    planner: dict | None = None,
) -> dict:
    return RuntimeChangeProposalEngine().propose(
        goal="keep goal",
        task_id="task-1",
        runner_result=runner or {},
        workspace_observation=observation or {},
        repair_advice=repair,
        memory_context=memory or {},
        planner_advisor_bridge=planner or {},
    )


def _repair(category: str, status: str = "repair_advised") -> dict:
    return {
        "repair_needed": category != "none",
        "advisor_status": "repair_not_needed" if category == "none" else status,
        "failure_category": category,
        "repairability": "likely_repairable",
        "failure_reasons": [f"reason:{category}"],
        "risk_flags": [],
    }


def test_success_does_not_create_proposal_and_safety_fields_are_fixed() -> None:
    result = _propose(_repair("none"), runner={"ok": True})

    assert result["schema"] == "zero.runtime.change_proposal_engine.v1"
    assert result["proposal_status"] == "proposal_not_needed"
    assert result["proposal"]["target_files"] == []
    assert result["approval_status"] == "not_required"
    assert result["read_only"] is True
    assert result["mutation_allowed"] is False
    assert result["patch_generation_allowed"] is False
    assert result["repair_execution_allowed"] is False
    assert result["decision_authority"] is False
    assert result["requested_changes_modified"] is False
    assert result["autonomous_apply_allowed"] is False
    assert result["requires_operator_approval"] is True


@pytest.mark.parametrize(("category", "expected_status", "risk"), [
    ("validation_failure", "proposal_created", "low"),
    ("mutation_failure", "proposal_created", "medium"),
    ("adapter_unavailable", "proposal_blocked_by_safety", "blocked"),
    ("path_safety_failure", "proposal_blocked_by_safety", "blocked"),
    ("rollback_failure", "manual_review_required", "high"),
])
def test_category_proposal_and_risk(
    category: str, expected_status: str, risk: str
) -> None:
    status = "manual_review_required" if category == "rollback_failure" else "repair_advised"
    result = _propose(
        _repair(category, status),
        runner={"ok": False, "changed_files": ["workspace/a.txt"]},
    )
    assert result["proposal_status"] == expected_status
    assert result["proposal"]["risk_level"] == risk
    assert result["approval_status"] == "pending"


def test_insufficient_observation_and_no_targets_is_insufficient() -> None:
    repair = _repair("observation_failure", "insufficient_evidence")
    result = _propose(repair)
    assert result["proposal_status"] == "insufficient_evidence"


def test_target_files_are_safe_deduplicated_and_memory_does_not_expand() -> None:
    result = _propose(
        _repair("validation_failure"),
        runner={"ok": False, "changed_files": [
            "workspace/a.txt", "workspace/a.txt", "../escape.txt", "C:\\absolute.txt"
        ]},
        observation={"file_observations": [
            {"path": "workspace/b.txt", "exists": True},
            {"path": "workspace/missing.txt", "exists": False},
        ]},
        memory={"successful_paths": ["workspace/a.txt", "workspace/history.txt"]},
        planner={"preferred_paths": ["workspace/b.txt", "../planner-escape.txt"]},
    )

    assert result["proposal"]["target_files"] == [
        "workspace/a.txt", "workspace/b.txt"
    ]
    assert "workspace/history.txt" not in result["proposal"]["target_files"]


def test_evidence_references_only_keep_safe_metadata() -> None:
    result = _propose(
        _repair("validation_failure"),
        observation={"evidence_observations": [{
            "evidence_type": "result_path", "path": "evidence/result.json",
            "exists": True, "readable": True, "content_hash_sha256": "abc",
            "parsed_json": {"secret": "not copied"},
        }]},
    )
    reference = result["proposal"]["evidence_references"][0]
    assert reference == {
        "evidence_type": "result_path", "path": "evidence/result.json",
        "exists": True, "readable": True, "content_hash_sha256": "abc",
    }


def test_actions_are_high_level_and_require_validation_and_rollback() -> None:
    result = _propose(
        _repair("validation_failure"),
        runner={"changed_files": ["a.txt"]},
    )
    actions = result["proposal"]["recommended_actions"]
    forbidden = ("patch", "diff", "shell", "python", "create_file", "update_file")
    assert all(not any(term in action for term in forbidden) for action in actions)
    assert "run_focused_validation" in result["proposal"]["validation_requirements"]
    assert {"rollback_plan_required": True} in result["proposal"]["rollback_requirements"]
    assert "snapshot_target_files_before_change" in result["proposal"]["rollback_requirements"]


def test_proposal_id_is_deterministic_and_inputs_are_not_modified() -> None:
    runner = {
        "ok": False, "changed_files": ["a.txt"],
        "requested_changes": [{"change_id": "one"}],
        "raw_secret": {"content": "large"},
    }
    observation = {"file_observations": [], "issues": []}
    repair = _repair("validation_failure")
    before = copy.deepcopy((runner, observation, repair))
    first = _propose(repair, runner=runner, observation=observation)
    second = _propose(repair, runner=runner, observation=observation)

    assert first["proposal_id"] == second["proposal_id"]
    assert (runner, observation, repair) == before
    assert "raw_secret" not in first["source_summary"]
    assert "requested_changes" not in first["source_summary"]
