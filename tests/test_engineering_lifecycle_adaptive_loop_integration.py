from core.tasks.engineering_lifecycle_state_machine import EngineeringLifecycleStateMachine


def test_engineering_lifecycle_evaluates_cycle_after_adaptive_loop_contract():
    cycle = {
        "adaptive_loop_contract": {
            "loop_state": "progressing",
            "next_cycle_allowed": True,
            "terminal": False,
            "reason": "progress_detected",
        },
        "adaptive_replan_state": {
            "loop_action": "continue",
            "creates_continuation": True,
            "terminal": False,
            "reason": "continue_requested",
        },
    }
    result = EngineeringLifecycleStateMachine().evaluate_cycle(cycle, from_state="running").to_dict()
    assert result["accepted"] is True
    assert result["lifecycle_state"] == "continuing"
    assert result["execution_path"]["mutates_runtime"] is False
    assert result["execution_path"]["mutates_memory"] is False
