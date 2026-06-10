from __future__ import annotations

from core.tasks.adaptive_replan_contract import build_adaptive_replan_contract


def _cycle(decision: str) -> dict[str, object]:
    return {
        "goal_id": "goal_a",
        "adaptive_decision": decision,
        "adaptive_decision_record": {"decision": decision, "reason": f"reason_{decision}"},
    }


def test_complete_contract_is_terminal() -> None:
    contract = build_adaptive_replan_contract(cycle=_cycle("complete"))
    assert contract.loop_action == "complete"
    assert contract.terminal is True
    assert contract.stop_reason == "complete"


def test_blocked_contract_is_terminal() -> None:
    contract = build_adaptive_replan_contract(cycle=_cycle("blocked"))
    assert contract.loop_action == "blocked"
    assert contract.terminal is True
    assert contract.stop_reason == "blocked"


def test_replan_contract_creates_replan_record_when_limit_available() -> None:
    contract = build_adaptive_replan_contract(cycle=_cycle("replan"), replan_count=0, max_replans=1)
    assert contract.loop_action == "replan"
    assert contract.creates_replan_record is True
    assert contract.requires_replan is True


def test_replan_contract_refuses_when_limit_exhausted() -> None:
    contract = build_adaptive_replan_contract(cycle=_cycle("replan"), replan_count=1, max_replans=1)
    assert contract.loop_action == "refuse"
    assert contract.refusal_reason == "max_replans_exhausted"
    assert contract.terminal is True


def test_continue_contract_creates_continuation_when_limit_available() -> None:
    contract = build_adaptive_replan_contract(cycle=_cycle("continue"), continuation_count=0, max_continuations=1)
    assert contract.loop_action == "continue"
    assert contract.creates_continuation is True
    assert contract.terminal is False


def test_continue_contract_refuses_when_limit_exhausted() -> None:
    contract = build_adaptive_replan_contract(cycle=_cycle("continue"), continuation_count=1, max_continuations=1)
    assert contract.loop_action == "refuse"
    assert contract.refusal_reason == "max_continuations_exhausted"
    assert contract.terminal is True


def test_unknown_decision_becomes_non_continuable_stop() -> None:
    contract = build_adaptive_replan_contract(cycle=_cycle("unexpected"))
    assert contract.loop_action == "stop"
    assert contract.stop_reason == "non_continuable_adaptive_decision"
