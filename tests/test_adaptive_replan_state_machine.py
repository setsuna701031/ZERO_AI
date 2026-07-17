from core.adaptive.adaptive_replan_state_machine import AdaptiveReplanStateMachine


def test_state_machine_maps_continue_contract_to_continuation_intent() -> None:
    result = AdaptiveReplanStateMachine().evaluate_contract({
        "loop_action": "continue",
        "creates_continuation": True,
        "reason": "next_work_available",
    })
    data = result.to_dict()
    assert data["accepted"] is True
    assert data["loop_action"] == "continue"
    assert data["terminal"] is False
    assert data["creates_continuation"] is True


def test_state_machine_maps_replan_contract_to_replan_intent() -> None:
    data = AdaptiveReplanStateMachine().evaluate_contract({
        "loop_action": "replan",
        "creates_replan_record": True,
        "stop_reason": "replan",
    }).to_dict()
    assert data["accepted"] is True
    assert data["loop_action"] == "replan"
    assert data["creates_replan_record"] is True
    assert data["terminal"] is False


def test_state_machine_rejects_illegal_transition() -> None:
    data = AdaptiveReplanStateMachine().evaluate_contract({"loop_action": "continue"}, from_state="complete").to_dict()
    assert data["accepted"] is False
    assert data["loop_action"] == "stop"
    assert data["terminal"] is True
