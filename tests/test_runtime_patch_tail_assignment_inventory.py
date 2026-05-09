from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


TARGET_FILES = [
    "core/tasks/scheduler.py",
    "core/agent/agent_loop.py",
]


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


def test_patch_tail_assignments_are_visible() -> None:
    inventory: dict[str, list[tuple[str, str]]] = {}

    for relative_path in TARGET_FILES:
        path = REPO_ROOT / relative_path
        assert path.exists(), relative_path
        inventory[relative_path] = _patch_assignments(path)

    assert inventory["core/tasks/scheduler.py"]
    assert inventory["core/agent/agent_loop.py"]


def test_scheduler_patch_tail_assignments_are_explicit() -> None:
    assignments = _patch_assignments(REPO_ROOT / "core/tasks/scheduler.py")

    assert any(target.startswith("Scheduler.") for target, _source in assignments)


def test_agent_loop_patch_tail_assignments_are_explicit() -> None:
    assignments = _patch_assignments(REPO_ROOT / "core/agent/agent_loop.py")

    assert any(target.startswith("AgentLoop.") for target, _source in assignments)