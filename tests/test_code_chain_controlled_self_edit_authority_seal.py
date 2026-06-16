from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from core.agent.code_chain_controlled_self_edit_bridge import (
    run_planner_owned_code_chain_bridge,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = REPO_ROOT / "core" / "agent" / "code_chain_controlled_self_edit_bridge.py"


def _tree() -> ast.AST:
    return ast.parse(BRIDGE_PATH.read_text(encoding="utf-8-sig"), filename=str(BRIDGE_PATH))


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def test_bridge_has_no_direct_step_executor_authority() -> None:
    violations: list[str] = []
    functions: set[str] = set()

    for node in ast.walk(_tree()):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(node.name)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name.rsplit(".", 1)[-1] for alias in node.names]
            if "StepExecutor" in names:
                violations.append(f"{node.lineno}:import StepExecutor")
        if isinstance(node, ast.Call) and _call_name(node) in {
            "StepExecutor",
            "execute_step",
            "execute_steps",
        }:
            violations.append(f"{node.lineno}:{_call_name(node)}")

    assert "step_executor_from_agent" not in functions
    assert violations == []


def test_bridge_does_not_read_agent_execution_endpoints() -> None:
    violations = [
        f"{node.lineno}:agent.{node.attr}"
        for node in ast.walk(_tree())
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "agent"
        and node.attr in {"step_executor", "task_runner"}
    ]

    assert violations == []


def test_bridge_without_dispatcher_capability_returns_blocked_audit_payload(tmp_path: Path) -> None:
    runtime = _RecordingRuntime()
    agent = _Agent(runtime=runtime, repo_root=tmp_path)

    result = run_planner_owned_code_chain_bridge(
        agent=agent,
        user_input="repair the controlled workcopy",
        call_planner_like=lambda *_args, **_kwargs: {
            "ok": True,
            "goal": "repair controlled workcopy",
            "route": "code_chain_controlled_self_edit",
            "requires_controlled_mutation": True,
            "steps": [{"type": "controlled_edit", "target_path": "workspace/example.py"}],
        },
    )

    assert result is not None
    assert runtime.calls == []
    assert result["ok"] is False
    assert result["blocked"] is True
    assert result["execution"]["executed"] is False
    assert result["execution"]["error"]
    assert result.get("finished") is not True
    assert result.get("completed") is not True
    path = result["execution_path"]
    assert path["direct_execution"] is False
    assert path["runtime_owns_execution"] is True
    assert path["taskrunner_required"] is True
    assert "Runtime -> TaskRunner -> StepExecutor" in path["authority_path"]


class _RecordingRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run_steps(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "ok": True,
            "results": [],
            "last_result": {},
            "execution_trace": [],
            "final_answer": "controlled repair complete",
        }


class _Agent:
    def __init__(self, *, runtime: Any, repo_root: Path) -> None:
        self.execution_runtime = runtime
        self.extra_kwargs = {"repo_root": str(repo_root)}
