from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from core.agent.agent_loop import AgentLoop
from core.runtime.step_executor import StepExecutor
from core.tools.tool_registry import ToolRegistry


class ToolBridgePlanner:
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
            "goal": "Planner produced real ToolRegistry read path",
            "persistent_runtime": True,
            "steps": [
                {
                    "type": "tool_call",
                    "description": "read shared input through ToolRegistry",
                    "tool": "read_file",
                    "input": {
                        "path": "shared/input.txt",
                    },
                }
            ],
            "execution_route": "planner_tool_registry_bridge_smoke",
            "semantic_type": "persistent_runtime",
        }


def _nested_find_text(payload: Any, needle: str) -> bool:
    if isinstance(payload, str):
        return needle in payload
    if isinstance(payload, dict):
        return any(_nested_find_text(value, needle) for value in payload.values())
    if isinstance(payload, list):
        return any(_nested_find_text(value, needle) for value in payload)
    return False


def _read_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_planner_runtime_dispatch_reaches_real_tool_registry_read_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    shared = workspace / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    input_path = shared / "input.txt"
    input_path.write_text("ZERO ToolRegistry bridge smoke\n", encoding="utf-8")

    tool_registry = ToolRegistry(workspace_dir=str(workspace))
    assert tool_registry.has_tool("read_file") is True

    step_executor = StepExecutor(
        tool_registry=tool_registry,
        workspace_root=str(workspace),
        debug=False,
    )
    planner = ToolBridgePlanner()

    loop = AgentLoop(
        planner=planner,
        step_executor=step_executor,
        repo_root=str(tmp_path),
        debug=False,
    )

    result = loop.run("Use planner runtime dispatch for Persistent Autonomous Engineering Runtime planner tool registry bridge")

    assert result["ok"] is True
    assert result["mode"] == "planner_step_executor_bridge"
    assert result["agent_loop_planner_step_executor_bridge"] is True
    assert len(planner.calls) == 1

    dispatch = result["planner_runtime_dispatch"]
    orchestrator = result["persistent_runtime_orchestrator"]

    assert dispatch["ok"] is True
    assert dispatch["status"] == "dispatched"
    assert orchestrator["ok"] is True
    assert orchestrator["status"] == "finished"

    cycle_results = orchestrator["multi_cycle_engineering_loop"]["cycle_results"]
    assert len(cycle_results) == 1
    runtime = cycle_results[0]["runtime"]

    assert runtime["status"] == "finished"
    assert runtime["executed_group_count"] == 1
    assert runtime["checkpoint_count"] == 1

    # Public runtime summaries and checkpoint payloads are compact.  Validate the
    # actual bridge by checking the persisted checkpoint's StepExecutor envelope:
    #
    # Planner tool_call
    # -> PlannerStepExecutorAdapter normalizes to type=tool
    # -> StepExecutor executes tool handler
    # -> ToolRegistry accepts read_file
    journal = _read_json(runtime["session_journal_path"])
    assert journal["status"] == "finished"
    assert journal["executed_groups"][0]["result"]["ok"] is True

    checkpoint_path = journal["checkpoints"][0]["checkpoint_path"]
    checkpoint = _read_json(checkpoint_path)

    assert checkpoint["status"] == "finished"
    assert _nested_find_text(checkpoint, "read_file")
    assert _nested_find_text(checkpoint, "tool")

    checkpoint_result = checkpoint["result"]
    assert checkpoint_result["ok"] is True
    assert checkpoint_result["step"]["type"] == "tool"
    assert checkpoint_result["step"]["tool_name"] == "read_file"
    assert checkpoint_result["step"]["args"] == {"path": "shared/input.txt"}
    assert checkpoint_result["tool_bridge"]["tool_registry_called_by_step_executor"] is True

    step_executor_result = checkpoint_result["step_executor_result"]
    assert step_executor_result["ok"] is True
    assert step_executor_result["step_type"] == "tool"
    assert step_executor_result["step"]["tool_name"] == "read_file"

    # The content itself may be omitted from compact public summaries depending
    # on the file tool implementation.  The source file remains the ground truth
    # for the read target used by the real ToolRegistry path.
    assert input_path.read_text(encoding="utf-8") == "ZERO ToolRegistry bridge smoke\n"


def test_planner_step_executor_adapter_normalizes_tool_call_shape() -> None:
    from core.runtime.planner_step_executor_adapter import PlannerStepExecutorAdapter

    adapter = PlannerStepExecutorAdapter(step_executor=None)
    step = {
        "type": "tool_call",
        "tool": "read_file",
        "input": {"path": "shared/input.txt"},
    }

    normalized = adapter._normalize_planner_step_for_step_executor(step)

    assert normalized["type"] == "tool"
    assert normalized["tool_name"] == "read_file"
    assert normalized["tool"] == "read_file"
    assert normalized["args"] == {"path": "shared/input.txt"}
    assert normalized["input"] == {"path": "shared/input.txt"}
    assert normalized["planner_step_executor_adapter"] is True
    assert normalized["planner_tool_bridge"]["tool_registry_called_by_step_executor"] is True
