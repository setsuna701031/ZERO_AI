from core.tasks.adaptive_loop_coordinator import AdaptiveLoopCoordinator


def test_adaptive_loop_coordinator_attaches_passive_loop_records() -> None:
    coordinator = AdaptiveLoopCoordinator()
    cycle = {
        "goal_id": "g1",
        "cycle_index": 0,
        "ok": True,
        "runtime_state": "running",
        "engineering_runtime_contract": {
            "goal_id": "g1",
            "ok": True,
            "runtime_result": {"state": "running", "ok": True},
            "adaptive_decision": {"decision": "continue", "reason": "more_work"},
        },
        "adaptive_decision": "continue",
        "adaptive_decision_record": {
            "decision": "continue",
            "reason": "more_work",
            "progress": {"remaining_tasks": ["t2"], "completed_tasks": ["t1"]},
        },
    }

    result = coordinator.attach_cycle_controls(cycle, max_continuations=3)

    assert result["adaptive_replan_contract"]["loop_action"] == "continue"
    assert result["adaptive_replan_state"]["creates_continuation"] is True
    assert result["adaptive_observation"]["goal_id"] == "g1"
    assert result["adaptive_delta"]["reason"] == "initial_observation"
    assert result["adaptive_loop_contract"]["next_cycle_allowed"] is True
    assert result["adaptive_loop_coordinator"]["execution_path"]["persists_records"] is False
    assert "adaptive_replan_contract" not in cycle
