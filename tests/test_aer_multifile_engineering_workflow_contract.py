from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from core.agent.agent_loop import AgentLoop
from core.runtime.step_executor import StepExecutor
from core.tools.tool_registry import ToolRegistry


class MultiFileEngineeringPlanner:
    """Planner emits a real multi-file engineering workflow through ToolRegistry.

    Workflow:
      read module_a.py
      read module_b.py
      write fixed module_a.py
      write fixed module_b.py
      write README summary
      read back all generated files for verification
    """

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
            "goal": "Planner produced multi-file engineering workflow through ToolRegistry",
            "persistent_runtime": True,
            "steps": [
                {
                    "type": "tool_call",
                    "description": "read module A source through ToolRegistry",
                    "tool": "read_file",
                    "input": {"path": "shared/module_a.py"},
                },
                {
                    "type": "tool_call",
                    "description": "read module B source through ToolRegistry",
                    "tool": "read_file",
                    "input": {"path": "shared/module_b.py"},
                },
                {
                    "type": "tool_call",
                    "description": "write fixed module A through ToolRegistry",
                    "tool": "write_file",
                    "input": {
                        "path": "shared/fixed_module_a.py",
                        "content": "def add(a, b):\n    return a + b\n",
                        "allow_overwrite": True,
                    },
                },
                {
                    "type": "tool_call",
                    "description": "write fixed module B through ToolRegistry",
                    "tool": "write_file",
                    "input": {
                        "path": "shared/fixed_module_b.py",
                        "content": "def multiply(a, b):\n    return a * b\n",
                        "allow_overwrite": True,
                    },
                },
                {
                    "type": "tool_call",
                    "description": "write engineering summary artifact through ToolRegistry",
                    "tool": "write_file",
                    "input": {
                        "path": "shared/engineering_multifile_summary.md",
                        "content": (
                            "# AER Multi-File Engineering Workflow\n\n"
                            "- fixed_module_a.py: add(a, b) uses addition\n"
                            "- fixed_module_b.py: multiply(a, b) uses multiplication\n"
                            "- runtime_path: Planner -> Runtime -> StepExecutor -> ToolRegistry\n"
                        ),
                        "allow_overwrite": True,
                    },
                },
                {
                    "type": "tool_call",
                    "description": "read fixed module A for verification",
                    "tool": "read_file",
                    "input": {"path": "shared/fixed_module_a.py"},
                },
                {
                    "type": "tool_call",
                    "description": "read fixed module B for verification",
                    "tool": "read_file",
                    "input": {"path": "shared/fixed_module_b.py"},
                },
                {
                    "type": "tool_call",
                    "description": "read engineering summary artifact for verification",
                    "tool": "read_file",
                    "input": {"path": "shared/engineering_multifile_summary.md"},
                },
            ],
            "execution_route": "planner_multifile_engineering_workflow",
            "semantic_type": "persistent_runtime",
        }


def _read_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _checkpoint_results(runtime: Dict[str, Any]) -> List[Dict[str, Any]]:
    journal = _read_json(runtime["session_journal_path"])
    return [_read_json(checkpoint["checkpoint_path"]) for checkpoint in journal["checkpoints"]]


def _load_module_namespace(path: Path) -> Dict[str, Any]:
    namespace: Dict[str, Any] = {}
    exec(path.read_text(encoding="utf-8"), namespace)
    return namespace


def test_aer_multifile_engineering_workflow_read_write_verify_artifact(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    shared = workspace / "shared"
    shared.mkdir(parents=True, exist_ok=True)

    module_a = shared / "module_a.py"
    module_b = shared / "module_b.py"
    fixed_a = shared / "fixed_module_a.py"
    fixed_b = shared / "fixed_module_b.py"
    summary = shared / "engineering_multifile_summary.md"

    module_a.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    module_b.write_text("def multiply(a, b):\n    return a + b\n", encoding="utf-8")

    tool_registry = ToolRegistry(workspace_dir=str(workspace))
    assert tool_registry.has_tool("read_file") is True
    assert tool_registry.has_tool("write_file") is True

    step_executor = StepExecutor(
        tool_registry=tool_registry,
        workspace_root=str(workspace),
        debug=False,
    )
    planner = MultiFileEngineeringPlanner()

    loop = AgentLoop(
        planner=planner,
        step_executor=step_executor,
        repo_root=str(tmp_path),
        debug=False,
    )

    result = loop.run(
        "Use planner runtime dispatch for Persistent Autonomous Engineering Runtime multi-file engineering workflow"
    )

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

    assert fixed_a.exists()
    assert fixed_b.exists()
    assert summary.exists()

    namespace_a = _load_module_namespace(fixed_a)
    namespace_b = _load_module_namespace(fixed_b)

    assert namespace_a["add"](2, 3) == 5
    assert namespace_b["multiply"](2, 3) == 6

    summary_text = summary.read_text(encoding="utf-8")
    assert "AER Multi-File Engineering Workflow" in summary_text
    assert "Planner -> Runtime -> StepExecutor -> ToolRegistry" in summary_text

    cycle_results = orchestrator["multi_cycle_engineering_loop"]["cycle_results"]
    assert len(cycle_results) == 1
    runtime = cycle_results[0]["runtime"]

    assert runtime["status"] == "finished"
    assert runtime["executed_group_count"] == 8
    assert runtime["checkpoint_count"] == 8

    checkpoints = _checkpoint_results(runtime)
    assert len(checkpoints) == 8

    steps = [checkpoint["result"]["step"] for checkpoint in checkpoints]
    assert [step["type"] for step in steps] == ["tool"] * 8
    assert [step["tool_name"] for step in steps] == [
        "read_file",
        "read_file",
        "write_file",
        "write_file",
        "write_file",
        "read_file",
        "read_file",
        "read_file",
    ]

    assert all(step["planner_step_executor_adapter"] is True for step in steps)
    assert all("tool_input" in step for step in steps)

    for checkpoint in checkpoints:
        assert checkpoint["result"]["ok"] is True
        assert checkpoint["result"]["step_executor_result"]["ok"] is True


def test_aer_multifile_engineering_workflow_write_failure_recovers(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    shared = workspace / "shared"
    shared.mkdir(parents=True, exist_ok=True)

    (shared / "module_a.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (shared / "module_b.py").write_text("def multiply(a, b):\n    return a + b\n", encoding="utf-8")

    class FailingMultiFilePlanner(MultiFileEngineeringPlanner):
        def plan(self, context=None, user_input="", route=None, **kwargs):
            plan = super().plan(context=context, user_input=user_input, route=route, **kwargs)
            plan["steps"][3]["tool"] = "missing_write_tool_for_recovery"
            return plan

    tool_registry = ToolRegistry(workspace_dir=str(workspace))
    step_executor = StepExecutor(
        tool_registry=tool_registry,
        workspace_root=str(workspace),
        debug=False,
    )
    planner = FailingMultiFilePlanner()

    loop = AgentLoop(
        planner=planner,
        step_executor=step_executor,
        repo_root=str(tmp_path),
        debug=False,
    )

    result = loop.run(
        "Use planner runtime dispatch for Persistent Autonomous Engineering Runtime multi-file engineering workflow"
    )

    assert result["ok"] is True

    orchestrator = result["persistent_runtime_orchestrator"]
    multi = orchestrator["multi_cycle_engineering_loop"]

    assert multi["closure_count"] == 1

    failed_cycle = multi["cycle_results"][0]
    closure = multi["closure_results"][0]["closure"]

    assert failed_cycle["runtime"]["status"] == "recoverable_failure"
    assert closure["status"] == "closed"
    assert closure["ok"] is True
