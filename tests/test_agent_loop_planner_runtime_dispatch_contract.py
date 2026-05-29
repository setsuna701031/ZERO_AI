from __future__ import annotations

import json
from pathlib import Path

from core.agent.agent_loop import AgentLoop


class DummyPlanner:
    def __init__(self) -> None:
        self.calls = []

    def plan(self, context=None, user_input="", route=None, **kwargs):
        self.calls.append(
            {
                "context": context,
                "user_input": user_input,
                "route": route,
                "kwargs": kwargs,
            }
        )
        return {
            "ok": True,
            "goal": "Planner produced persistent runtime plan",
            "steps": [
                {
                    "type": "inspect",
                    "description": "planner step one",
                    "target_file": "core/agent/agent_loop.py",
                },
                {
                    "type": "verify",
                    "description": "planner step two",
                },
            ],
            "execution_route": "generic_planner_path",
            "semantic_type": "generic_task",
        }


def read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_agent_loop_planner_runtime_dispatch_uses_planner_result(tmp_path: Path) -> None:
    planner = DummyPlanner()
    loop = AgentLoop(planner=planner, repo_root=str(tmp_path), debug=False)

    result = loop.run("Use planner runtime dispatch for Persistent Autonomous Engineering Runtime")

    assert result["ok"] is True
    assert result["mode"] == "planner_runtime_dispatch"
    assert result["agent_loop_planner_runtime_dispatch_route"] is True
    assert len(planner.calls) == 1

    dispatch = result["planner_runtime_dispatch"]
    orchestrator = result["persistent_runtime_orchestrator"]

    assert dispatch["ok"] is True
    assert dispatch["status"] == "dispatched"
    assert dispatch["task"]["persistent_runtime"] is True
    assert orchestrator["ok"] is True
    assert orchestrator["status"] == "finished"
    assert orchestrator["cycle_count"] == 1
    assert result["plan"]["persistent_runtime"] is True
    assert result["plan"]["planner_runtime_dispatch"] is True

    session_record = read_json(orchestrator["session_record_path"])
    assert session_record["status"] == "finished"


def test_agent_loop_planner_runtime_dispatch_payload_is_normalized(tmp_path: Path) -> None:
    planner = DummyPlanner()
    loop = AgentLoop(planner=planner, repo_root=str(tmp_path), debug=False)

    result = loop.run("Plan and dispatch a multi-cycle persistent runtime task")

    assert result["ok"] is True
    assert result["mode"] == "planner_runtime_dispatch"
    assert "planner runtime dispatch finished" in result["final_answer"]

    execution = result["execution"]

    assert execution["ok"] is True
    assert execution["steps_executed"] == 1
    assert execution["completed_steps"] == 1
    assert execution["results"][0]["ok"] is True
    assert execution["results"][0]["step"]["type"] == "planner_runtime_dispatch"
    assert execution["planner_runtime_dispatch"]["status"] == "dispatched"
    assert execution["persistent_runtime_orchestrator"]["status"] == "finished"
    assert execution["execution_trace"][0]["type"] == "planner_runtime_dispatch"


def test_agent_loop_planner_runtime_dispatch_helper_ignores_plain_text(tmp_path: Path) -> None:
    planner = DummyPlanner()
    loop = AgentLoop(planner=planner, repo_root=str(tmp_path), debug=False)

    candidate = loop._zero_v824_agent_try_planner_runtime_dispatch_route_for_test("hello normal short task")

    assert candidate is None
    assert planner.calls == []
