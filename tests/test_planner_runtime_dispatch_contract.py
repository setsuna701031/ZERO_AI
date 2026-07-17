from __future__ import annotations

import json
from pathlib import Path

from core.runtime.planner_runtime_dispatch import (

    dispatch_planner_result_to_persistent_runtime,
    planner_result_to_persistent_runtime_task,
    should_dispatch_planner_result_to_persistent_runtime,
)
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]



def read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_planner_result_to_persistent_runtime_task_converts_steps_to_cycles() -> None:
    planner_result = {
        "goal": "Persistent Autonomous Engineering Runtime from planner",
        "persistent_runtime": True,
        "steps": [
            {"type": "read_file", "description": "inspect current runtime files", "target_file": "core/agent/agent_loop.py"},
            {"type": "verify", "description": "run runtime contract tests"},
        ],
    }

    task = planner_result_to_persistent_runtime_task(
        user_input="build long runtime",
        planner_result=planner_result,
    )

    assert task["persistent_runtime"] is True
    assert task["mode"] == "persistent_runtime"
    assert task["id"].startswith("planner_prt_")
    assert len(task["cycles"]) == 1
    assert task["cycles"][0]["cycle_id"] == "planner_cycle_1"
    assert len(task["cycles"][0]["target_groups"]) == 2
    assert "inspect current runtime files" in task["cycles"][0]["target_groups"][0]


def test_should_dispatch_planner_result_detects_persistent_plan() -> None:
    assert should_dispatch_planner_result_to_persistent_runtime(
        user_input="normal",
        planner_result={"persistent_runtime": True},
    ) is True

    assert should_dispatch_planner_result_to_persistent_runtime(
        user_input="Persistent Autonomous Engineering Runtime",
        planner_result={"steps": [{"description": "x"}]},
    ) is True

    assert should_dispatch_planner_result_to_persistent_runtime(
        user_input="normal short task",
        planner_result={"steps": [{"description": "x"}]},
    ) is False


def test_dispatch_planner_result_to_persistent_runtime_runs_orchestrator(tmp_path: Path) -> None:
    planner_result = {
        "goal": "Persistent Autonomous Engineering Runtime from planner",
        "persistent_runtime": True,
        "steps": [
            {"type": "inspect", "description": "planner creates cycle one"},
            {"type": "verify", "description": "planner verifies cycle one"},
        ],
    }

    result = dispatch_planner_result_to_persistent_runtime(
        repo_root=tmp_path,
        user_input="Persistent Autonomous Engineering Runtime",
        planner_result=planner_result,
    )

    dispatch = result["planner_runtime_dispatch"]
    orchestrator = dispatch["orchestrator"]

    assert result["ok"] is True
    assert dispatch["ok"] is True
    assert dispatch["status"] == "dispatched"
    assert dispatch["routed"] is True
    assert orchestrator["ok"] is True
    assert orchestrator["status"] == "finished"
    assert orchestrator["cycle_count"] == 1

    log = read_json(dispatch["dispatch_log_path"])
    assert log["schema"] == "zero.aer.planner_runtime_dispatch.v1"
    assert log["dispatches"][-1]["status"] == "dispatched"


def test_dispatch_planner_result_refuses_normal_plan_without_force(tmp_path: Path) -> None:
    result = dispatch_planner_result_to_persistent_runtime(
        repo_root=tmp_path,
        user_input="normal short task",
        planner_result={"steps": [{"description": "normal step"}]},
    )

    dispatch = result["planner_runtime_dispatch"]

    assert result["ok"] is False
    assert dispatch["status"] == "not_persistent_runtime_plan"
    assert dispatch["routed"] is False


def test_dispatch_planner_result_force_runs_normal_plan(tmp_path: Path) -> None:
    result = dispatch_planner_result_to_persistent_runtime(
        repo_root=tmp_path,
        user_input="normal short task",
        planner_result={"steps": [{"description": "forced normal step"}]},
        force=True,
    )

    dispatch = result["planner_runtime_dispatch"]
    orchestrator = dispatch["orchestrator"]

    assert result["ok"] is True
    assert dispatch["status"] == "dispatched"
    assert orchestrator["status"] == "finished"
