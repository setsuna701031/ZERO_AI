import pytest

from core.adaptive import AdaptivePlan


def test_adaptive_plan_contains_required_contract_fields() -> None:
    plan = AdaptivePlan("goal-1", "sub-1", "continue_active", "active")
    assert plan.to_dict() == {
        "selected_goal_id": "goal-1",
        "selected_subgoal_id": "sub-1",
        "decision_type": "continue_active",
        "reason": "active",
        "required_transition": None,
        "requires_user_review": False,
        "evidence_required": [],
    }


def test_adaptive_plan_rejects_unknown_decision() -> None:
    with pytest.raises(ValueError, match="adaptive_plan_requires_valid_decision_type"):
        AdaptivePlan("goal-1", None, "complete_goal", "unsafe")
