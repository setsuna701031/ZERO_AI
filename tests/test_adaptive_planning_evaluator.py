from __future__ import annotations

import ast
from pathlib import Path

from core.tasks.adaptive_planning_evaluator import (
    ADAPTIVE_PLANNING_DECISION_SCHEMA,
    AdaptivePlanningEvaluator,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EVALUATOR_PATH = REPO_ROOT / "core/tasks/adaptive_planning_evaluator.py"


def _decision(**kwargs) -> dict:
    defaults = {
        "latest_execution_result": {"ok": True, "status": "running", "result_bundle": {}},
        "current_goal_state": {"goal_state": "running", "remaining_tasks": ["next"], "blocked_tasks": [], "failed_tasks": []},
        "current_task_buckets": {"pending": [{"summary": {"task_id": "next"}}], "running": [], "completed": [], "blocked": [], "failed": []},
        "memory_summary": {"records": []},
    }
    defaults.update(kwargs)
    return AdaptivePlanningEvaluator().evaluate(**defaults)


def _imported_symbols() -> set[str]:
    tree = ast.parse(EVALUATOR_PATH.read_text(encoding="utf-8"))
    symbols: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                symbols.add(alias.name)
                symbols.add(alias.asname or alias.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            symbols.add(module)
            for alias in node.names:
                symbols.add(alias.name)
                symbols.add(alias.asname or alias.name)
                symbols.add(f"{module}.{alias.name}")
    return symbols


def _called_symbols() -> set[str]:
    tree = ast.parse(EVALUATOR_PATH.read_text(encoding="utf-8"))

    def name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""

    return {name(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}


def test_evaluator_continue_decision() -> None:
    result = _decision()

    assert result["schema"] == ADAPTIVE_PLANNING_DECISION_SCHEMA
    assert result["decision"] == "continue"
    assert result["reason"] == "continuation_can_proceed"
    assert result["terminal"] is False
    assert result["deterministic"] is True


def test_evaluator_replan_decision_after_failed_or_blocked_result() -> None:
    failed = _decision(
        latest_execution_result={"ok": False, "status": "failed", "result_bundle": {}},
        current_goal_state={"goal_state": "failed", "remaining_tasks": [], "blocked_tasks": [], "failed_tasks": ["failed_task"]},
        current_task_buckets={"pending": [], "running": [], "completed": [], "blocked": [], "failed": []},
    )
    blocked = _decision(
        latest_execution_result={"ok": False, "status": "blocked", "result_bundle": {}},
        current_goal_state={"goal_state": "blocked", "remaining_tasks": [], "blocked_tasks": ["blocked_task"], "failed_tasks": []},
        current_task_buckets={"pending": [], "running": [], "completed": [], "blocked": [{"summary": {"task_id": "blocked_task"}}], "failed": []},
    )

    assert failed["decision"] == "replan"
    assert failed["reason"] == "failed_task"
    assert blocked["decision"] == "replan"
    assert blocked["reason"] == "blocked_task"


def test_evaluator_block_decision() -> None:
    result = _decision(
        latest_execution_result={"ok": False, "status": "failed", "unrecoverable": True, "result_bundle": {}},
        current_goal_state={"goal_state": "running", "remaining_tasks": ["unsafe"], "blocked_tasks": [], "failed_tasks": []},
    )

    assert result["decision"] == "block"
    assert result["reason"] == "execution_result_unrecoverable"
    assert result["terminal"] is True


def test_evaluator_complete_decision() -> None:
    result = _decision(
        latest_execution_result={"ok": True, "status": "completed", "result_bundle": {}},
        current_goal_state={"goal_state": "completed", "remaining_tasks": [], "blocked_tasks": [], "failed_tasks": []},
        current_task_buckets={"pending": [], "running": [], "completed": [{"summary": {"task_id": "done"}}], "blocked": [], "failed": []},
    )

    assert result["decision"] == "complete"
    assert result["reason"] == "goal_lifecycle_completed"
    assert result["terminal"] is True


def test_evaluator_does_not_import_or_call_engineering_task_runner() -> None:
    imports = _imported_symbols()
    calls = _called_symbols()

    assert "core.tasks.engineering_task_runner" not in imports
    assert "EngineeringTaskRunner" not in imports
    assert "run_engineering_task" not in imports
    assert "run_engineering_task" not in calls


def test_evaluator_does_not_import_or_instantiate_engineering_memory_store() -> None:
    imports = _imported_symbols()
    calls = _called_symbols()

    assert "core.tasks.engineering_memory_store" not in imports
    assert "EngineeringMemoryStore" not in imports
    assert "EngineeringMemoryStore" not in calls
    assert "save_record" not in calls
