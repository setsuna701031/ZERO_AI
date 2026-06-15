from __future__ import annotations

from pathlib import Path

from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_goal_runner import EngineeringGoalRunner


def test_fresh_goal_run_ignores_dirty_repo_root_workspace_and_poison_memory(tmp_path: Path) -> None:
    work_packages = tmp_path / "workspace" / "work_packages"
    work_packages.mkdir(parents=True)
    (work_packages / "engineering_memory_store.json").write_text(
        '{"schema":"poison","records":[{"goal":"Build isolated system","status":"failed","keywords":["isolated"]}]}',
        encoding="utf-8",
    )
    (work_packages / "goal_build_isolated_system.engineering_goal_state.json").write_text(
        '{"schema":"zero.engineering_task.goal_state.v1","goal_id":"goal_build_isolated_system","goal_state":"failed","failed_tasks":["poison_task"]}',
        encoding="utf-8",
    )
    (work_packages / "goal_build_isolated_system.engineering_state.json").write_text(
        '{"schema":"poison","status":"failed"}',
        encoding="utf-8",
    )

    repository = EngineeringGoalRepository(tmp_path)
    goal = repository.save_goal({"summary": "Build isolated system"})

    result = EngineeringGoalRunner(repo_root=tmp_path, repository=repository).run_goal(goal["goal_id"])

    runtime = result["runtime_result"]
    continuation = runtime["iterations"][0]["continuation_result"]
    lifecycle = continuation["goal_lifecycle"]
    assert result["ok"] is False
    assert runtime["state"] == "replan"
    assert lifecycle["goal_state"] == "failed"
    assert lifecycle["completion_rejected"] is True
    assert "poison_task" not in repr(runtime)


def test_fresh_goal_run_does_not_read_large_repo_root_memory_store(tmp_path: Path) -> None:
    work_packages = tmp_path / "workspace" / "work_packages"
    work_packages.mkdir(parents=True)
    memory_path = work_packages / "engineering_memory_store.json"
    memory_path.write_text(
        '{"schema":"poison","records":[' + ",".join('{"goal":"poison","status":"failed"}' for _ in range(2000)) + "]}",
        encoding="utf-8",
    )

    repository = EngineeringGoalRepository(tmp_path)
    goal = repository.save_goal({"summary": "Build memory-isolated system"})

    result = EngineeringGoalRunner(repo_root=tmp_path, repository=repository).run_goal(goal["goal_id"])

    assert result["ok"] is False
    assert result["runtime_result"]["state"] == "replan"
    assert memory_path.exists()
    assert memory_path.stat().st_size > 50000
