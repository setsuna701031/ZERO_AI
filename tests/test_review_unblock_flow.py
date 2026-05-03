from __future__ import annotations

from pathlib import Path

from core.repo_sandbox.review import apply_review, create_review, reject_review
from core.runtime.task_runtime import TaskRuntime


def _task(tmp_path: Path) -> dict:
    task_dir = tmp_path / "workspace" / "tasks" / "task_review_unblock"
    return {
        "task_id": "task_review_unblock",
        "task_name": "task_review_unblock",
        "goal": "review unblock",
        "status": "running",
        "task_dir": str(task_dir),
        "runtime_state_file": str(task_dir / "runtime_state.json"),
        "steps": [],
        "current_step_index": 0,
    }


def test_apply_review_clears_review_blocker(tmp_path: Path) -> None:
    repo_root = tmp_path
    target = repo_root / "workspace" / "n_apply_sample.py"
    sandbox_target = repo_root / "workspace" / "repo_sandbox" / "workspace" / "n_apply_sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    sandbox_target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    sandbox_target.write_text("VALUE = 2\n", encoding="utf-8")

    runtime = TaskRuntime(workspace_root=str(repo_root / "workspace"))
    task = _task(tmp_path)
    runtime.mark_waiting_review(
        task,
        review_id="review-n-apply",
        review_payload={"file_path": "workspace/n_apply_sample.py"},
    )

    create_review(
        "review-n-apply",
        {
            "file_path": "workspace/n_apply_sample.py",
            "_repo_root": str(repo_root),
            "runtime_state_file": task["runtime_state_file"],
            "workspace_root": str(repo_root / "workspace"),
        },
        diff="-VALUE = 1\n+VALUE = 2\n",
    )

    result = apply_review("review-n-apply")
    assert result["status"] == "applied"
    assert target.read_text(encoding="utf-8") == "VALUE = 2\n"

    loaded = runtime.load_runtime_state(task)
    assert loaded["requires_review"] is False
    assert not any(b.get("status") == "pending" for b in loaded.get("blockers", []))


def test_reject_review_clears_review_blocker_without_touching_file(tmp_path: Path) -> None:
    repo_root = tmp_path
    target = repo_root / "workspace" / "n_reject_sample.py"
    sandbox_target = repo_root / "workspace" / "repo_sandbox" / "workspace" / "n_reject_sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    sandbox_target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("VALUE = 1\n", encoding="utf-8")
    sandbox_target.write_text("VALUE = 2\n", encoding="utf-8")

    runtime = TaskRuntime(workspace_root=str(repo_root / "workspace"))
    task = _task(tmp_path)
    runtime.mark_waiting_review(
        task,
        review_id="review-n-reject",
        review_payload={"file_path": "workspace/n_reject_sample.py"},
    )

    create_review(
        "review-n-reject",
        {
            "file_path": "workspace/n_reject_sample.py",
            "_repo_root": str(repo_root),
            "runtime_state_file": task["runtime_state_file"],
            "workspace_root": str(repo_root / "workspace"),
        },
        diff="-VALUE = 1\n+VALUE = 2\n",
    )

    result = reject_review("review-n-reject", reason="test reject")
    assert result["status"] == "rejected"
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"

    loaded = runtime.load_runtime_state(task)
    assert loaded["requires_review"] is False
    assert not any(b.get("status") == "pending" for b in loaded.get("blockers", []))
