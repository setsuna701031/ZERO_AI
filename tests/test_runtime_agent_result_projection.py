from __future__ import annotations

import pytest

from core.agent.runtime_agent_controller import project_mission_result


@pytest.mark.parametrize(("payload", "expected"), [
    ({"mission_status": "completed"}, "completed"),
    ({"session_status": "completed"}, "completed"),
    ({"execution_status": "completed"}, "completed"),
    ({"status": "already_completed"}, "completed"),
    ({"mission_status": "waiting_for_plan_confirmation"}, "waiting_for_approval"),
    ({"session_status": "waiting_for_operator"}, "waiting_for_approval"),
    ({"plan_status": "waiting_for_operator_approval"}, "waiting_for_approval"),
    ({"approval_required": True, "approval_status": "pending"}, "waiting_for_approval"),
    ({"mission_status": "running"}, "running"),
    ({"mission_status": "blocked"}, "blocked"),
    ({"approval_status": "denied"}, "blocked"),
    ({"mission_status": "failed"}, "failed"),
    ({"validation_status": "validation_failed"}, "failed"),
    ({"rollback_status": "rollback_failed"}, "failed"),
    ({"mission_status": "cancelled"}, "cancelled"),
    ({"status": "something-new"}, "failed"),
])
def test_explicit_mission_result_projection(payload, expected):
    assert project_mission_result(payload)["entry_status"] == expected


def test_negative_evidence_wins_over_completed_marker():
    projected = project_mission_result({"mission_status": "completed", "failure": {"reasons": ["transaction failed"]}})
    assert projected["entry_status"] == "failed"


def test_safety_and_identity_failures_block_instead_of_complete():
    assert project_mission_result({"status": "completed", "reasons": ["unsafe path"]})["entry_status"] == "blocked"
    projected = project_mission_result({"mission_id": "other", "status": "completed"}, expected_mission_id="expected")
    assert projected == {"entry_status": "blocked", "reason": "agent_mission_identity_mismatch"}


def test_coherent_completed_mission_and_session_projects_completed():
    projected = project_mission_result(
        {"execution_status": "completed", "mission_id": "m", "session_id": "s"},
        mission={"mission_id": "m", "mission_status": "completed", "failure": None},
        session={"session_id": "s", "session_status": "completed", "failure": None},
        expected_mission_id="m", expected_session_id="s",
    )
    assert projected["entry_status"] == "completed"

