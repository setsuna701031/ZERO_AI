from core.adaptive.adaptive_replan_state_machine import AdaptiveReplanStateMachine
from core.tasks.adaptive_replan_contract import build_adaptive_replan_contract


def _cycle(decision: str) -> dict:
    return {
        "adaptive_decision": decision,
        "adaptive_decision_record": {"decision": decision, "reason": f"{decision}_reason"},
    }


def test_loop_facing_contract_goes_through_state_machine_for_continue() -> None:
    contract = build_adaptive_replan_contract(cycle=_cycle("continue"), continuation_count=0, max_continuations=2)
    result = AdaptiveReplanStateMachine().evaluate_contract(contract.to_dict()).to_dict()
    assert result["accepted"] is True
    assert result["creates_continuation"] is True
    assert result["loop_action"] == "continue"


def test_loop_facing_contract_goes_through_state_machine_for_replan() -> None:
    contract = build_adaptive_replan_contract(cycle=_cycle("replan"), replan_count=0, max_replans=1)
    result = AdaptiveReplanStateMachine().evaluate_contract(contract.to_dict()).to_dict()
    assert result["accepted"] is True
    assert result["creates_replan_record"] is True
    assert result["loop_action"] == "replan"


def test_loop_facing_contract_goes_through_state_machine_for_refusal() -> None:
    contract = build_adaptive_replan_contract(cycle=_cycle("continue"), continuation_count=2, max_continuations=2)
    result = AdaptiveReplanStateMachine().evaluate_contract(contract.to_dict()).to_dict()
    assert result["accepted"] is True
    assert result["loop_action"] == "refuse"
    assert result["terminal"] is True
    assert result["refusal_reason"] == "max_continuations_exhausted"
