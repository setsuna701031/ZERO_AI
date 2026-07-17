from core.adaptive import AdaptivePlanner, AdaptivePolicy


def test_adaptive_policy_defaults_are_enabled() -> None:
    policy = AdaptivePolicy()
    assert policy.require_evidence_for_completion is True
    assert policy.require_all_subgoals_completed is True
    assert policy.require_review_for_resume is True
    assert policy.prevent_runtime_bypass is True


def test_policy_toggle_changes_completion_evidence_behavior() -> None:
    goal = {"goal_id": "goal-1", "status": "completed"}
    subgoals = [{"subgoal_id": "sub-1", "status": "completed"}]
    strict = AdaptivePlanner().decide(current_goal=goal, subgoals=subgoals)
    relaxed = AdaptivePlanner(policy=AdaptivePolicy(require_evidence_for_completion=False)).decide(
        current_goal=goal,
        subgoals=subgoals,
    )
    assert strict.decision_type == "request_evidence"
    assert relaxed.decision_type == "no_action"


def test_prevent_runtime_bypass_toggle_changes_resumable_behavior() -> None:
    goal = {"goal_id": "goal-1", "status": "active"}
    subgoals = [{"subgoal_id": "sub-1", "status": "resumable"}]
    strict = AdaptivePlanner().decide(current_goal=goal, subgoals=subgoals)
    relaxed = AdaptivePlanner(policy=AdaptivePolicy(prevent_runtime_bypass=False)).decide(
        current_goal=goal,
        subgoals=subgoals,
    )
    assert strict.decision_type == "wait_for_user"
    assert relaxed.decision_type == "resume_blocked"
