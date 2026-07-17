from core.tasks.goal_loop_coordinator import GoalLoopCoordinator


def test_goal_loop_coordinator_classifies_replan_and_continue() -> None:
    coordinator = GoalLoopCoordinator()

    replan = coordinator.classify_state({"creates_replan_record": True, "stop_reason": "replan"}).to_dict()
    assert replan["action"] == "create_replan_record"
    assert replan["terminal"] is True
    assert replan["stop_reason"] == "replan"

    cont = coordinator.classify_state({"creates_continuation": True}).to_dict()
    assert cont["action"] == "create_continuation"
    assert cont["terminal"] is False


def test_goal_loop_coordinator_classifies_terminal_refusal() -> None:
    coordinator = GoalLoopCoordinator()
    decision = coordinator.classify_state({
        "accepted": False,
        "loop_action": "stop",
        "stop_reason": "invalid_transition",
    }).to_dict()
    assert decision["action"] == "terminal"
    assert decision["terminal"] is True
    assert decision["refusal_reason"] == "invalid_transition"
