from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from core.agent.agent_loop import AgentLoop
from core.runtime.runtime_dispatcher import RuntimeDispatcher
from core.runtime.step_executor import StepExecutor
from core.tools.tool_registry import ToolRegistry
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_fast]




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

    assert callable(RuntimeDispatcher.dispatch)
    assert dispatch["ok"] is True
    assert dispatch["status"] == "dispatched"
    assert orchestrator["ok"] is True
    assert orchestrator["status"] == "completed"

    runtime = orchestrator["multi_cycle_engineering_loop"]["cycle_results"][0]["runtime"]
    checkpoint_result = runtime["latest_checkpoint"]["result"]
    step_result = checkpoint_result["step_executor_result"]
    authority_context = step_result["input"]["context"]["authority_context"]
    execution_path = step_result["execution_path"]

    assert step_result["ok"] is True
    assert step_result["tool"] == "read_file"
    assert step_result["output"]["content"] == "ZERO ToolRegistry bridge smoke\n"
    assert execution_path["runtime_owns_execution"] is True
    assert execution_path["taskrunner_required"] is True
    assert execution_path["step_executor_endpoint_only"] is True
    assert authority_context["authority_source"] == "runtime_dispatcher"
    assert authority_context["authority_policy"] == "owner_issued_runtime_execution_capability"
    assert "RuntimeExecutionCapability(" in str(authority_context["runtime_execution_capability"])
    assert "delegated=True" in str(authority_context["runtime_execution_capability"])
    assert _nested_find_text(result, "runtime_dispatcher")
    assert _nested_find_text(result, "owner_issued_runtime_execution_capability")

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
