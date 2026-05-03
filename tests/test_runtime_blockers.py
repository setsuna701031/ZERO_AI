from __future__ import annotations

from pathlib import Path

from core.runtime.blockers import active_blockers, make_review_blocker
from core.runtime.task_runtime import TaskRuntime


def _task(tmp_path: Path) -> dict:
    task_dir = tmp_path / "tasks" / "task_blocker"
    return {
        "task_id": "task_blocker",
        "task_name": "task_blocker",
        "goal": "blocker smoke",
        "status": "queued",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [],
    }


def test_make_review_blocker_is_active() -> None:
    blocker = make_review_blocker("review-1", payload={"file_path": "workspace/a.py"})
    assert blocker["type"] == "review"
    assert blocker["status"] == "pending"
    assert active_blockers([blocker])[0]["id"] == "review-1"


def test_task_runtime_mark_waiting_review_uses_generic_blocker(tmp_path: Path) -> None:
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    task = _task(tmp_path)

    result = runtime.mark_waiting_review(
        task,
        review_id="review-abc",
        review_payload={"file_path": "workspace/a.py"},
    )

    state = result["runtime_state"]
    assert result["status"] == "waiting_review"
    assert state["active_blocker_count"] == 1
    assert state["blockers"][0]["type"] == "review"
    assert state["blockers"][0]["id"] == "review-abc"
    assert state["next_action"] == "wait_for_external_event"


def test_task_runtime_remove_blocker_resumes_task(tmp_path: Path) -> None:
    runtime = TaskRuntime(workspace_root=str(tmp_path))
    task = _task(tmp_path)

    runtime.mark_waiting_review(task, review_id="review-abc")
    result = runtime.remove_blocker(task, "review-abc", resolution_status="applied")

    state = result["runtime_state"]
    assert result["removed"] is True
    assert state["active_blocker_count"] == 0
    assert state["status"] == "running"
    assert state["next_action"] == "run_next_tick"
