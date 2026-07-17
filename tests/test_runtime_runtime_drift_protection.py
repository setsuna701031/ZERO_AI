from __future__ import annotations

from core.adaptive.continuation_runtime import ContinuationRuntime
from core.adaptive.replan_runtime import ReplanRuntime
from core.session.engineering_session_runtime import EngineeringSessionRuntime


def detect_runtime_drift(*, session_runtime, continuation_runtime, replan_runtime) -> dict[str, object]:
    drift = {
        "current_goal_id": session_runtime.current_goal_id != continuation_runtime.current_goal_id,
        "continuation_count": session_runtime.continuation_count != continuation_runtime.continuation_count,
        "replan_count": session_runtime.replan_count != replan_runtime.replan_count,
    }
    return {
        "has_drift": any(drift.values()),
        "drift": drift,
    }


def test_runtime_drift_detection_catches_all_mirrored_state_mismatches() -> None:
    session_runtime = EngineeringSessionRuntime.start("goal_a", max_cycles=3, max_replans=3, max_continuations=3).replace(
        current_goal_id="goal_a",
        continuation_count=3,
        replan_count=2,
    )
    continuation_runtime = ContinuationRuntime.start("goal_a__continuation_1", continuation_count=2, max_continuations=3)
    replan_runtime = ReplanRuntime.start(replan_count=1, max_replans=3)

    result = detect_runtime_drift(
        session_runtime=session_runtime,
        continuation_runtime=continuation_runtime,
        replan_runtime=replan_runtime,
    )

    assert result["has_drift"] is True
    assert result["drift"] == {
        "current_goal_id": True,
        "continuation_count": True,
        "replan_count": True,
    }


def test_runtime_drift_detection_accepts_authoritative_mirrors() -> None:
    continuation_runtime = ContinuationRuntime.start("goal_a", max_continuations=3).record_work_item(
        {"goal_id": "goal_a__continuation_1"}
    )
    replan_runtime = ReplanRuntime.start(max_replans=3).record_replan({"goal_id": "goal_a"})
    session_runtime = EngineeringSessionRuntime.start("goal_a", max_cycles=3, max_replans=3, max_continuations=3).replace(
        current_goal_id=continuation_runtime.current_goal_id,
        continuation_count=continuation_runtime.continuation_count,
        replan_count=replan_runtime.replan_count,
    )

    result = detect_runtime_drift(
        session_runtime=session_runtime,
        continuation_runtime=continuation_runtime,
        replan_runtime=replan_runtime,
    )

    assert result["has_drift"] is False
    assert result["drift"] == {
        "current_goal_id": False,
        "continuation_count": False,
        "replan_count": False,
    }
