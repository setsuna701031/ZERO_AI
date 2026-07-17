from core.adaptive.replan_runtime import ReplanRuntime


def test_replan_runtime_records_replan() -> None:
    runtime = ReplanRuntime.start(max_replans=1)
    updated = runtime.record_replan({"goal_id": "goal_a"})
    assert updated.replan_count == 1
    assert updated.limit_reached
    assert updated.to_dict()["execution_path"]["mutates_memory"] is False
