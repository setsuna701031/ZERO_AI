from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from core.agent.agent_loop import AgentLoop


REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_LOOP_PATH = REPO_ROOT / "core" / "agent" / "agent_loop.py"


def _tree() -> ast.AST:
    return ast.parse(AGENT_LOOP_PATH.read_text(encoding="utf-8-sig"), filename=str(AGENT_LOOP_PATH))


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def test_agent_loop_has_no_direct_execution_endpoint_calls_or_construction() -> None:
    violations: list[str] = []

    for node in ast.walk(_tree()):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name in {"StepExecutor", "TaskRunner", "execute_step", "execute_steps", "_run_one_step"}:
            violations.append(f"{node.lineno}:{name}")

    assert violations == []


def test_agent_loop_does_not_hold_step_executor_or_taskrunner_authority() -> None:
    assignments: list[str] = []

    for node in ast.walk(_tree()):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and target.attr in {"step_executor", "task_runner"}
            ):
                assignments.append(f"{node.lineno}:self.{target.attr}")

    assert assignments == []


def test_v826_direct_step_executor_factory_is_removed() -> None:
    functions = {
        node.name
        for node in ast.walk(_tree())
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "_zero_v826_step_executor_from_agent" not in functions
    assert "_zero_v826_execution_runtime_from_agent" in functions


def test_agent_loop_endpoint_is_reached_through_runtime_and_taskrunner(tmp_path: Path) -> None:
    endpoint = _RecordingEndpoint()
    loop = AgentLoop(step_executor=endpoint, workspace_dir=str(tmp_path), repo_root=str(tmp_path))

    result = loop._execute_direct_step(
        {"type": "inspect", "path": "workspace/example.txt"},
        context={"source": "boundary_test"},
        user_input="inspect example",
        route={"mode": "direct"},
    )

    assert endpoint.calls
    authority = endpoint.calls[0]["context"]["authority_context"]
    assert authority["authority_layer"] == "task_runner"
    assert result["last_result"]["execution_path"]["authority_path"] == (
        "AgentLoop -> Runtime -> TaskRunner -> StepExecutor"
    )


def test_agent_loop_runtime_path_contract_is_auditable() -> None:
    loop = AgentLoop()
    result = loop.execution_runtime.run_step(step={"type": "inspect"})
    path = result["execution_path"]

    assert path["direct_execution"] is False
    assert path["agent_loop_owns_execution"] is False
    assert path["runtime_owns_execution"] is True
    assert path["taskrunner_required"] is True
    assert path["step_executor_endpoint_only"] is True
    assert path["authority_path"] == "AgentLoop -> Runtime -> TaskRunner -> StepExecutor"


class _RecordingEndpoint:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"ok": True, "source": "step_executor"}
