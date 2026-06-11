from __future__ import annotations

import ast
from pathlib import Path

from core.runtime.controlled_mutation_bridge import execute_controlled_mutation_probe


REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = REPO_ROOT / "core" / "runtime" / "controlled_mutation_bridge.py"


def _tree() -> ast.AST:
    return ast.parse(BRIDGE_PATH.read_text(encoding="utf-8-sig"), filename=str(BRIDGE_PATH))


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def test_controlled_mutation_bridge_has_no_direct_executor_authority() -> None:
    violations: list[str] = []

    for node in ast.walk(_tree()):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = {alias.name.rsplit(".", 1)[-1] for alias in node.names}
            if "StepExecutor" in names:
                violations.append(f"{node.lineno}:import StepExecutor")
        if isinstance(node, ast.Call) and _call_name(node) in {"StepExecutor", "execute_step"}:
            violations.append(f"{node.lineno}:{_call_name(node)}")

    assert violations == []


def test_controlled_mutation_bridge_has_no_hidden_executor_adapter() -> None:
    names = {
        node.name.lower()
        for node in ast.walk(_tree())
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }

    assert not {name for name in names if "executor_adapter" in name or "step_executor_from" in name}


def test_controlled_mutation_probe_returns_runtime_owned_execution_path(tmp_path: Path) -> None:
    result = execute_controlled_mutation_probe(
        repo_root=tmp_path,
        task={},
        task_id="mutation-authority-seal",
        goal="prove runtime-owned mutation path",
        target_path="workspace/shared/target.py",
    )

    assert result["ok"] is True
    path = result["execution_path"]
    assert path["direct_execution"] is False
    assert path["runtime_owns_execution"] is True
    assert path["taskrunner_required"] is True
    assert path["step_executor_endpoint_only"] is True
