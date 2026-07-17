from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]




REPO_ROOT = Path(__file__).resolve().parents[1]


def test_real_goal_loop_does_not_complete_without_goal_completion_authority(tmp_path) -> None:
    repository = EngineeringGoalRepository(tmp_path)
    goal = repository.save_goal({"summary": "Build demo system"})

    result = EngineeringGoalLoop(repo_root=tmp_path, repository=repository).run_until_terminal(goal["goal_id"])

    assert result["ok"] is False
    assert result["terminal"] is True
    assert result["stop_reason"] == "replan"
    assert result["cycle_count"] == 1
    assert result["cycles"][0]["runtime_state"] == "replan"
    assert result["cycles"][0]["adaptive_decision"] == "replan"
    assert result["goal_completion_authority_result"] == {}


def test_goal_loop_cli_smoke_outputs_cycles_summary(tmp_path) -> None:
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

    loop = subprocess.run(
        [python, str(REPO_ROOT / "app.py"), "goal", "loop", goal_id],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(loop.stdout)
    summary = payload["cycles_summary"]

    assert payload["ok"] is False
    assert summary["goal_id"] == goal_id
    assert summary["terminal"] is True
    assert summary["stop_reason"] == "replan"
    assert summary["cycle_count"] == 1
    assert summary["cycles"][0]["cycle_index"] == 0
    assert summary["cycles"][0]["adaptive_decision"] == "replan"
