from copy import deepcopy

import pytest

from core.runtime.runtime_end_to_end_orchestrator import build_runtime_session_final_evidence
from core.runtime.runtime_mission_execution_approval_flow import execute_approved_mission, review_mission_execution_plan
from core.runtime.runtime_mission_orchestrator import _project_goal
from core.runtime.runtime_natural_language_mission_bootstrap import run_natural_language_mission
from core.runtime.runtime_operator_session import fingerprint, load_runtime_session


NOW = "2026-07-13T00:00:00+00:00"


def completed_session(*, mode="transactional_active_execution", validation="passed", rollback="not_required"):
    tx = {"transaction_status": "committed", "transaction_mode": mode, "validation_status": validation, "rollback_status": rollback, "committed_paths": ["hello.txt"]}
    session = {"session_id": "session-1", "session_status": "completed", "task_id": "task-1", "natural_task": {}, "identity_chain": {}, "operator_actions": [], "checkpoints": [], "phase_history": [], "artifacts": {"transaction_result": tx}}
    session["artifacts"]["final_evidence"] = build_runtime_session_final_evidence(session)
    return session


@pytest.mark.parametrize("mode", ["transactional_active_execution", "controlled_read_only"])
def test_project_goal_accepts_only_evidenced_committed_completion(mode):
    goal = {"goal_status": "running", "started_at": NOW}
    _project_goal(goal, completed_session(mode=mode), NOW)
    assert goal["goal_status"] == "completed"
    assert goal["result_summary"]["transaction_status"] == "committed"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"transaction_status": "rolled_back"}, "transaction_rolled_back"),
        ({"validation_status": "failed"}, "validation_failed"),
        ({"rollback_status": "failed"}, "rollback_failed"),
    ],
)
def test_project_goal_rejects_failed_transaction_validation_or_rollback(change, reason):
    session = completed_session()
    session["artifacts"]["transaction_result"].update(change)
    session["artifacts"]["final_evidence"] = build_runtime_session_final_evidence(session)
    goal = {"goal_status": "running", "started_at": NOW}
    _project_goal(goal, session, NOW)
    assert goal["goal_status"] == "failed"
    assert reason in goal["failure"]["reasons"]


def test_project_goal_rejects_tampered_completion_evidence():
    session = completed_session()
    session["artifacts"]["final_evidence"]["outcome"] = "forged"
    goal = {"goal_status": "running", "started_at": NOW}
    _project_goal(goal, session, NOW)
    assert goal["goal_status"] == "failed"
    assert goal["failure"]["reasons"] == ["completion_evidence_invalid"]


def test_project_goal_rejects_missing_completion_evidence():
    session = completed_session()
    session["artifacts"].pop("final_evidence")
    goal = {"goal_status": "running", "started_at": NOW}
    _project_goal(goal, session, NOW)
    assert goal["goal_status"] == "failed"
    assert goal["failure"]["reasons"] == ["completion_evidence_invalid"]


def test_committed_goal_session_is_persisted_to_canonical_session_path(tmp_path):
    artifact = run_natural_language_mission("create hello.txt with content hello zero", workspace_root=tmp_path, now=NOW)
    review_mission_execution_plan(artifact["artifact_path"], decision="approve", operator_id="operator", now=NOW)
    result = execute_approved_mission(artifact["artifact_path"], operator_id="operator", now=NOW)
    session_path = result["completed_sessions"][0]["goal_id"]
    from core.runtime.runtime_mission_model import load_mission
    mission = load_mission(artifact["mission_reference"]["path"], check_expiry=False)
    reloaded = load_runtime_session(mission["goals"][session_path]["session_path"], now=NOW)
    assert reloaded["session_status"] == "completed"
    assert reloaded["artifacts"]["transaction_result"]["transaction_status"] == "committed"
    evidence = reloaded["artifacts"]["final_evidence"]
    unsigned = deepcopy(evidence); claimed = unsigned.pop("final_evidence_fingerprint")
    assert claimed == fingerprint(unsigned)
