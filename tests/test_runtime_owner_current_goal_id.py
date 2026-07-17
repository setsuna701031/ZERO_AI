from __future__ import annotations

from core.adaptive.continuation_runtime import ContinuationRuntime
from core.session.engineering_session_runtime import EngineeringSessionRuntime


def _runtime_drift(session_runtime, continuation_runtime, replan_runtime=None):
    drift = []
    if session_runtime.current_goal_id != continuation_runtime.current_goal_id:
        drift.append("current_goal_id")
    if session_runtime.continuation_count != continuation_runtime.continuation_count:
        drift.append("continuation_count")
    if replan_runtime is not None and session_runtime.replan_count != replan_runtime.replan_count:
        drift.append("replan_count")
    return drift


def test_current_goal_id_owner_is_continuation_runtime_after_work_item() -> None:
    session_runtime = EngineeringSessionRuntime.start("goal_a", max_cycles=2, max_continuations=2)
    continuation_runtime = ContinuationRuntime.start("goal_a", max_continuations=2)

    continuation_runtime = continuation_runtime.record_work_item({"goal_id": "goal_a__continuation_1"})

    assert continuation_runtime.current_goal_id == "goal_a__continuation_1"
    assert session_runtime.current_goal_id == "goal_a"
    assert "current_goal_id" in _runtime_drift(session_runtime, continuation_runtime)


def test_session_runtime_can_only_mirror_current_goal_id_from_continuation_runtime() -> None:
    session_runtime = EngineeringSessionRuntime.start("goal_a", max_cycles=2, max_continuations=2)
    continuation_runtime = ContinuationRuntime.start("goal_a", max_continuations=2).record_work_item(
        {"goal_id": "goal_a__continuation_1"}
    )

    mirrored = session_runtime.replace(current_goal_id=continuation_runtime.current_goal_id)

    assert mirrored.current_goal_id == continuation_runtime.current_goal_id
    assert _runtime_drift(mirrored, continuation_runtime) == []
