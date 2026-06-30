from core.session.engineering_session_runtime import EngineeringSessionRuntime
from core.session.session_progression_coordinator import SessionProgressionCoordinator
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




class FakeAdaptiveLoopCoordinator:
    def attach_cycle_controls(self, cycle, **kwargs):
        updated = dict(cycle)
        updated["adaptive_replan_state"] = {"accepted": True, "loop_action": "complete", "terminal": True}
        updated["adaptive_observation"] = {"goal_id": updated.get("goal_id", "goal"), "cycle_index": updated.get("cycle_index", 0)}
        return updated


class FakeLifecycleCoordinator:
    def attach_lifecycle(self, cycle, *, from_state="created"):
        updated = dict(cycle)
        updated["engineering_lifecycle_state"] = {"accepted": True, "lifecycle_state": "completed"}
        return updated


class FakeSessionCoordinator:
    def attach_session(self, cycle, *, from_state="created"):
        updated = dict(cycle)
        updated["engineering_session_state"] = {"accepted": True, "session_state": "completed"}
        return updated


class FakeProgramCoordinator:
    def attach_program(self, cycle, *, from_state="created"):
        updated = dict(cycle)
        updated["engineering_program_state"] = {"accepted": True, "program_state": "completed"}
        return updated


def test_session_runtime_is_bookkeeping_only() -> None:
    runtime = EngineeringSessionRuntime.start("goal_a", max_cycles=2, max_replans=1, max_continuations=2)
    record = runtime.to_dict()
    assert record["execution_path"]["session_runtime_bookkeeping_only"] is True
    assert record["execution_path"]["executes_tasks"] is False
    assert record["execution_path"]["creates_continuation"] is False
    assert record["execution_path"]["creates_replan"] is False
    assert record["execution_path"]["persists_records"] is False
    assert record["execution_path"]["mutates_memory"] is False


def test_session_progression_coordinator_does_not_create_records() -> None:
    coordinator = SessionProgressionCoordinator(
        adaptive_loop_coordinator=FakeAdaptiveLoopCoordinator(),
        lifecycle_coordinator=FakeLifecycleCoordinator(),
        session_coordinator=FakeSessionCoordinator(),
        program_coordinator=FakeProgramCoordinator(),
    )
    cycle, runtime = coordinator.attach_cycle_progression(
        {"goal_id": "goal_a", "cycle_index": 0},
        runtime=EngineeringSessionRuntime.start("goal_a"),
        cycle_index=0,
    )
    marker = cycle["session_progression_coordinator"]["execution_path"]
    assert marker["coordinator_only"] is True
    assert marker["creates_continuation"] is False
    assert marker["creates_replan"] is False
    assert marker["persists_records"] is False
    assert runtime.current_goal_id == "goal_a"
