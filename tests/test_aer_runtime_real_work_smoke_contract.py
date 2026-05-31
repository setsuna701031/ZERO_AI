from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from core.agent.agent_loop import AgentLoop


class RealWorkPlanner:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
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

        source_path = self.workspace / "input.txt"
        output_path = self.workspace / "output.txt"

        return {
            "ok": True,
            "goal": "Planner produced real read/write/verify runtime work",
            "persistent_runtime": True,
            "steps": [
                {
                    "type": "read_file",
                    "description": "read real input file",
                    "path": str(source_path),
                },
                {
                    "type": "write_file",
                    "description": "write real output file",
                    "path": str(output_path),
                    "content": "ZERO real work smoke output\n",
                },
                {
                    "type": "verify_file_contains",
                    "description": "verify real output file content",
                    "path": str(output_path),
                    "contains": "ZERO real work smoke output",
                },
            ],
            "execution_route": "planner_runtime_real_work_smoke",
            "semantic_type": "persistent_runtime",
        }


class RealWorkStepExecutor:
    """Minimal real side-effect executor used only by this contract test.

    This is intentionally a test StepExecutor implementation.  It proves that
    the production AgentLoop -> PlannerRuntimeDispatch -> LongEngineeringRuntime
    -> PlannerStepExecutorAdapter path can carry planner steps into an actual
    StepExecutor endpoint that performs read / write / verify work.
    """

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.last_read_text = ""

    def execute(self, step=None, task=None, context=None, previous_result=None, step_index=None, step_count=None, **kwargs):
        step = step if isinstance(step, dict) else {}
        context = context if isinstance(context, dict) else {}
        step_type = str(step.get("type") or "").strip()

        self.calls.append(
            {
                "step": dict(step),
                "task": dict(task) if isinstance(task, dict) else {},
                "context": dict(context),
                "step_index": step_index,
                "step_count": step_count,
            }
        )

        if step_type == "read_file":
            path = Path(str(step.get("path") or ""))
            text = path.read_text(encoding="utf-8")
            self.last_read_text = text
            return {
                "ok": True,
                "status": "finished",
                "operation": "read_file",
                "path": str(path),
                "text": text,
                "planner_step_executor_adapter": bool(step.get("planner_step_executor_adapter")),
            }

        if step_type == "write_file":
            path = Path(str(step.get("path") or ""))
            path.parent.mkdir(parents=True, exist_ok=True)
            content = str(step.get("content") or "")
            path.write_text(content, encoding="utf-8")
            return {
                "ok": True,
                "status": "finished",
                "operation": "write_file",
                "path": str(path),
                "bytes_written": len(content.encode("utf-8")),
                "planner_step_executor_adapter": bool(step.get("planner_step_executor_adapter")),
            }

        if step_type == "verify_file_contains":
            path = Path(str(step.get("path") or ""))
            expected = str(step.get("contains") or "")
            text = path.read_text(encoding="utf-8")
            ok = expected in text
            return {
                "ok": ok,
                "status": "finished" if ok else "failed",
                "operation": "verify_file_contains",
                "path": str(path),
                "contains": expected,
                "planner_step_executor_adapter": bool(step.get("planner_step_executor_adapter")),
                "error": None if ok else f"missing expected content: {expected}",
            }

        return {
            "ok": False,
            "status": "unsupported_step_type",
            "operation": step_type,
            "error": f"unsupported step type: {step_type}",
        }


def test_aer_runtime_real_work_read_write_verify_smoke(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace" / "shared"
    workspace.mkdir(parents=True, exist_ok=True)
    input_path = workspace / "input.txt"
    output_path = workspace / "output.txt"
    input_path.write_text("ZERO real work smoke input\n", encoding="utf-8")

    planner = RealWorkPlanner(workspace=workspace)
    step_executor = RealWorkStepExecutor()
    loop = AgentLoop(
        planner=planner,
        step_executor=step_executor,
        repo_root=str(tmp_path),
        debug=False,
    )

    result = loop.run("Use planner runtime dispatch for Persistent Autonomous Engineering Runtime real work smoke")

    assert result["ok"] is True
    assert result["mode"] == "planner_step_executor_bridge"
    assert result["agent_loop_planner_step_executor_bridge"] is True

    dispatch = result["planner_runtime_dispatch"]
    orchestrator = result["persistent_runtime_orchestrator"]

    assert dispatch["ok"] is True
    assert dispatch["status"] == "dispatched"
    assert orchestrator["ok"] is True
    assert orchestrator["status"] == "finished"

    # The real-work planner produced three steps; the bridge must deliver all
    # three to the StepExecutor endpoint through LongEngineeringRuntime groups.
    assert len(planner.calls) == 1
    assert len(step_executor.calls) == 3

    assert [call["step"]["type"] for call in step_executor.calls] == [
        "read_file",
        "write_file",
        "verify_file_contains",
    ]

    assert all(call["step"]["planner_step_executor_adapter"] is True for call in step_executor.calls)
    assert all(call["context"]["planner_step_executor_adapter"] is True for call in step_executor.calls)

    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == "ZERO real work smoke output\n"

    cycle_results = orchestrator["multi_cycle_engineering_loop"]["cycle_results"]
    assert len(cycle_results) == 1
    runtime = cycle_results[0]["runtime"]
    assert runtime["status"] == "finished"
    assert runtime["executed_group_count"] == 3
    assert runtime["checkpoint_count"] == 3


def test_aer_runtime_real_work_failure_creates_recoverable_runtime(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace" / "shared"
    workspace.mkdir(parents=True, exist_ok=True)

    class FailingPlanner(RealWorkPlanner):
        def plan(self, context=None, user_input="", route=None, **kwargs):
            plan = super().plan(context=context, user_input=user_input, route=route, **kwargs)
            plan["steps"][2]["contains"] = "missing expected text"
            return plan

    planner = FailingPlanner(workspace=workspace)
    step_executor = RealWorkStepExecutor()
    (workspace / "input.txt").write_text("ZERO real work smoke input\n", encoding="utf-8")

    loop = AgentLoop(
        planner=planner,
        step_executor=step_executor,
        repo_root=str(tmp_path),
        debug=False,
    )

    result = loop.run("Use planner runtime dispatch for Persistent Autonomous Engineering Runtime real work smoke")

    # The multi-cycle layer closes recoverable failures by creating a resume
    # session.  The outer dispatch remains ok only if recovery closure succeeds.
    assert result["ok"] is True
    orchestrator = result["persistent_runtime_orchestrator"]
    multi = orchestrator["multi_cycle_engineering_loop"]

    assert multi["closure_count"] == 1
    failed_cycle = multi["cycle_results"][0]
    closure = multi["closure_results"][0]["closure"]

    assert failed_cycle["runtime"]["status"] == "recoverable_failure"
    assert closure["status"] == "closed"
    assert closure["ok"] is True
    assert len(step_executor.calls) >= 3
