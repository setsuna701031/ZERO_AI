from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from core.agent.agent_loop import AgentLoop
from core.runtime.step_executor import StepExecutor
from core.tools.tool_registry import ToolRegistry
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




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
                        "target_path": "shared/fixed_module_b.py",
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
    multi = orchestrator["multi_cycle_engineering_loop"]
    runtime = multi["cycle_results"][0]["runtime"]

    assert dispatch["ok"] is True
    assert dispatch["status"] == "dispatched"
    assert orchestrator["ok"] is True
    assert orchestrator["status"] == "completed"
    assert multi["executed_group_count"] == 8
    assert runtime["executed_group_count"] == 8
    assert runtime["plan_group_count"] == 8
    assert runtime["failure_count"] == 0
    assert runtime["recoverable"] is False

    checkpoints = _checkpoint_results(runtime)
    assert len(checkpoints) == 8
    step_results = [checkpoint["result"]["step_executor_result"] for checkpoint in checkpoints]
    assert all(step_result["ok"] is True for step_result in step_results)
    assert all(step_result["execution_path"]["runtime_owns_execution"] is True for step_result in step_results)
    assert all(step_result["execution_path"]["taskrunner_required"] is True for step_result in step_results)
    assert all(step_result["execution_path"]["step_executor_endpoint_only"] is True for step_result in step_results)

    authority_contexts = [
        step_result["input"]["context"]["authority_context"]
        for step_result in step_results
    ]
    assert all(context["authority_source"] == "runtime_dispatcher" for context in authority_contexts)
    assert all(context["authority_policy"] == "owner_issued_runtime_execution_capability" for context in authority_contexts)
    assert all(context["authority_propagation_required"] is True for context in authority_contexts)
    assert all(context["can_execute_privileged_step"] is True for context in authority_contexts)
    assert all("RuntimeExecutionCapability(" in str(context["runtime_execution_capability"]) for context in authority_contexts)
    execution_authorities = [
        step_result["input"]["context"]["execution_authority"]
        for step_result in step_results
    ]
    assert all(authority["authority_source"] == "runtime_dispatcher" for authority in execution_authorities)
    assert all(authority["authority_status"] == "allowed" for authority in execution_authorities)
    assert all(step_result.get("error") is None for step_result in step_results)
    assert all(step_result.get("task_completion_authority") is None for step_result in step_results)

    assert fixed_a.exists()
    assert fixed_b.exists()
    assert summary.exists()
    assert _load_module_namespace(fixed_a)["add"](2, 3) == 5
    assert _load_module_namespace(fixed_b)["multiply"](2, 3) == 6
    summary_text = summary.read_text(encoding="utf-8")
    assert "fixed_module_a.py" in summary_text
    assert "fixed_module_b.py" in summary_text
    assert "Planner -> Runtime -> StepExecutor -> ToolRegistry" in summary_text


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

    assert result["ok"] is False

    orchestrator = result["persistent_runtime_orchestrator"]
    multi = orchestrator["multi_cycle_engineering_loop"]

    assert multi["closure_count"] == 1

    failed_cycle = multi["cycle_results"][0]
    closure = multi["closure_results"][0]["closure"]

    assert failed_cycle["runtime"]["status"] == "recoverable_failure"
    assert closure["status"] == "closed"
    assert closure["ok"] is True


def test_aer_multifile_engineering_workflow_rejects_shared_path_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    shared = workspace / "shared"
    shared.mkdir(parents=True, exist_ok=True)

    class EscapingPlanner(MultiFileEngineeringPlanner):
        def plan(self, context=None, user_input="", route=None, **kwargs):
            plan = super().plan(context=context, user_input=user_input, route=route, **kwargs)
            plan["steps"] = [
                {
                    "type": "tool_call",
                    "description": "attempt shared path escape",
                    "tool": "write_file",
                    "input": {
                        "target_path": "../escaped.py",
                        "content": "escaped = True\n",
                        "allow_overwrite": True,
                    },
                }
            ]
            return plan

    loop = AgentLoop(
        planner=EscapingPlanner(),
        step_executor=StepExecutor(
            tool_registry=ToolRegistry(workspace_dir=str(workspace)),
            workspace_root=str(workspace),
            debug=False,
        ),
        repo_root=str(tmp_path),
        debug=False,
    )

    result = loop.run(
        "Use planner runtime dispatch for Persistent Autonomous Engineering Runtime multi-file engineering workflow"
    )

    runtime = result["persistent_runtime_orchestrator"]["multi_cycle_engineering_loop"]["cycle_results"][0]["runtime"]
    assert runtime["status"] == "recoverable_failure"
    assert not (tmp_path / "escaped.py").exists()
    assert not (workspace / "escaped.py").exists()
