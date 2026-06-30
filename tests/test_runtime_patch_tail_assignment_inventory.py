from __future__ import annotations

import ast
from pathlib import Path
import pytest

pytestmark = [pytest.mark.contract, pytest.mark.contract_heavy]




REPO_ROOT = Path(__file__).resolve().parents[1]


def _patch_assignments(path: Path) -> list[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))

    assignments: list[tuple[str, str]] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Name):
            continue
        if not node.value.id.startswith("_zero_"):
            continue

        for target in node.targets:
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                assignments.append((f"{target.value.id}.{target.attr}", node.value.id))

    return assignments


def _class_method_names(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }

    return set()


def test_scheduler_patch_tail_assignments_are_visible() -> None:
    path = REPO_ROOT / "core/tasks/scheduler.py"

    assert path.exists(), "core/tasks/scheduler.py"

    assignments = _patch_assignments(path)

    assert assignments
    assert any(target.startswith("Scheduler.") for target, _source in assignments)


def test_agent_loop_runtime_contract_methods_are_visible() -> None:
    path = REPO_ROOT / "core/agent/agent_loop.py"

    assert path.exists(), "core/agent/agent_loop.py"

    methods = _class_method_names(path, "AgentLoop")

    assert "run" in methods
    assert "_try_force_scheduler_self_edit_route" in methods
    assert any(
        name in methods
        for name in (
            "_try_handle_direct_route",
            "_try_handle_llm_route",
            "_run_task_mode",
            "_run_single_shot_mode",
        )
    )


def test_agent_loop_no_fake_tail_assignment_required() -> None:
    path = REPO_ROOT / "core/agent/agent_loop.py"

    assert path.exists(), "core/agent/agent_loop.py"

    assignments = _patch_assignments(path)

    assert not any(target.startswith("AgentLoop.") for target, _source in assignments)