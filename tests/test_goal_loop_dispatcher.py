from core.tasks.goal_loop_dispatcher import GoalLoopDispatcher
from core.adaptive.continuation_runtime import ContinuationRuntime
from core.adaptive.replan_runtime import ReplanRuntime


class FakeContinuationCoordinator:
    def create_work_item(self, *, runtime, cycle, goal_id, cycle_index, continuation_plan, runner_result):
        item = {
            "goal_id": f"{goal_id}__continuation_1",
            "continuation_coordinator": {"created_work_item": True},
        }
        return item, runtime.record_work_item(item)


class FakeReplanCoordinator:
    def create_replan_record(self, *, runtime, cycle, goal_id, cycle_index, replan_request, runner_result):
        record = {
            "goal_id": goal_id,
            "replan_coordinator": {"created_replan_record": True},
        }
        return record, runtime.record_replan(record)


def _dispatcher() -> GoalLoopDispatcher:
    return GoalLoopDispatcher(
        continuation_coordinator=FakeContinuationCoordinator(),
        replan_coordinator=FakeReplanCoordinator(),
    )


def test_dispatcher_delegates_continuation() -> None:
    result = _dispatcher().dispatch(
        loop_decision={"action": "create_continuation"},
        cycle={"goal_id": "goal_a"},
        current_goal_id="goal_a",
        cycle_index=0,
        continuation_runtime=ContinuationRuntime.start("goal_a", max_continuations=2),
        replan_runtime=ReplanRuntime.start(max_replans=1),
    )

    assert result.terminal is False
    assert result.current_goal_id == "goal_a__continuation_1"
    assert result.cycle["continuation_work_item"]["continuation_coordinator"]["created_work_item"] is True


def test_dispatcher_delegates_replan() -> None:
    result = _dispatcher().dispatch(
        loop_decision={"action": "create_replan_record", "stop_reason": "replan"},
        cycle={"goal_id": "goal_a"},
        current_goal_id="goal_a",
        cycle_index=0,
        continuation_runtime=ContinuationRuntime.start("goal_a", max_continuations=2),
        replan_runtime=ReplanRuntime.start(max_replans=1),
    )

    assert result.terminal is True
    assert result.stop_reason == "replan"
    assert result.cycle["replan_record"]["replan_coordinator"]["created_replan_record"] is True


def test_dispatcher_allows_complete_terminal_when_authority_accepts() -> None:
    result = _dispatcher().dispatch(
        loop_decision={"action": "terminal", "stop_reason": "complete"},
        cycle={
            "goal_id": "goal_a",
            "adaptive_decision_record": {"decision": "complete"},
            "goal_completion_authority_result": {
                "accepted": True,
                "completed": True,
            },
        },
        current_goal_id="goal_a",
        cycle_index=0,
        continuation_runtime=ContinuationRuntime.start("goal_a", max_continuations=2),
        replan_runtime=ReplanRuntime.start(max_replans=1),
    )

    assert result.terminal is True
    assert result.action == "terminal"
    assert result.stop_reason == "complete"


def test_dispatcher_blocks_complete_terminal_without_authority() -> None:
    result = _dispatcher().dispatch(
        loop_decision={"action": "terminal", "stop_reason": "complete"},
        cycle={
            "goal_id": "goal_a",
            "adaptive_decision_record": {"decision": "complete"},
        },
        current_goal_id="goal_a",
        cycle_index=0,
        continuation_runtime=ContinuationRuntime.start("goal_a", max_continuations=2),
        replan_runtime=ReplanRuntime.start(max_replans=1),
    )

    assert result.terminal is False
    assert result.action == "terminal_blocked"
    assert result.stop_reason == "goal_completion_authority_required"
    assert result.cycle["goal_completion_authority_required"] is True