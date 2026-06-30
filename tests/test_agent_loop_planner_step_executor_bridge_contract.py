from __future__ import annotations

from pathlib import Path

from core.agent.agent_loop import AgentLoop
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




class DummyPlanner:
    def __init__(self) -> None:
        self.calls = []

    def plan(self, context=None, user_input="", route=None, **kwargs):
        self.calls.append({"context": context, "user_input": user_input, "route": route})
        return {
            "ok": True,
            "goal": "Planner produced executable runtime plan",
            "steps": [
                {
                    "type": "dummy_exec",
                    "description": "execute planner step one",
                    "payload": {"value": 1},
                },
            ],
            "execution_route": "generic_planner_path",
            "semantic_type": "generic_task",
        }


class DummyStepExecutor:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, step=None, task=None, context=None, previous_result=None, step_index=None, step_count=None, **kwargs):
        self.calls.append(
            {
                "step": step,
                "task": task,
                "context": context,
                "step_index": step_index,
                "step_count": step_count,
            }
        )
        return {
            "ok": True,
            "status": "finished",
            "message": "dummy step executor finished",
            "step_type": step.get("type") if isinstance(step, dict) else "",
            "received_adapter": bool(step.get("planner_step_executor_adapter")) if isinstance(step, dict) else False,
        }


def test_agent_loop_planner_dispatch_calls_step_executor_adapter(tmp_path: Path) -> None:
    planner = DummyPlanner()
    step_executor = DummyStepExecutor()
    loop = AgentLoop(
        planner=planner,
        step_executor=step_executor,
        repo_root=str(tmp_path),
        debug=False,
    )

    result = loop.run("Use planner runtime dispatch for Persistent Autonomous Engineering Runtime")

    assert result["ok"] is True
    assert result["mode"] == "planner_step_executor_bridge"
    assert result["agent_loop_planner_step_executor_bridge"] is True
    assert len(planner.calls) == 1
    assert len(step_executor.calls) == 1

    call = step_executor.calls[0]
    assert call["step"]["type"] == "dummy_exec"
    assert call["step"]["planner_step_executor_adapter"] is True
    assert call["context"]["planner_step_executor_adapter"] is True

    dispatch = result["planner_runtime_dispatch"]
    orchestrator = result["persistent_runtime_orchestrator"]

    assert dispatch["ok"] is True
    assert dispatch["status"] == "dispatched"
    assert orchestrator["ok"] is True
    assert orchestrator["status"] == "completed"
    assert orchestrator["cycle_count"] == 1


def test_agent_loop_planner_step_executor_bridge_ignores_plain_text(tmp_path: Path) -> None:
    planner = DummyPlanner()
    step_executor = DummyStepExecutor()
    loop = AgentLoop(
        planner=planner,
        step_executor=step_executor,
        repo_root=str(tmp_path),
        debug=False,
    )

    candidate = loop._zero_v825_agent_try_planner_runtime_dispatch_route_for_test("hello normal short task")

    assert candidate is None
    assert planner.calls == []
    assert step_executor.calls == []
