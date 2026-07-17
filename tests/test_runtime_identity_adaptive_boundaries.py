from __future__ import annotations

import pytest

from core.adaptive.continuation_coordinator import ContinuationCoordinator
from core.adaptive.continuation_runtime import ContinuationRuntime
from core.adaptive.replan_coordinator import ReplanCoordinator
from core.adaptive.replan_runtime import ReplanRuntime
from core.runtime.runtime_dispatcher import RuntimeDispatcher


class _Repository:
    def save_goal(self, record):
        return record


class _CapturingQueue:
    def __init__(self) -> None:
        self.request = None

    def record_replan_request(self, package_id, request):
        self.request = request
        return {"replan_requests": []}


def test_continuation_rejects_runtime_only_identity_without_filling_session() -> None:
    coordinator = ContinuationCoordinator(repository=_Repository())

    with pytest.raises(ValueError, match="runtime_identity_missing_fields:session_id"):
        coordinator.create_work_item(
            runtime=ContinuationRuntime.start("goal-a"),
            cycle={
                "goal_id": "goal-a",
                "runtime_session_id": "runtime-a",
            },
        )


def test_replan_rejects_runtime_only_identity_without_filling_session() -> None:
    with pytest.raises(ValueError, match="runtime_identity_missing_fields:session_id"):
        ReplanCoordinator().create_replan_record(
            runtime=ReplanRuntime.start(),
            cycle={
                "goal_id": "goal-a",
                "runtime_session_id": "runtime-a",
            },
        )


def test_adaptive_coordinators_reject_session_only_identity_without_filling_runtime() -> None:
    cycle = {"goal_id": "goal-a", "session_id": "session-a"}

    with pytest.raises(ValueError, match="runtime_identity_missing_fields:runtime_session_id"):
        ContinuationCoordinator(repository=_Repository()).create_work_item(
            runtime=ContinuationRuntime.start("goal-a"),
            cycle=cycle,
        )
    with pytest.raises(ValueError, match="runtime_identity_missing_fields:runtime_session_id"):
        ReplanCoordinator().create_replan_record(
            runtime=ReplanRuntime.start(),
            cycle=cycle,
        )


def test_runtime_dispatcher_marks_missing_session_without_runtime_fallback(tmp_path) -> None:
    queue = _CapturingQueue()
    dispatcher = RuntimeDispatcher(
        queue=queue,
        task_runner=object(),
        workspace_root=tmp_path,
    )

    result = dispatcher._replan(
        package_id="package-a",
        record={"runtime_session_id": "runtime-a"},
        task={},
        feedback={},
    )

    assert result["ok"] is False
    assert queue.request["session_id"] == ""
    assert queue.request["runtime_session_id"] == "runtime-a"
    assert queue.request["identity_missing_fields"] == ["session_id"]


def test_runtime_dispatcher_marks_missing_runtime_without_polluting_session(tmp_path) -> None:
    queue = _CapturingQueue()
    dispatcher = RuntimeDispatcher(
        queue=queue,
        task_runner=object(),
        workspace_root=tmp_path,
    )

    dispatcher._replan(
        package_id="package-a",
        record={"session_id": "session-a"},
        task={},
        feedback={},
    )

    assert queue.request["session_id"] == "session-a"
    assert queue.request["runtime_session_id"] == ""
    assert queue.request["identity_missing_fields"] == ["runtime_session_id"]
