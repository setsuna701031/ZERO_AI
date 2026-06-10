from core.tasks.engineering_lifecycle_state_machine import EngineeringLifecycleStateMachine


def _loop(action, **extra):
    replan = {"loop_action": action, **extra}
    return {
        "loop_state": "terminal" if action in {"complete", "blocked", "refuse", "stop"} else "progressing",
        "adaptive_replan_state": replan,
        "terminal": action in {"complete", "blocked", "refuse", "stop"},
        "next_cycle_allowed": action == "continue",
        "reason": f"{action}_reason",
    }


def test_engineering_lifecycle_maps_completion_to_completed():
    result = EngineeringLifecycleStateMachine().evaluate_adaptive_loop(_loop("complete"), from_state="running")
    assert result.accepted is True
    assert result.lifecycle_state == "completed"
    assert result.terminal is True


def test_engineering_lifecycle_maps_replan_to_replanning():
    result = EngineeringLifecycleStateMachine().evaluate_adaptive_loop(
        _loop("replan", creates_replan_record=True),
        from_state="running",
    )
    assert result.accepted is True
    assert result.lifecycle_state == "replanning"
    assert result.terminal is False


def test_engineering_lifecycle_maps_continue_to_continuing():
    result = EngineeringLifecycleStateMachine().evaluate_adaptive_loop(
        _loop("continue", creates_continuation=True),
        from_state="running",
    )
    assert result.accepted is True
    assert result.lifecycle_state == "continuing"
