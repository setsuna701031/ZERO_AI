import pytest

from core.goals import GoalTransition


def test_transition_normalizes_contract_fields() -> None:
    transition = GoalTransition("goal", " goal-1 ", "created", "planned", "plan")
    assert transition.target_id == "goal-1"
    assert transition.to_state == "planned"


def test_transition_rejects_cross_target_state() -> None:
    with pytest.raises(ValueError, match="subgoal_transition_requires_valid_state"):
        GoalTransition("subgoal", "sub-1", "planned", "active", "start")
