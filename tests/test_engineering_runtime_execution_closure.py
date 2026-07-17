from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_goal_runner import EngineeringGoalRunner
import pytest

pytestmark = [pytest.mark.integration]




REPO_ROOT = Path(__file__).resolve().parents[1]


def test_goal_run_task_completion_does_not_complete_goal_without_attestation(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    goal = repository.save_goal({"summary": "Build demo system"})

    result = EngineeringGoalRunner(repo_root=tmp_path, repository=repository).run_goal(goal["goal_id"])

    runtime = result["runtime_result"]
    iterations = runtime["iterations"]
    continuation = iterations[-1]["continuation_result"]
    lifecycle = continuation["goal_lifecycle"]
    completed = set(lifecycle["completed_tasks"])

    assert result["ok"] is False
    assert runtime["state"] == "replan"
    assert continuation["stopped_reason"] == "failed"
    assert lifecycle["goal_state"] == "failed"
    assert lifecycle["completion_rejected"] is True
    assert completed == {f"{goal['goal_id']}_breakdown", f"{goal['goal_id']}_result"}
    assert any(cycle["submitted_to"] == "core.tasks.engineering_task_runner.run_engineering_task" for cycle in continuation["cycles"])
    assert result["runtime_root_cause"]["decision_state"] == "replan"


def test_repeated_summary_goal_uses_fresh_runtime_identity(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    first = repository.save_goal({"summary": "Build demo system"})
    first_result = EngineeringGoalRunner(repo_root=tmp_path, repository=repository).run_goal(first["goal_id"])
    second = repository.save_goal({"summary": "Build demo system"})
    second_result = EngineeringGoalRunner(repo_root=tmp_path, repository=repository).run_goal(second["goal_id"])

    assert first["goal_id"] != second["goal_id"]
    assert first_result["runtime_result"]["state"] == "replan"
    assert second_result["runtime_result"]["state"] == "replan"
    assert second_result["runtime_root_cause"]["decision_state"] == "replan"


def test_goal_run_cli_smoke_rejects_completion_without_attestation(tmp_path) -> None:
    store = tmp_path / "goals.json"
    env = {**dict(os.environ), "ZERO_GOAL_STORE": str(store), "PYTHONPATH": str(REPO_ROOT)}
    python = sys.executable

    add = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "goal", "add", "Build demo system"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    created = json.loads(add.stdout)
    goal_id = created["goal"]["goal_id"]

    run = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "goal", "run", goal_id],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(run.stdout)
    runtime = payload["runner_result"]["runtime_result"]

    assert payload["ok"] is False
    assert runtime["state"] == "replan"
    assert runtime["decision_state"] == "replan"
    assert runtime["iterations"][0]["state"] == "replan"
    assert runtime["iterations"][0]["continuation"]["goal_lifecycle"]["goal_state"] != "completed"
    assert payload["runner_result"]["runtime_root_cause"]["decision_state"] == "replan"
