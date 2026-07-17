from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.adaptive import AdaptiveDispatcher, AdaptivePlan, AdaptiveRuntimeResume
from core.runtime.task_runner import TaskRunner


REPO_ROOT = Path(__file__).resolve().parents[1]


class RecordingRunner(TaskRunner):
    def __init__(self) -> None:
        self.calls = 0

    def run_task(self, task, current_tick=0):
        self.calls += 1
        return {"ok": True, "status": "running", "task": task, "current_tick": current_tick}


def test_runtime_consumes_execution_contract_only() -> None:
    runner = RecordingRunner()
    contract = AdaptiveDispatcher().dispatch(AdaptivePlan("goal-1", "sub-1", "continue_active", "continue"))
    result = runner.run_task_adaptive({"task_id": "task-1"}, execution_contract=contract)
    assert result["status"] == "running"
    assert runner.calls == 1

    with pytest.raises(TypeError, match="requires_adaptive_execution_contract"):
        runner.run_task_adaptive({"task_id": "task-1"}, execution_contract={"action_type": "execute_next_step"})


def test_runtime_does_not_execute_disallowed_contract() -> None:
    runner = RecordingRunner()
    contract = AdaptiveDispatcher().dispatch(AdaptivePlan("goal-1", "sub-1", "wait_for_user", "review"))
    result = runner.run_task_adaptive({"task_id": "task-1"}, execution_contract=contract)
    assert result["runtime_allowed"] is False
    assert runner.calls == 0


def test_runtime_does_not_accept_adaptive_runtime_resume_as_decision_authority() -> None:
    runner = RecordingRunner()
    with pytest.raises(TypeError, match="requires_adaptive_execution_contract"):
        runner.run_task_adaptive({"task_id": "task-1"}, execution_contract=AdaptiveRuntimeResume())


def test_runtime_bridge_imports_no_planner_or_goal_state_machine() -> None:
    paths = [
        REPO_ROOT / "core" / "runtime" / "task_runner.py",
        REPO_ROOT / "core" / "runtime" / "persistent_runtime_orchestrator.py",
    ]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "core.adaptive.adaptive_planner" not in imports
        assert "core.goals.goal_state_machine" not in imports


def test_runtime_reads_only_allowed_execution_contract_fields() -> None:
    path = REPO_ROOT / "core" / "runtime" / "task_runner.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_zero_run_task_adaptive"
    )
    fields = {
        node.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "execution_contract"
    }
    assert fields == {"action_type", "runtime_allowed"}
