from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_PATH = ROOT / "core" / "tasks" / "scheduler.py"


def _source() -> str:
    return SCHEDULER_PATH.read_text(encoding="utf-8-sig")


def _method_node(name: str) -> ast.FunctionDef:
    tree = ast.parse(_source())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found")


def _owner(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
    return "<module>"


def test_scheduler_imports_endpoint_and_delegation_boundary_types() -> None:
    source = _source()

    assert "from core.runtime.step_executor import StepExecutor" in source
    assert "from core.runtime.task_runner import TaskRunner" in source


def test_scheduler_constructs_one_endpoint_and_one_delegation_boundary() -> None:
    tree = ast.parse(_source())
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    constructors: list[str] = []
    direct_calls: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in {"StepExecutor", "TaskRunner"}:
                constructors.append(f"{func.id}:{_owner(node, parents)}:{node.lineno}")
            if isinstance(func, ast.Attribute) and func.attr in {"execute_step", "execute_steps"}:
                direct_calls.append(f"{func.attr}:{_owner(node, parents)}:{node.lineno}")

    assert direct_calls == []
    assert len([item for item in constructors if item.startswith("StepExecutor:__init__:")]) == 1
    assert len([item for item in constructors if item.startswith("TaskRunner:__init__:")]) == 1


def test_scheduler_runtime_boundary_uses_runtime_dispatcher_handoff() -> None:
    method_source = ast.get_source_segment(_source(), _method_node("_run_step_via_task_runner")) or ""

    assert "RuntimeDispatcher(" in method_source
    assert "run_scheduler_boundary" in method_source
    assert "runner.run_task" not in method_source
    assert "TaskRunner(" not in method_source
    assert "StepExecutor(" not in method_source
    assert ".execute_step(" not in method_source
    assert ".execute_steps(" not in method_source


def test_scheduler_execution_path_declares_delegation_boundary() -> None:
    source = _source()

    assert '"authority_path": "Scheduler -> RuntimeDispatcher -> TaskRunner -> StepExecutor"' in source
    assert '"direct_execution": False' in source
    assert '"scheduler_owns_execution": False' in source
    assert '"runtime_dispatcher_required": True' in source
    assert '"taskrunner_required": True' in source
    assert '"step_executor_endpoint_only": True' in source
