from __future__ import annotations

import json
from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository
from core.tasks.engineering_portfolio_repository import EngineeringPortfolioRepository
from core.tasks.engineering_program_cycle import EngineeringProgramCycle
from core.tasks.engineering_program_repository import EngineeringProgramRepository
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




def test_agent_loop_routes_persisted_engineering_goal_through_program_mainline(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    def fake_run_until_idle(self, program_id: str, max_portfolios: int = 5):
        calls.append(program_id)
        return {
            "schema": "zero.engineering_program_cycle.summary.v1",
            "ok": True,
            "program_id": program_id,
            "portfolio_id": "portfolio_1",
            "goal_id": "agent_goal_1",
            "selected_goal": {"selected_goal_id": "agent_goal_1"},
            "adaptive_decision": {"decision": "complete"},
            "stop_reason": "program_completed",
            "runs": [],
        }

    def fail_goal_loop(*args, **kwargs):
        raise AssertionError("AgentLoop must not bypass Program into GoalLoop")

    monkeypatch.setattr(EngineeringProgramCycle, "run_until_idle", fake_run_until_idle)
    monkeypatch.setattr(EngineeringGoalLoop, "run_until_terminal", fail_goal_loop)

    payload = json.dumps(
        {
            "task_type": "engineering_task",
            "engineering_goal_route": True,
            "repo_root": str(tmp_path),
            "goal_id": "agent_goal_1",
            "program_id": "program_1",
            "portfolio_id": "portfolio_1",
            "goal": "Build adaptive goal route",
            "max_cycles": 2,
        }
    )

    response = AgentLoop(repo_root=str(tmp_path)).run(payload)
    saved_goal = EngineeringGoalRepository(tmp_path).load_goal("agent_goal_1")

    assert response["ok"] is True
    assert response["mode"] == "engineering_program_mainline"
    assert response["agent_loop_runtime_route"] == "engineering_program_mainline"
    assert response["legacy_direct_json_engineering_task_runner"] is False
    assert response["plan"]["delegated_to"] == "core.tasks.engineering_program_cycle.EngineeringProgramCycle.run_until_idle"
    assert response["route"]["authority_path"] == "AgentLoop -> RuntimeNativeMainline -> Program -> Portfolio -> Goal -> Adaptive Planner -> Runtime"
    assert calls == ["program_1"]
    assert response["program_id"] == "program_1"
    assert response["portfolio_id"] == "portfolio_1"
    assert response["goal_id"] == "agent_goal_1"
    assert response["selected_goal"]["selected_goal_id"] == "agent_goal_1"
    assert response["adaptive_decision"]["decision"] == "complete"
    assert response["stop_reason"] == "program_completed"
    assert response["execution_path"]["direct_goal_runner_bypass"] is False
    assert saved_goal is not None
    assert saved_goal["payload"]["engineering_goal_lifecycle"] is True
    assert EngineeringPortfolioRepository(tmp_path).list_portfolio_goals("portfolio_1") == ["agent_goal_1"]
    assert EngineeringProgramRepository(tmp_path).load_program("program_1")["portfolio_ids"] == ["portfolio_1"]


def test_agent_loop_direct_engineering_task_route_is_labeled_legacy(tmp_path: Path, monkeypatch) -> None:
    def fake_run_engineering_task(payload, *, repo_root):
        return {
            "schema": "zero.engineering_task_runner.v1",
            "ok": True,
            "mode": "engineering_task_runner",
            "package_id": "legacy_task",
            "requirement_summary": {},
            "normalized_payload": {},
            "result_bundle": {"schema": "zero.engineering_task.result_bundle.v1", "artifact_paths": {}},
            "work_package_result": {},
            "verification_result": {},
            "change_set": {},
            "final_message": "done",
        }

    monkeypatch.setattr("core.tasks.engineering_task_runner.run_engineering_task", fake_run_engineering_task)

    response = AgentLoop(repo_root=str(tmp_path)).run(
        json.dumps(
            {
                "task_type": "engineering_task",
                "repo_root": str(tmp_path),
                "task_id": "legacy_task",
                "goal": "Run direct legacy task",
            }
        )
    )

    assert response["ok"] is True
    assert response["mode"] == "engineering_task_runner"
    assert response["agent_loop_runtime_route"] == "engineering_task_runner"
    assert response["legacy_direct_json_engineering_task_runner"] is False
    assert response["route"]["legacy_direct_json_engineering_task_runner"] is False
    assert response["execution_path"]["legacy_direct_engineering_task_route"] is False
    assert response["execution_path"]["program_mainline"] is False
