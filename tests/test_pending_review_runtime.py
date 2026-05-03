from __future__ import annotations

from pathlib import Path

from core.runtime.task_runtime import TaskRuntime


def test_task_runtime_mark_waiting_review_persists_review_fields(tmp_path: Path) -> None:
    runtime = TaskRuntime(workspace_root=str(tmp_path / "workspace"))
    task = {
        "task_id": "task_review_runtime",
        "task_name": "task_review_runtime",
        "goal": "review runtime",
        "status": "running",
        "task_dir": str(tmp_path / "workspace" / "tasks" / "task_review_runtime"),
        "runtime_state_file": str(tmp_path / "workspace" / "tasks" / "task_review_runtime" / "runtime_state.json"),
        "steps": [],
        "current_step_index": 0,
    }

    result = runtime.mark_waiting_review(
        task,
        current_tick=3,
        review_id="review-runtime-001",
        review_payload={"file_path": "workspace/a.py"},
    )

    assert result["status"] == "waiting_review"
    assert result["requires_review"] is True
    assert result["review_status"] == "pending_review"
    assert result["review_id"] == "review-runtime-001"

    loaded = runtime.load_runtime_state(task)
    assert loaded["status"] == "waiting_review"
    assert loaded["requires_review"] is True
    assert loaded["review_status"] == "pending_review"
    assert loaded["review_id"] == "review-runtime-001"
    assert loaded["review_payload"] == {"file_path": "workspace/a.py"}

    assert task["status"] == "waiting_review"
    assert task["requires_review"] is True
    assert task["review_id"] == "review-runtime-001"
