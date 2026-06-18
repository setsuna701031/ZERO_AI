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


def test_continuation_coordinator_creates_work_item_and_updates_runtime(tmp_path) -> None:
    repo = FakeRepository()
    coordinator = ContinuationCoordinator(repo_root=tmp_path, repository=repo)
    runtime = ContinuationRuntime.start("goal_a", max_continuations=2)
    cycle = {
        "goal_id": "goal_a",
        "cycle_index": 0,
        "session_id": "session_a",
        "runtime_session_id": "runtime_a",
        "continuation_plan": {
            "next_runtime_request": {"payload": {"goal": "Continue work"}},
            "work_item_template": {"objective": "Continue work", "acceptance": {"ok": True}},
            "evidence_chain": [{"evidence_id": "e1"}],
        },
    }
    work_item, updated = coordinator.create_work_item(runtime=runtime, cycle=cycle)
    assert work_item["goal_id"] == "goal_a__continuation_1"
    assert updated.current_goal_id == "goal_a__continuation_1"
    assert updated.continuation_count == 1
    assert repo.load_goal("goal_a__continuation_1")["metadata"]["source"] == "continuation_coordinator"
