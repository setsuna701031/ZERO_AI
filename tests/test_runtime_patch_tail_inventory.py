from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


PATCH_TAIL_TARGETS = {
    "core/tasks/scheduler.py": "_zero_",
    "core/agent/agent_loop.py": "_zero_",
}


def _function_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def test_patch_tail_inventory_is_visible() -> None:
    inventory: dict[str, list[str]] = {}

    for relative_path, prefix in PATCH_TAIL_TARGETS.items():
        path = REPO_ROOT / relative_path
        assert path.exists(), relative_path

        names = [
            name
            for name in _function_names(path)
            if name.startswith(prefix)
        ]

        inventory[relative_path] = names

    assert inventory["core/tasks/scheduler.py"]
    assert inventory["core/agent/agent_loop.py"]


def test_scheduler_patch_tail_is_not_silent() -> None:
    names = _function_names(REPO_ROOT / "core/tasks/scheduler.py")
    patch_names = [name for name in names if name.startswith("_zero_")]

    assert len(patch_names) >= 1


def test_agent_loop_patch_tail_is_not_silent() -> None:
    names = _function_names(REPO_ROOT / "core/agent/agent_loop.py")
    patch_names = [name for name in names if name.startswith("_zero_")]

    assert len(patch_names) >= 1