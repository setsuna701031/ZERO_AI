from core.adaptive.continuation_runtime import ContinuationRuntime


def test_continuation_runtime_records_work_item() -> None:
    runtime = ContinuationRuntime.start("goal_a", max_continuations=2)
    updated = runtime.record_work_item({"goal_id": "goal_a__continuation_1"})
    assert updated.current_goal_id == "goal_a__continuation_1"
    assert updated.continuation_count == 1
    assert not updated.limit_reached
    assert updated.to_dict()["execution_path"]["executes_tasks"] is False
