from __future__ import annotations

from pathlib import Path

from core.tasks.engineering_task_runner import run_engineering_task


def _goal_payload(goal_id: str, *, steps: list[dict], resume: bool = False) -> dict:
    return {
        "task_type": "engineering_task",
        "engineering_goal_lifecycle": True,
        "goal_id": goal_id,
        "task_id": goal_id,
        "package_id": goal_id,
        "goal": f"Lifecycle goal {goal_id}",
        "mode": "execute",
        "approval": True,
        "resume": resume,
        "steps": steps,
    }


def _write_step(package_id: str, target_path: str, content: str) -> dict:
    return {
        "package_id": package_id,
        "goal": f"Write {target_path}",
        "edits": [
            {
                "operation": "write_file",
                "target_path": target_path,
                "content": content,
                "verify_contains": content.strip(),
            }
        ],
    }


def test_goal_record_is_created(tmp_path: Path) -> None:
    result = run_engineering_task(
        _goal_payload(
            "goal_lifecycle_created",
            steps=[_write_step("goal_lifecycle_created_task", "workspace/goal_lifecycle_created.txt", "created\n")],
        ),
        repo_root=tmp_path,
    )

    lifecycle = result["result_bundle"]["goal_lifecycle"]

    assert lifecycle["schema"] == "zero.engineering_task.goal_state.v1"
    assert lifecycle["goal_id"] == "goal_lifecycle_created"
    assert Path(lifecycle["state_path"]).exists()
    assert lifecycle["completed_tasks"] == ["goal_lifecycle_created_task"]
    assert {item["event"] for item in lifecycle["lifecycle_events"]} >= {"goal_created", "running", "task_selected"}


def test_goal_progresses_after_successful_task_and_generates_next_task(tmp_path: Path) -> None:
    result = run_engineering_task(
        _goal_payload(
            "goal_lifecycle_progress",
            steps=[
                _write_step("goal_lifecycle_progress_one", "workspace/goal_lifecycle_progress_one.txt", "one\n"),
                _write_step("goal_lifecycle_progress_two", "workspace/goal_lifecycle_progress_two.txt", "two\n"),
            ],
        ),
        repo_root=tmp_path,
    )

    lifecycle = result["result_bundle"]["goal_lifecycle"]
    nested_bundle = result["result_bundle"]["step_results"][0]["result"]["result_bundle"]

    assert lifecycle["goal_state"] == "next_task_generated"
    assert lifecycle["progress"]["completed_count"] == 1
    assert lifecycle["remaining_tasks"] == ["goal_lifecycle_progress_two"]
    assert lifecycle["next_task"] == "goal_lifecycle_progress_two"
    assert any(item["event"] == "progress_evaluated" for item in lifecycle["lifecycle_events"])
    assert any(item["event"] == "next_task_generated" for item in lifecycle["lifecycle_events"])
    assert nested_bundle["execution_path"]["no_new_runtime_path"] is True
    assert nested_bundle["execution_path"]["direct_write_shortcut"] is False
    assert "WorkPackageScheduler.submit" in nested_bundle["execution_path"]["existing_aer_work_package_path"]


def test_blocked_task_moves_goal_to_blocked(tmp_path: Path) -> None:
    result = run_engineering_task(
        _goal_payload(
            "goal_lifecycle_blocked",
            steps=[
                _write_step(
                    "goal_lifecycle_blocked_task",
                    "core/runtime/goal_lifecycle_blocked_task.py",
                    "blocked\n",
                )
            ],
        ),
        repo_root=tmp_path,
    )

    lifecycle = result["result_bundle"]["goal_lifecycle"]

    assert result["ok"] is False
    assert lifecycle["goal_state"] == "blocked"
    assert lifecycle["blocked_tasks"] == ["goal_lifecycle_blocked_task"]
    assert lifecycle["completed_tasks"] == []
    assert any(item["event"] == "blocked" for item in lifecycle["lifecycle_events"])


def test_completed_goal_is_marked_completed_and_memory_updated(tmp_path: Path) -> None:
    result = run_engineering_task(
        _goal_payload(
            "goal_lifecycle_completed",
            steps=[_write_step("goal_lifecycle_completed_task", "workspace/goal_lifecycle_completed.txt", "done\n")],
        ),
        repo_root=tmp_path,
    )

    lifecycle = result["result_bundle"]["goal_lifecycle"]

    assert result["ok"] is True
    assert lifecycle["goal_state"] == "completed"
    assert lifecycle["progress"]["percent_complete"] == 1.0
    assert lifecycle["remaining_tasks"] == []
    assert any(item["event"] == "memory_updated" for item in lifecycle["lifecycle_events"])
    assert any(ref["source"] == "updated_memory" for ref in lifecycle["memory_refs"])


def test_resume_preserves_goal_state_across_executions(tmp_path: Path) -> None:
    payload = _goal_payload(
        "goal_lifecycle_resume",
        steps=[
            _write_step("goal_lifecycle_resume_one", "workspace/goal_lifecycle_resume_one.txt", "one\n"),
            _write_step("goal_lifecycle_resume_two", "workspace/goal_lifecycle_resume_two.txt", "two\n"),
        ],
    )
    first = run_engineering_task(payload, repo_root=tmp_path)
    resumed = run_engineering_task({**payload, "resume": True}, repo_root=tmp_path)

    first_lifecycle = first["result_bundle"]["goal_lifecycle"]
    resumed_lifecycle = resumed["result_bundle"]["goal_lifecycle"]

    assert first_lifecycle["goal_state"] == "next_task_generated"
    assert resumed_lifecycle["goal_state"] == "completed"
    assert resumed_lifecycle["completed_tasks"] == [
        "goal_lifecycle_resume_one",
        "goal_lifecycle_resume_two",
    ]
    assert resumed_lifecycle["progress"]["completed_count"] == 2
    assert any(item["event"] == "next_task_generated" for item in resumed_lifecycle["lifecycle_events"])
