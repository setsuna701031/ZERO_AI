from __future__ import annotations

from pathlib import Path

from core.tasks.goal_continuation_coordinator import GoalContinuationCoordinator, continue_engineering_goal


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


def _goal_payload(goal_id: str, steps: list[dict], *, resume: bool = False) -> dict:
    return {
        "task_type": "engineering_task",
        "engineering_goal_lifecycle": True,
        "goal_id": goal_id,
        "task_id": goal_id,
        "package_id": goal_id,
        "goal": f"Continue engineering goal {goal_id}",
        "mode": "execute",
        "approval": True,
        "resume": resume,
        "steps": steps,
    }


def test_goal_continuation_ok_only_is_not_success(tmp_path: Path) -> None:
    payload = _goal_payload(
        "goal_continuation_success",
        [_write_step("goal_continuation_success_task", "workspace/goal_continuation_success.txt", "success\n")],
    )

    result = continue_engineering_goal(payload, repo_root=tmp_path)

    lifecycle = result["goal_lifecycle"]
    assert result["ok"] is False
    assert result["terminal"] is True
    assert result["cycle_count"] == 2
    assert lifecycle["goal_state"] != "completed"
    assert lifecycle["completed_tasks"] == ["goal_continuation_success_task"]
    assert result["execution_path"]["existing_aer_path_reused"] is True
    assert (tmp_path / "workspace/goal_continuation_success.txt").read_text(encoding="utf-8") == "success\n"


def test_goal_continuation_multiple_steps_stops_without_completion_attestation(tmp_path: Path) -> None:
    payload = _goal_payload(
        "goal_continuation_multiple",
        [
            _write_step("goal_continuation_multiple_one", "workspace/goal_continuation_multiple_one.txt", "one\n"),
            _write_step("goal_continuation_multiple_two", "workspace/goal_continuation_multiple_two.txt", "two\n"),
            _write_step("goal_continuation_multiple_three", "workspace/goal_continuation_multiple_three.txt", "three\n"),
        ],
    )

    result = GoalContinuationCoordinator(repo_root=tmp_path).continue_goal(payload)

    lifecycle = result["goal_lifecycle"]
    assert result["ok"] is False
    assert lifecycle["goal_state"] != "completed"


def test_goal_continuation_resume(tmp_path: Path) -> None:
    payload = _goal_payload(
        "goal_continuation_resume",
        [
            _write_step("goal_continuation_resume_one", "workspace/goal_continuation_resume_one.txt", "one\n"),
            _write_step("goal_continuation_resume_two", "workspace/goal_continuation_resume_two.txt", "two\n"),
            _write_step("goal_continuation_resume_three", "workspace/goal_continuation_resume_three.txt", "three\n"),
        ],
    )
    coordinator = GoalContinuationCoordinator(repo_root=tmp_path)

    first = coordinator.continue_goal(payload, max_cycles=1)
    active = coordinator.load_active_goals()
    resumed = coordinator.continue_goal({**payload, "resume": True})

    assert first["terminal"] is False
    assert first["goal_lifecycle"]["goal_state"] == "next_task_generated"
    assert len(active) == 1
    assert active[0]["goal_id"] == "goal_continuation_resume"
    assert resumed["ok"] is False
    assert resumed["goal_lifecycle"]["goal_state"] != "completed"


def test_goal_continuation_blocked(tmp_path: Path) -> None:
    payload = _goal_payload(
        "goal_continuation_blocked",
        [
            _write_step("goal_continuation_blocked_one", "workspace/goal_continuation_blocked_one.txt", "one\n"),
            _write_step("goal_continuation_blocked_two", "core/runtime/goal_continuation_blocked.py", "blocked\n"),
            _write_step("goal_continuation_blocked_never", "workspace/goal_continuation_blocked_never.txt", "never\n"),
        ],
    )

    result = GoalContinuationCoordinator(repo_root=tmp_path).continue_goal(payload)

    lifecycle = result["goal_lifecycle"]
    assert result["ok"] is False
    assert result["terminal"] is True
    assert result["stopped_reason"] == "blocked"
    assert result["cycle_count"] == 2
    assert lifecycle["goal_state"] == "blocked"
    assert lifecycle["completed_tasks"] == ["goal_continuation_blocked_one"]
    assert lifecycle["blocked_tasks"] == ["goal_continuation_blocked_two"]
    assert not (tmp_path / "workspace/goal_continuation_blocked_never.txt").exists()
    assert not (tmp_path / "core/runtime/goal_continuation_blocked.py").exists()


def test_goal_continuation_does_not_complete_without_canonical_attestation(tmp_path: Path) -> None:
    payload = _goal_payload(
        "goal_continuation_complete",
        [
            _write_step("goal_continuation_complete_one", "workspace/goal_continuation_complete_one.txt", "one\n"),
            _write_step("goal_continuation_complete_two", "workspace/goal_continuation_complete_two.txt", "two\n"),
            _write_step("goal_continuation_complete_three", "workspace/goal_continuation_complete_three.txt", "three\n"),
        ],
    )

    result = continue_engineering_goal(payload, repo_root=tmp_path)
    lifecycle = result["engineering_goal_lifecycle"]

    assert lifecycle["goal_state"] != "completed"
    assert result["ok"] is False
    assert GoalContinuationCoordinator(repo_root=tmp_path).load_active_goals() == []


def coordinator_events(lifecycle: dict) -> set[str]:
    return {str(item.get("event") or "") for item in lifecycle.get("lifecycle_events", []) if isinstance(item, dict)}
