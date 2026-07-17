from core.adaptive import AdaptivePlanner, AdaptivePolicy
from core.evidence import EvidenceRecord, EvidenceValidator
from core.tasks.engineering_adaptive_planner import EngineeringAdaptivePlanner


def test_active_subgoal_can_continue() -> None:
    plan = AdaptivePlanner().decide(
        current_goal={"goal_id": "goal-1", "status": "active"},
        subgoals=[{"subgoal_id": "sub-1", "status": "active"}],
    )
    assert plan.decision_type == "continue_active"


def test_completed_goal_without_evidence_requests_evidence() -> None:
    plan = AdaptivePlanner().decide(
        current_goal={"goal_id": "goal-1", "status": "completed"},
        subgoals=[{"subgoal_id": "sub-1", "status": "completed"}],
    )
    assert plan.decision_type == "request_evidence"


def test_goal_with_active_subgoal_cannot_be_treated_as_completed() -> None:
    evidence = EvidenceValidator().validate(
        EvidenceRecord("e-1", "goal-1", None, "scanner", "complete", "2026-06-09T00:00:00Z")
    )
    plan = AdaptivePlanner().decide(
        current_goal={"goal_id": "goal-1", "status": "completed"},
        subgoals=[{"subgoal_id": "sub-1", "status": "active"}],
        evidence_summary=[evidence],
    )
    assert plan.decision_type == "no_action"
    assert plan.requires_user_review is True


def test_resumable_never_continues_active() -> None:
    plan = AdaptivePlanner().decide(
        current_goal={"goal_id": "goal-1", "status": "active"},
        subgoals=[{"subgoal_id": "sub-1", "status": "resumable"}],
    )
    assert plan.decision_type == "wait_for_user"


def test_resume_requires_review_by_default_and_policy_can_disable_it() -> None:
    subgoal = {"subgoal_id": "sub-1", "status": "blocked", "resume_point": {"task_id": "task-1"}}
    strict = AdaptivePlanner().decide(current_goal={"goal_id": "goal-1", "status": "active"}, subgoals=[subgoal])
    relaxed = AdaptivePlanner(policy=AdaptivePolicy(require_review_for_resume=False)).decide(
        current_goal={"goal_id": "goal-1", "status": "active"},
        subgoals=[subgoal],
    )
    assert strict.decision_type == "resume_blocked"
    assert strict.requires_user_review is True
    assert relaxed.requires_user_review is False


def test_active_blocker_produces_valid_mark_blocked_plan() -> None:
    plan = AdaptivePlanner().decide(
        current_goal={"goal_id": "goal-1", "status": "active"},
        subgoals=[{"subgoal_id": "sub-1", "status": "active"}],
        blocker_summary={"reason": "external dependency"},
    )
    assert plan.decision_type == "mark_blocked"
    assert plan.required_transition["to_state"] == "blocked"


def test_engineering_adaptive_mainline_marks_completed_goal_with_next_target_as_continuation() -> None:
    runtime_result = {
        "ok": True,
        "state": "complete",
        "next_runtime_request": {
            "goal_id": "goal-1",
            "payload": {
                "goal": "建立 workspace/example_next.txt",
                "target_path": "workspace/example_next.txt",
                "task_type": "engineering_task",
            },
            "source_runtime_state": "complete",
        },
        "iterations": [
            {
                "continuation_result": {
                    "goal_lifecycle": {
                        "goal_id": "goal-1",
                        "goal_state": "completed",
                        "completed_tasks": ["workspace/example.txt"],
                        "remaining_tasks": [],
                        "failed_tasks": [],
                        "blocked_tasks": [],
                    }
                }
            }
        ],
    }

    decision = EngineeringAdaptivePlanner().decide_next_action(
        goal={"goal_id": "goal-1", "summary": "建立 workspace/example.txt"},
        runtime_result=runtime_result,
    )

    assert decision["decision"] == "complete"
    assert decision["mainline_decision"] == "create_continuation"
    assert decision["next_action"] == "create_continuation_work_item"
    assert decision["continuation_plan"]["next_runtime_request"]["payload"]["target_path"] == "workspace/example_next.txt"


def test_engineering_adaptive_mainline_replans_missing_artifact() -> None:
    runtime_result = {
        "ok": False,
        "state": "replan",
        "stop_reason": "missing_artifact",
        "iterations": [
            {
                "continuation_result": {
                    "goal_lifecycle": {
                        "goal_id": "goal-1",
                        "goal_state": "failed",
                        "completed_tasks": [],
                        "remaining_tasks": ["workspace/example.txt"],
                        "failed_tasks": ["missing_artifact:workspace/example.txt"],
                        "blocked_tasks": [],
                    }
                }
            }
        ],
    }

    decision = EngineeringAdaptivePlanner().decide_next_action(
        goal={"goal_id": "goal-1", "summary": "建立 workspace/example.txt"},
        runtime_result=runtime_result,
        runtime_root_cause={"stop_reason": "missing_artifact"},
    )

    assert decision["decision"] == "replan"
    assert decision["replan_request"]["reason"] == "missing_artifact"
    assert decision["replan_request"]["replan_reason"] == "missing_artifact"
    assert decision["replan_request"]["source_goal_id"] == "goal-1"
    assert decision["replan_request"]["failed_step"]["reason"] == "missing_artifact"
    assert "workspace/example.txt" in decision["replan_request"]["missing_artifacts"]
    assert decision["replan_request"]["next_runtime_request"]["payload"]["target_path"] == "workspace/example.txt"
