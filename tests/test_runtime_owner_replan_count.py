from __future__ import annotations

from core.adaptive.replan_runtime import ReplanRuntime
from core.session.engineering_session_runtime import EngineeringSessionRuntime


def _replan_count_drift(session_runtime, replan_runtime) -> bool:
    return session_runtime.replan_count != replan_runtime.replan_count


def test_replan_count_owner_is_replan_runtime() -> None:
    session_runtime = EngineeringSessionRuntime.start("goal_a", max_cycles=1, max_replans=2)
    replan_runtime = ReplanRuntime.start(max_replans=2)

    replan_runtime = replan_runtime.record_replan({"goal_id": "goal_a"})

    assert replan_runtime.replan_count == 1
    assert session_runtime.replan_count == 0
    assert _replan_count_drift(session_runtime, replan_runtime) is True


def test_session_runtime_replan_count_is_mirror_not_owner() -> None:
    session_runtime = EngineeringSessionRuntime.start("goal_a", max_cycles=1, max_replans=2)
    replan_runtime = ReplanRuntime.start(max_replans=2).record_replan({"goal_id": "goal_a"})

    mirrored = session_runtime.replace(replan_count=replan_runtime.replan_count)

    assert mirrored.replan_count == 1
    assert _replan_count_drift(mirrored, replan_runtime) is False
