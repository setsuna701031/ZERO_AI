from core.adaptive.replan_coordinator import ReplanCoordinator
from core.adaptive.replan_runtime import ReplanRuntime


def test_replan_coordinator_creates_record_and_updates_runtime(tmp_path) -> None:
    coordinator = ReplanCoordinator(repo_root=tmp_path)
    runtime = ReplanRuntime.start(max_replans=2)
    cycle = {
        "goal_id": "goal_a",
        "cycle_index": 0,
        "replan_request": {
            "reason": "recoverable_runtime_failure",
            "root_cause_report": {"primary_cause": "missing_output"},
            "evidence_chain": [{"evidence_id": "e1"}],
        },
    }
    record, updated = coordinator.create_replan_record(runtime=runtime, cycle=cycle)
    assert record["goal_id"] == "goal_a"
    assert record["reason"] == "recoverable_runtime_failure"
    assert updated.replan_count == 1
    assert record["replan_coordinator"]["execution_path"]["executes_tasks"] is False
