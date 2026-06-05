from __future__ import annotations

import json
from pathlib import Path

from core.agent.agent_loop import AgentLoop
from core.tasks.engineering_goal_loop import EngineeringGoalLoop
from core.tasks.engineering_goal_repository import EngineeringGoalRepository


def test_agent_loop_routes_opted_in_engineering_task_through_goal_stack(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    def fake_run_until_terminal(self, goal_id: str, max_cycles: int = 3):
        calls.append(goal_id)
        return {
            "schema": "zero.engineering_goal_loop.v1",
            "ok": True,
            "mode": "engineering_goal_loop",
            "goal_id": goal_id,
            "terminal": True,
            "stop_reason": "complete",
            "cycles": [],
        }

    monkeypatch.setattr(EngineeringGoalLoop, "run_until_terminal", fake_run_until_terminal)

    payload = json.dumps(
        {
            "task_type": "engineering_task",
            "engineering_goal_route": True,
            "repo_root": str(tmp_path),
            "goal_id": "agent_goal_1",
            "goal": "Build adaptive goal route",
            "max_cycles": 2,
        }
    )

    response = AgentLoop(repo_root=str(tmp_path)).run(payload)
    saved_goal = EngineeringGoalRepository(tmp_path).load_goal("agent_goal_1")

    assert response["ok"] is True
    assert response["mode"] == "engineering_goal_stack"
    assert response["agent_loop_runtime_route"] == "engineering_goal_stack"
    assert response["legacy_direct_json_engineering_task_runner"] is False
    assert response["plan"]["delegated_to"] == "core.tasks.engineering_goal_loop.EngineeringGoalLoop.run_until_terminal"
    assert response["route"]["authority_path"].startswith("AgentLoop -> EngineeringGoalRepository")
    assert calls == ["agent_goal_1"]
    assert saved_goal is not None
    assert saved_goal["payload"]["engineering_goal_lifecycle"] is True


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
    assert response["legacy_direct_json_engineering_task_runner"] is True
    assert response["route"]["legacy_direct_json_engineering_task_runner"] is True
