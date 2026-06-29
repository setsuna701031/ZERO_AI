from core.adaptive.adaptive_loop_contract import build_adaptive_loop_contract
from core.adaptive.adaptive_loop_state import classify_adaptive_loop_state
import pytest

pytestmark = [pytest.mark.contract]




def test_loop_contract_marks_continuation_as_next_cycle_allowed() -> None:
    cycle = {
        "goal_id": "goal-1",
        "cycle_index": 0,
        "adaptive_observation": {"goal_id": "goal-1", "cycle_index": 0},
        "adaptive_delta": {"previous_cycle_index": None, "reason": "initial_observation"},
        "adaptive_replan_state": {"loop_action": "continue", "terminal": False, "creates_continuation": True},
    }
    data = build_adaptive_loop_contract(cycle)
    assert data["loop_state"] == "initial"
    assert data["next_cycle_allowed"] is True
    assert data["execution_path"]["executes_tasks"] is False


def test_loop_state_classifies_terminal() -> None:
    assert classify_adaptive_loop_state(delta={}, replan_state={"terminal": True}) == "terminal"


def test_loop_state_classifies_stalled() -> None:
    assert classify_adaptive_loop_state(delta={"previous_cycle_index": 0, "stalled": True}, replan_state={}) == "stalled"
