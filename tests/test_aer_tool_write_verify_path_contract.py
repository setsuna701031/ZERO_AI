from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from core.agent.agent_loop import AgentLoop
from core.runtime.step_executor import StepExecutor
from core.tools.tool_registry import ToolRegistry


class ToolWriteVerifyPlanner:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

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
            "goal": "Planner produced ToolRegistry read/write/verify path",
            "persistent_runtime": True,
            "steps": [
                {
                    "type": "tool_call",
                    "description": "read shared source through ToolRegistry",
                    "tool": "read_file",
                    "input": {
                        "path": "shared/source.txt",
                    },
                },
                {
                    "type": "tool_call",
                    "description": "write transformed output through ToolRegistry",
                    "tool": "write_file",
                    "input": {
                        "path": "shared/output.txt",
                        "content": "ZERO ToolRegistry write verify smoke\n",
                        "allow_overwrite": True,
                    },
                },
                {
                    "type": "tool_call",
                    "description": "read written output through ToolRegistry",
                    "tool": "read_file",
                    "input": {
                        "path": "shared/output.txt",
                    },
                },
            ],
            "execution_route": "planner_tool_registry_write_verify_path",
            "semantic_type": "persistent_runtime",
        }


def _read_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _checkpoint_results(runtime: Dict[str, Any]) -> List[Dict[str, Any]]:
    journal = _read_json(runtime["session_journal_path"])
    return [_read_json(checkpoint["checkpoint_path"]) for checkpoint in journal["checkpoints"]]


def test_planner_tool_registry_read_write_verify_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    shared = workspace / "shared"
    shared.mkdir(parents=True, exist_ok=True)

    source_path = shared / "source.txt"
    output_path = shared / "output.txt"
    source_path.write_text("ZERO ToolRegistry source\n", encoding="utf-8")

    tool_registry = ToolRegistry(workspace_dir=str(workspace))
    assert tool_registry.has_tool("read_file") is True
    assert tool_registry.has_tool("write_file") is True

    step_executor = StepExecutor(
        tool_registry=tool_registry,
        workspace_root=str(workspace),
        debug=False,
    )
    planner = ToolWriteVerifyPlanner()

    loop = AgentLoop(
        planner=planner,
        step_executor=step_executor,
        repo_root=str(tmp_path),
        debug=False,
    )

    result = loop.run("Use planner runtime dispatch for Persistent Autonomous Engineering Runtime tool write verify path")

    assert result["ok"] is False
    assert result["mode"] == "planner_step_executor_bridge"
    assert result["agent_loop_planner_step_executor_bridge"] is True
    assert len(planner.calls) == 1

    dispatch = result["planner_runtime_dispatch"]
    orchestrator = result["persistent_runtime_orchestrator"]

    assert dispatch["ok"] is False
    assert orchestrator["ok"] is False
    assert orchestrator["status"] != "finished"
    assert not output_path.exists()


def test_planner_step_executor_adapter_tool_input_compatibility() -> None:
    from core.runtime.planner_step_executor_adapter import PlannerStepExecutorAdapter

    adapter = PlannerStepExecutorAdapter(step_executor=None)
    step = {
        "type": "tool_call",
        "tool": "write_file",
        "input": {
            "path": "shared/output.txt",
            "content": "hello",
            "allow_overwrite": True,
        },
    }

    normalized = adapter._normalize_planner_step_for_step_executor(step)

    assert normalized["type"] == "tool"
    assert normalized["tool_name"] == "write_file"
    assert normalized["tool"] == "write_file"
    assert normalized["tool_input"] == {
        "path": "shared/output.txt",
        "content": "hello",
        "allow_overwrite": True,
    }
    assert normalized["args"] == normalized["tool_input"]
    assert normalized["input"] == normalized["tool_input"]
    assert normalized["planner_tool_bridge"]["tool_input_compatibility"] is True
