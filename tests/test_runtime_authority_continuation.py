from core.adaptive.continuation_coordinator import ContinuationCoordinator
from core.adaptive.continuation_runtime import ContinuationRuntime


class FakeRepository:
    def __init__(self) -> None:
        self.records = {}

    def load_goal(self, goal_id):
        return self.records.get(goal_id)

    def save_goal(self, record):
        self.records[record["goal_id"]] = dict(record)
        return self.records[record["goal_id"]]


def test_continuation_runtime_has_no_repository_authority() -> None:
    runtime = ContinuationRuntime.start("goal_a", max_continuations=2)
    record = runtime.to_dict()
    assert not hasattr(runtime, "save_goal")
    assert not hasattr(runtime, "update_goal")
    assert record["execution_path"]["continuation_runtime_bookkeeping_only"] is True
    assert record["execution_path"]["executes_tasks"] is False
    assert record["execution_path"]["persists_records"] is False
    assert record["execution_path"]["mutates_memory"] is False


def test_continuation_coordinator_is_only_continuation_writer(tmp_path) -> None:
    coordinator = ContinuationCoordinator(repo_root=tmp_path, repository=FakeRepository())
    work_item, runtime = coordinator.create_work_item(
        runtime=ContinuationRuntime.start("goal_a", max_continuations=2),
            cycle={
                "goal_id": "goal_a",
                "cycle_index": 0,
                "session_id": "session_a",
                "runtime_session_id": "runtime_a",
                "continuation_plan": {
                "next_runtime_request": {"payload": {"goal": "Continue"}},
                "work_item_template": {"objective": "Continue", "acceptance": {}},
                "evidence_chain": [],
            },
        },
    )
    marker = work_item["continuation_coordinator"]["execution_path"]
    assert work_item["continuation_coordinator"]["created_work_item"] is True
    assert marker["coordinator_only"] is True
    assert marker["executes_tasks"] is False
    assert marker["decides_adaptive_action"] is False
    assert marker["writes_evidence"] is False
    assert runtime.continuation_count == 1
