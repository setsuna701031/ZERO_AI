from core.adaptive.replan_coordinator import ReplanCoordinator
from core.adaptive.replan_runtime import ReplanRuntime


def test_replan_runtime_has_no_record_creation_authority() -> None:
    runtime = ReplanRuntime.start(max_replans=2)
    record = runtime.to_dict()
    assert not hasattr(runtime, "create_replan_record")
    assert not hasattr(runtime, "save_goal")
    assert record["execution_path"]["replan_runtime_bookkeeping_only"] is True
    assert record["execution_path"]["executes_tasks"] is False
    assert record["execution_path"]["persists_records"] is False
    assert record["execution_path"]["mutates_memory"] is False


def test_replan_coordinator_is_only_replan_record_creator(tmp_path) -> None:
    coordinator = ReplanCoordinator(repo_root=tmp_path)
    record, runtime = coordinator.create_replan_record(
        runtime=ReplanRuntime.start(max_replans=2),
        cycle={
            "goal_id": "goal_a",
            "cycle_index": 0,
            "replan_request": {"reason": "recoverable_runtime_failure", "evidence_chain": []},
        },
    )
    marker = record["replan_coordinator"]["execution_path"]
    assert record["replan_coordinator"]["created_replan_record"] is True
    assert marker["coordinator_only"] is True
    assert marker["executes_tasks"] is False
    assert marker["decides_adaptive_action"] is False
    assert marker["writes_evidence"] is False
    assert runtime.replan_count == 1
