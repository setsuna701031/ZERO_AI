from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


RESPONSIBILITY_KEYWORDS = {
    "dispatch": ["dispatch", "run_one", "run_next", "tick", "runner"],
    "queue": ["queue", "enqueue", "requeue", "hygiene"],
    "replan": ["replan"],
    "repair": ["repair", "rollback", "fingerprint"],
    "path": ["path", "artifact", "scope"],
    "trace": ["trace", "history", "audit", "record", "observe"],
    "planner": ["plan", "planner", "parse", "route"],
    "repo_edit": ["repo_edit", "code_edit"],
    "task_loop": ["task", "loop", "run_task"],
    "response": ["response", "answer", "normalize"],
}


TARGET_FILES = {
    "scheduler": "core/tasks/scheduler.py",
    "agent_loop": "core/agent/agent_loop.py",
}


def _function_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)

    return names


def _bucket_functions(names: list[str]) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {key: [] for key in RESPONSIBILITY_KEYWORDS}

    for name in names:
        lowered = name.lower()

        for bucket, keywords in RESPONSIBILITY_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                buckets[bucket].append(name)

    return buckets


def test_scheduler_responsibility_buckets_are_visible() -> None:
    names = _function_names(REPO_ROOT / TARGET_FILES["scheduler"])
    buckets = _bucket_functions(names)

    assert buckets["dispatch"]
    assert buckets["queue"]
    assert buckets["repair"]
    assert buckets["path"]
    assert buckets["trace"]
    assert buckets["planner"]


def test_agent_loop_responsibility_buckets_are_visible() -> None:
    names = _function_names(REPO_ROOT / TARGET_FILES["agent_loop"])
    buckets = _bucket_functions(names)

    assert buckets["repo_edit"]
    assert buckets["planner"]
    assert buckets["trace"]
    assert buckets["task_loop"]
    assert buckets["response"]


def test_large_runtime_files_still_require_boundary_tracking() -> None:
    scheduler_lines = (REPO_ROOT / TARGET_FILES["scheduler"]).read_text(
        encoding="utf-8",
        errors="ignore",
    ).splitlines()

    agent_loop_lines = (REPO_ROOT / TARGET_FILES["agent_loop"]).read_text(
        encoding="utf-8",
        errors="ignore",
    ).splitlines()

    assert len(scheduler_lines) > 1000
    assert len(agent_loop_lines) > 1000