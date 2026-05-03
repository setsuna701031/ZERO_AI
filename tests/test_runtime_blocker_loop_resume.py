from __future__ import annotations

from pathlib import Path

from core.agent.loop_decision import observe_and_decide
from core.runtime.task_runtime import TaskRuntime


def _task(tmp_path: Path) -> dict:
    task_dir = tmp_path / "workspace" / "tasks" / "task_blocker_loop"
    return {
        "task_id": "task_blocker_loop",
        "task_name": "task_blocker_loop",
        "goal": "blocker loop smoke",
        "status": "running",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [{"type": "noop"}],
        "current_step_index": 0,
    }


def test_runtime_blocker_causes_loop_wait_and_resume_after_remove(tmp_path: Path) -> None:
    runtime = TaskRuntime(workspace_root=str(tmp_path / "workspace"))
    task = _task(tmp_path)

    waiting = runtime.mark_waiting_review(
        task,
        review_id="review-loop-runtime-001",
        review_payload={"file_path": "workspace/a.py"},
    )

    wait_decision = observe_and_decide(
        {
            "ok": True,
            "status": waiting["status"],
            "runtime_state": waiting["runtime_state"],
            "current_step_index": 0,
            "steps_total": 1,
        },
        task=waiting["task"],
    )

    assert wait_decision["decision"] == "wait"
    assert wait_decision["next_action"] == "wait_for_external_event"
    assert "review-loop-runtime-001" in wait_decision["reason"]

    resumed = runtime.remove_blocker(task, "review-loop-runtime-001", resolution_status="applied")

    resume_decision = observe_and_decide(
        {
            "ok": True,
            "status": resumed["status"],
            "runtime_state": resumed["runtime_state"],
            "current_step_index": 0,
            "steps_total": 1,
        },
        task=resumed["task"],
    )

    assert resumed["runtime_state"]["active_blocker_count"] == 0
    assert resume_decision["decision"] == "continue"
    assert resume_decision["next_action"] == "run_next_tick"
