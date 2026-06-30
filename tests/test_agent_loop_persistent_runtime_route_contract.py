from __future__ import annotations

import json
from pathlib import Path

from core.agent.agent_loop import AgentLoop
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




def read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_agent_loop_routes_persistent_runtime_to_orchestrator(tmp_path: Path) -> None:
    loop = AgentLoop(repo_root=str(tmp_path), debug=False)

    result = loop.run("Persistent Autonomous Engineering Runtime final loop")

    assert result["ok"] is True
    assert result["mode"] == "persistent_runtime"
    assert result["route"]["mode"] == "persistent_runtime"
    assert result["agent_loop_persistent_runtime_route"] is True
    assert result["task"]["id"].startswith("agent_prt_")

    orchestrator = result["persistent_runtime_orchestrator"]

    assert orchestrator["ok"] is True
    assert orchestrator["status"] == "finished"
    assert orchestrator["routed"] is True
    assert orchestrator["cycle_count"] == 1
    assert orchestrator["boundary"]["does_not_modify_execution_gateway"] is True
    assert orchestrator["boundary"]["does_not_modify_step_executor"] is True

    session_record = read_json(orchestrator["session_record_path"])
    assert session_record["schema"] == "zero.aer.persistent_runtime_orchestrator.v1"
    assert session_record["status"] == "finished"


def test_agent_loop_persistent_runtime_route_keeps_execution_payload_normalized(tmp_path: Path) -> None:
    loop = AgentLoop(repo_root=str(tmp_path), debug=False)

    result = loop.run("Failure -> Recovery -> Resume persistent runtime")

    assert result["ok"] is True
    assert result["mode"] == "persistent_runtime"
    assert "persistent runtime finished" in result["final_answer"]

    execution = result["execution"]
    orchestrator = result["persistent_runtime_orchestrator"]

    assert execution["ok"] is True
    assert execution["steps_executed"] == 1
    assert execution["completed_steps"] == 1
    assert execution["results"][0]["ok"] is True
    assert execution["results"][0]["step"]["type"] == "persistent_runtime_orchestrator"
    assert execution["persistent_runtime_orchestrator"]["status"] == "finished"
    assert orchestrator["status"] == "finished"
    assert execution["execution_trace"][0]["type"] == "persistent_runtime_orchestrator"


def test_agent_loop_persistent_runtime_helper_does_not_trigger_for_plain_text(tmp_path: Path) -> None:
    loop = AgentLoop(repo_root=str(tmp_path), debug=False)

    candidate = loop._zero_v823_agent_try_persistent_runtime_route_for_test("hello normal short task")

    assert candidate is None
