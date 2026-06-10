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


def test_dispatcher_delegates_continuation() -> None:
    dispatcher = GoalLoopDispatcher(
        continuation_coordinator=FakeContinuationCoordinator(),
        replan_coordinator=FakeReplanCoordinator(),
    )
    result = dispatcher.dispatch(
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
    dispatcher = GoalLoopDispatcher(
        continuation_coordinator=FakeContinuationCoordinator(),
        replan_coordinator=FakeReplanCoordinator(),
    )
    result = dispatcher.dispatch(
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
