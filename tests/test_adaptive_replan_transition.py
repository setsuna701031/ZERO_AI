from core.adaptive.adaptive_replan_transition import AdaptiveReplanTransition


def test_transition_from_contract_normalizes_loop_action() -> None:
    transition = AdaptiveReplanTransition.from_contract({"loop_action": "request_replan", "reason": "repair"})
    assert transition.from_state == "continue"
    assert transition.to_state == "replan"
    assert transition.action == "replan"
    assert transition.reason == "repair"
    assert transition.to_dict()["execution_path"]["executes_tasks"] is False
