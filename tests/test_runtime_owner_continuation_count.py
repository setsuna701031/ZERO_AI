from __future__ import annotations

from core.adaptive.continuation_runtime import ContinuationRuntime
from core.session.engineering_session_runtime import EngineeringSessionRuntime


def _continuation_count_drift(session_runtime, continuation_runtime) -> bool:
    return session_runtime.continuation_count != continuation_runtime.continuation_count


def test_continuation_count_owner_is_continuation_runtime() -> None:
    session_runtime = EngineeringSessionRuntime.start("goal_a", max_cycles=2, max_continuations=2)
    continuation_runtime = ContinuationRuntime.start("goal_a", max_continuations=2)

    continuation_runtime = continuation_runtime.record_work_item({"goal_id": "goal_a__continuation_1"})

    assert continuation_runtime.continuation_count == 1
    assert session_runtime.continuation_count == 0
    assert _continuation_count_drift(session_runtime, continuation_runtime) is True


def test_session_runtime_continuation_count_is_mirror_not_owner() -> None:
    session_runtime = EngineeringSessionRuntime.start("goal_a", max_cycles=2, max_continuations=2)
    continuation_runtime = ContinuationRuntime.start("goal_a", max_continuations=2).record_work_item(
        {"goal_id": "goal_a__continuation_1"}
    )

    mirrored = session_runtime.replace(continuation_count=continuation_runtime.continuation_count)

    assert mirrored.continuation_count == 1
    assert _continuation_count_drift(mirrored, continuation_runtime) is False
