from core.session.engineering_session_runtime import EngineeringSessionRuntime
from core.session.session_progression_coordinator import SessionProgressionCoordinator


class _Decision:
    def __init__(self, action: str) -> None:
        self.action = action

    def to_dict(self) -> dict[str, object]:
        return {"action": self.action, "terminal": self.action != "create_continuation"}


class _Adaptive:
    def attach_cycle_controls(self, cycle, **kwargs):
        updated = dict(cycle)
        updated["adaptive_replan_state"] = {"creates_continuation": True, "loop_action": "continue"}
        updated["adaptive_observation"] = {"goal_id": updated["goal_id"], "cycle_index": updated["cycle_index"]}
        updated["adaptive_delta"] = {"previous_cycle_index": None}
        updated["adaptive_loop_contract"] = {"loop_state": "initial"}
        return updated


class _Lifecycle:
    def attach_lifecycle(self, cycle, *, from_state="created"):
        updated = dict(cycle)
        updated["engineering_lifecycle_state"] = {"lifecycle_state": "continuing", "from_state": from_state}
        return updated


class _Session:
    def attach_session(self, cycle, *, from_state="created"):
        updated = dict(cycle)
        updated["engineering_session_state"] = {"session_state": "active", "from_state": from_state}
        return updated


class _Program:
    def attach_program(self, cycle, *, from_state="created"):
        updated = dict(cycle)
        updated["engineering_program_state"] = {"program_state": "active", "from_state": from_state}
        return updated


class _GoalLoop:
    def classify_state(self, state):
        return _Decision("create_continuation")


def test_session_progression_attaches_all_passive_controls() -> None:
    coordinator = SessionProgressionCoordinator(
        adaptive_loop_coordinator=_Adaptive(),
        lifecycle_coordinator=_Lifecycle(),
        session_coordinator=_Session(),
        program_coordinator=_Program(),
        goal_loop_coordinator=_GoalLoop(),
    )
    runtime = EngineeringSessionRuntime.start("goal-a")

    cycle, updated_runtime = coordinator.attach_cycle_progression(
        {"goal_id": "goal-a", "cycle_index": 0},
        runtime=runtime,
        cycle_index=0,
    )

    assert cycle["goal_loop_decision"]["action"] == "create_continuation"
    assert cycle["session_progression_coordinator"]["attached_session"] is True
    assert updated_runtime.session_from_state == "active"
    assert updated_runtime.program_from_state == "active"
    assert updated_runtime.previous_observation["goal_id"] == "goal-a"


def test_session_progression_decision_helpers() -> None:
    assert SessionProgressionCoordinator.is_continuation_decision({"action": "create_continuation"})
    assert SessionProgressionCoordinator.is_replan_decision({"action": "create_replan_record"})
    assert SessionProgressionCoordinator.is_terminal_decision({"action": "terminal"})
