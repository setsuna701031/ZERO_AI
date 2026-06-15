from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from core.agent.agent_loop import AgentLoop


class EngineeringChainPlanner:
    """Planner that emits a real engineering chain.

    Chain:
      read source -> analyze -> modify/write -> verify -> artifact summary
    """

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

        source_path = self.workspace / "buggy_math.py"
        output_path = self.workspace / "fixed_math.py"
        artifact_path = self.workspace / "engineering_summary.md"

        return {
            "ok": True,
            "goal": "Planner produced real engineering task chain",
            "persistent_runtime": True,
            "steps": [
                {
                    "type": "read_file",
                    "description": "read source file",
                    "path": str(source_path),
                },
                {
                    "type": "analyze_python_math_bug",
                    "description": "analyze deterministic math bug",
                    "source_path": str(source_path),
                },
                {
                    "type": "write_fixed_python_file",
                    "description": "write fixed Python file",
                    "source_path": str(source_path),
                    "output_path": str(output_path),
                    "replace": {
                        "old": "return a - b",
                        "new": "return a + b",
                    },
                },
                {
                    "type": "verify_python_function_result",
                    "description": "verify add(2, 3) result",
                    "path": str(output_path),
                    "function": "add",
                    "args": [2, 3],
                    "expected": 5,
                },
                {
                    "type": "write_engineering_artifact",
                    "description": "write engineering summary artifact",
                    "path": str(artifact_path),
                    "title": "AER Engineering Task Chain Smoke",
                },
            ],
            "execution_route": "planner_engineering_task_chain_smoke",
            "semantic_type": "persistent_runtime",
        }


class EngineeringChainStepExecutor:
    """Test StepExecutor that performs a real read/analyze/modify/verify/artifact chain."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.memory: Dict[str, Any] = {}

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
            self.memory["last_read_path"] = str(path)
            self.memory["last_read_text"] = text
            return {
                "ok": True,
                "status": "finished",
                "operation": "read_file",
                "path": str(path),
                "text": text,
                "planner_step_executor_adapter": bool(step.get("planner_step_executor_adapter")),
            }

        if step_type == "analyze_python_math_bug":
            source_path = Path(str(step.get("source_path") or ""))
            text = source_path.read_text(encoding="utf-8")
            bug_found = "return a - b" in text
            self.memory["analysis"] = {
                "bug_found": bug_found,
                "source_path": str(source_path),
                "reason": "add uses subtraction" if bug_found else "no known deterministic bug found",
            }
            return {
                "ok": bug_found,
                "status": "finished" if bug_found else "failed",
                "operation": "analyze_python_math_bug",
                "bug_found": bug_found,
                "reason": self.memory["analysis"]["reason"],
                "planner_step_executor_adapter": bool(step.get("planner_step_executor_adapter")),
            }

        if step_type == "write_fixed_python_file":
            source_path = Path(str(step.get("source_path") or ""))
            output_path = Path(str(step.get("output_path") or ""))
            replacement = step.get("replace") if isinstance(step.get("replace"), dict) else {}
            old = str(replacement.get("old") or "")
            new = str(replacement.get("new") or "")
            text = source_path.read_text(encoding="utf-8")
            if old not in text:
                return {
                    "ok": False,
                    "status": "failed",
                    "operation": "write_fixed_python_file",
                    "error": f"old text not found: {old}",
                }
            fixed = text.replace(old, new, 1)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(fixed, encoding="utf-8")
            self.memory["fixed_path"] = str(output_path)
            return {
                "ok": True,
                "status": "finished",
                "operation": "write_fixed_python_file",
                "source_path": str(source_path),
                "output_path": str(output_path),
                "changed": True,
                "planner_step_executor_adapter": bool(step.get("planner_step_executor_adapter")),
            }

        if step_type == "verify_python_function_result":
            path = Path(str(step.get("path") or ""))
            function = str(step.get("function") or "")
            args = list(step.get("args") or [])
            expected = step.get("expected")
            namespace: Dict[str, Any] = {}
            exec(path.read_text(encoding="utf-8"), namespace)
            actual = namespace[function](*args)
            ok = actual == expected
            self.memory["verification"] = {
                "path": str(path),
                "function": function,
                "args": args,
                "expected": expected,
                "actual": actual,
                "ok": ok,
            }
            return {
                "ok": ok,
                "status": "finished" if ok else "failed",
                "operation": "verify_python_function_result",
                "actual": actual,
                "expected": expected,
                "planner_step_executor_adapter": bool(step.get("planner_step_executor_adapter")),
                "error": None if ok else f"expected {expected}, got {actual}",
            }

        if step_type == "write_engineering_artifact":
            path = Path(str(step.get("path") or ""))
            path.parent.mkdir(parents=True, exist_ok=True)
            verification = self.memory.get("verification", {})
            content = (
                f"# {step.get('title')}\n\n"
                "## Result\n\n"
                f"- verification_ok: {verification.get('ok')}\n"
                f"- expected: {verification.get('expected')}\n"
                f"- actual: {verification.get('actual')}\n"
                f"- fixed_path: {self.memory.get('fixed_path')}\n"
            )
            path.write_text(content, encoding="utf-8")
            self.memory["artifact_path"] = str(path)
            return {
                "ok": True,
                "status": "finished",
                "operation": "write_engineering_artifact",
                "path": str(path),
                "planner_step_executor_adapter": bool(step.get("planner_step_executor_adapter")),
            }

        return {
            "ok": False,
            "status": "unsupported_step_type",
            "operation": step_type,
            "error": f"unsupported step type: {step_type}",
        }


def test_aer_engineering_task_chain_read_analyze_modify_verify_artifact(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace" / "shared"
    workspace.mkdir(parents=True, exist_ok=True)

    source_path = workspace / "buggy_math.py"
    fixed_path = workspace / "fixed_math.py"
    artifact_path = workspace / "engineering_summary.md"

    source_path.write_text(
        "def add(a, b):\n"
        "    return a - b\n",
        encoding="utf-8",
    )

    planner = EngineeringChainPlanner(workspace=workspace)
    step_executor = EngineeringChainStepExecutor()
    loop = AgentLoop(
        planner=planner,
        step_executor=step_executor,
        repo_root=str(tmp_path),
        debug=False,
    )

    result = loop.run("Use planner runtime dispatch for Persistent Autonomous Engineering Runtime engineering task chain")

    assert result["ok"] is True
    assert result["mode"] == "planner_step_executor_bridge"
    assert result["agent_loop_planner_step_executor_bridge"] is True

    dispatch = result["planner_runtime_dispatch"]
    orchestrator = result["persistent_runtime_orchestrator"]

    assert dispatch["ok"] is True
    assert dispatch["status"] == "dispatched"
    assert orchestrator["ok"] is True
    assert orchestrator["status"] == "finished"

    assert len(planner.calls) == 1
    assert len(step_executor.calls) == 5

    assert [call["step"]["type"] for call in step_executor.calls] == [
        "read_file",
        "analyze_python_math_bug",
        "write_fixed_python_file",
        "verify_python_function_result",
        "write_engineering_artifact",
    ]

    assert all(call["step"]["planner_step_executor_adapter"] is True for call in step_executor.calls)
    assert all(call["context"]["planner_step_executor_adapter"] is True for call in step_executor.calls)

    assert fixed_path.exists()
    assert "return a + b" in fixed_path.read_text(encoding="utf-8")

    namespace: Dict[str, Any] = {}
    exec(fixed_path.read_text(encoding="utf-8"), namespace)
    assert namespace["add"](2, 3) == 5

    assert artifact_path.exists()
    artifact_text = artifact_path.read_text(encoding="utf-8")
    assert "verification_ok: True" in artifact_text
    assert "actual: 5" in artifact_text

    cycle_results = orchestrator["multi_cycle_engineering_loop"]["cycle_results"]
    assert len(cycle_results) == 1
    runtime = cycle_results[0]["runtime"]
    assert runtime["status"] == "finished"
    assert runtime["executed_group_count"] == 5
    assert runtime["checkpoint_count"] == 5


def test_aer_engineering_task_chain_verify_failure_recovery_closure(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace" / "shared"
    workspace.mkdir(parents=True, exist_ok=True)

    source_path = workspace / "buggy_math.py"
    source_path.write_text(
        "def add(a, b):\n"
        "    return a - b\n",
        encoding="utf-8",
    )

    class FailingEngineeringPlanner(EngineeringChainPlanner):
        def plan(self, context=None, user_input="", route=None, **kwargs):
            plan = super().plan(context=context, user_input=user_input, route=route, **kwargs)
            plan["steps"][3]["expected"] = 999
            return plan

    planner = FailingEngineeringPlanner(workspace=workspace)
    step_executor = EngineeringChainStepExecutor()
    loop = AgentLoop(
        planner=planner,
        step_executor=step_executor,
        repo_root=str(tmp_path),
        debug=False,
    )

    result = loop.run("Use planner runtime dispatch for Persistent Autonomous Engineering Runtime engineering task chain")

    assert result["ok"] is False

    orchestrator = result["persistent_runtime_orchestrator"]
    multi = orchestrator["multi_cycle_engineering_loop"]

    assert multi["closure_count"] == 1
    failed_cycle = multi["cycle_results"][0]
    closure = multi["closure_results"][0]["closure"]

    assert failed_cycle["runtime"]["status"] == "recoverable_failure"
    assert closure["status"] == "closed"
    assert closure["ok"] is True
    assert len(step_executor.calls) >= 4
