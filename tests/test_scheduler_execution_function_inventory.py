from __future__ import annotations

import ast
from pathlib import Path


TARGET = Path("core/tasks/scheduler.py")


EXECUTION_NAME_MARKERS = [
    "run_one",
    "run_once",
    "run_next",
    "tick",
    "dispatch",
    "execute",
    "runner",
    "step",
    "terminal",
    "blocked",
    "finished",
    "failed",
]


def _function_names() -> list[str]:
    tree = ast.parse(TARGET.read_text(encoding="utf-8", errors="ignore"))
    names: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)

    return names


def test_scheduler_execution_functions_are_visible() -> None:
    names = _function_names()

    matched = [
        name
        for name in names
        if any(marker in name.lower() for marker in EXECUTION_NAME_MARKERS)
    ]

    assert len(matched) >= 20


def test_scheduler_has_core_execution_entrypoints() -> None:
    names = set(_function_names())

    expected = {
        "run_next",
        "run_one",
        "run_once",
        "tick",
        "run_one_step",
    }

    missing = sorted(expected - names)

    assert missing == []


def test_scheduler_simple_runner_boundary_is_runtime_owned() -> None:
    content = TARGET.read_text(encoding="utf-8", errors="ignore")

    forbidden_wrappers = [
        "def _handle_simple_terminal_task",
        "def _handle_simple_blocked_task",
        "def _handle_simple_finished_task",
        "def _handle_simple_invalid_step",
        "def _handle_simple_step_exception",
        "def _handle_simple_step_success",
    ]

    for wrapper in forbidden_wrappers:
        assert wrapper not in content, wrapper

    required_entrypoints = {
        "_run_simple_task_tick",
        "_execute_simple_step",
    }

    names = set(_function_names())

    missing = sorted(required_entrypoints - names)

    assert missing == []