from core.tasks.lifecycle_coordinator import LifecycleCoordinator


class FakeLifecycle:
    def evaluate_cycle(self, cycle, *, from_state):
        return {
            "accepted": True,
            "from_state": from_state,
            "to_state": "running",
            "terminal": False,
        }


def test_lifecycle_coordinator_attaches_lifecycle_without_mutating_runtime() -> None:
    coordinator = LifecycleCoordinator(engineering_lifecycle_state_machine=FakeLifecycle())
    cycle = {"goal_id": "g1", "engineering_runtime_contract": {"runtime_result": {}}}
    result = coordinator.attach_lifecycle(cycle, from_state="created")

    assert result["engineering_lifecycle_state"]["from_state"] == "created"
    assert result["engineering_lifecycle_state"]["to_state"] == "running"
    assert result["lifecycle_coordinator"]["execution_path"]["executes_tasks"] is False
    assert result["lifecycle_coordinator"]["execution_path"]["mutates_memory"] is False
    assert "engineering_lifecycle_state" not in cycle
