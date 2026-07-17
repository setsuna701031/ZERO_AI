from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_LOOP_PATH = ROOT / "core" / "agent" / "agent_loop.py"


def _source() -> str:
    return AGENT_LOOP_PATH.read_text(encoding="utf-8")


def _method_node() -> ast.FunctionDef:
    tree = ast.parse(_source())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_try_handle_engineering_task_route":
            return node
    raise AssertionError("_try_handle_engineering_task_route not found")


def test_legacy_direct_engineering_task_route_removed_from_source() -> None:
    source = _source()

    assert "legacy_direct_json_engineering_task_runner\"] = True" not in source
    assert "legacy_direct_json_engineering_task_runner'] = True" not in source
    assert "\"legacy_direct_json_engineering_task_runner\": True" not in source
    assert "'legacy_direct_json_engineering_task_runner': True" not in source
    assert "AgentLoop -> EngineeringTaskRunner" not in source


def test_engineering_task_route_is_runtime_admission_only() -> None:
    method = _method_node()
    method_source = ast.get_source_segment(_source(), method) or ""

    assert "governed_runtime_route" in method_source
    assert "runtime_owns_execution" in method_source
    assert "direct_execution" in method_source
    assert "agent_loop_owns_execution" in method_source
    assert "AgentExecutionRuntime" in method_source
    assert "TaskRunner" in method_source
    assert "StepExecutor" in method_source
    assert "EngineeringTaskRunner(" not in method_source


def test_agent_loop_does_not_directly_call_step_executor_in_legacy_route() -> None:
    method = _method_node()

    forbidden_names = {
        "EngineeringTaskRunner",
        "StepExecutor",
        "TaskRunner",
        "execute_step",
        "execute_steps",
    }

    for node in ast.walk(method):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Name):
                assert target.id not in forbidden_names
            if isinstance(target, ast.Attribute):
                assert target.attr not in {"execute_step", "execute_steps", "run_task"}
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"step_executor", "task_runner"}


def test_legacy_route_reports_runtime_owned_authority_contract() -> None:
    method_source = ast.get_source_segment(_source(), _method_node()) or ""

    assert "\"legacy_direct_json_engineering_task_runner\": False" in method_source
    assert "\"governed_runtime_route\": True" in method_source
    assert "\"runtime_owns_execution\": True" in method_source
    assert "\"direct_execution\": False" in method_source
    assert "\"agent_loop_owns_execution\": False" in method_source
    assert "\"taskrunner_required\": True" in method_source
    assert "\"step_executor_endpoint_only\": True" in method_source
