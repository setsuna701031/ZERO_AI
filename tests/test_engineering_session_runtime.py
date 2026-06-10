from core.session.engineering_session_runtime import EngineeringSessionRuntime


def test_session_runtime_start_normalizes_limits() -> None:
    runtime = EngineeringSessionRuntime.start("goal-a", max_cycles=0, max_replans=-1, max_continuations=None)

    assert runtime.target_goal_id == "goal-a"
    assert runtime.current_goal_id == "goal-a"
    assert runtime.cycle_limit == 1
    assert runtime.max_replans == 0
    assert runtime.max_continuations == 1
    assert runtime.to_dict()["execution_path"]["mutates_memory"] is False


def test_session_runtime_append_cycle_is_immutable() -> None:
    runtime = EngineeringSessionRuntime.start("goal-a", max_cycles=2)
    updated = runtime.append_cycle({"cycle_index": 0, "goal_id": "goal-a"})

    assert runtime.cycles == []
    assert len(updated.cycles) == 1
    assert updated.cycles[0]["goal_id"] == "goal-a"
