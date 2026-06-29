from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.integration]

ROOT = Path(__file__).resolve().parents[1]

SCAN_ROOTS = (
    ROOT / "core" / "runtime",
    ROOT / "core" / "tasks",
    ROOT / "core" / "adaptive",
)

CANONICAL_OWNER_SYMBOL = "core.runtime.task_runtime.project_runtime_status"

ALLOWED_FILES = {
    "core/runtime/runtime_state_machine.py",
    "core/runtime/task_runtime.py",
}

TRACKED_STATUS_TARGETS = {
    "state",
    "task",
    "runtime_state",
    "safe_runtime_state",
    "task_payload",
    "runtime_payload",
    "next_task",
    "effective_task",
    "goal_state",
    "session",
    "record",
    "result",
    "payload",
    "after",
    "updated_task",
}

CANONICAL_PROJECTION_CLIENTS = {
    "core/adaptive/adaptive_runtime_resume.py",
    "core/runtime/persistent_runtime_orchestrator.py",
    "core/runtime/runtime_recovery_continuation.py",
    "core/runtime/task_runner.py",
    "core/runtime/thin_runtime_bridge.py",
    "core/runtime/work_package_queue.py",
    "core/tasks/scheduler.py",
    "core/tasks/scheduler_core/repo_state_helpers.py",
    "core/tasks/scheduler_core/runtime_overlay_helpers.py",
    "core/tasks/scheduler_core/runtime_resume_gate.py",
    "core/tasks/scheduler_core/simple_runner_helpers.py",
}


def _repo_rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _status_key(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == "status"


def _target_base_name(node: ast.AST) -> str:
    value = node.value if isinstance(node, ast.Subscript) else node
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return ""


def _status_assignments(path: Path) -> list[tuple[int, str]]:
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(path))
    findings: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue

        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if not isinstance(target, ast.Subscript):
                continue
            if not _status_key(target.slice):
                continue

            base = _target_base_name(target)
            if base not in TRACKED_STATUS_TARGETS:
                continue

            segment = ast.get_source_segment(source, node) or "status assignment"
            findings.append((node.lineno, segment.strip()))

    return findings


def test_runtime_status_ownership_inventory_is_explicit() -> None:
    findings: dict[str, list[tuple[int, str]]] = {}

    for root in SCAN_ROOTS:
        for path in root.rglob("*.py"):
            rel = _repo_rel(path)
            if rel in ALLOWED_FILES:
                continue
            writes = _status_assignments(path)
            if writes:
                findings[rel] = writes

    assert not findings, {
        "unexpected_direct_status_writers": findings,
        "canonical_owner": CANONICAL_OWNER_SYMBOL,
        "required_boundary": "project_runtime_status(...) or runtime state-machine APIs",
    }


def test_runtime_status_owner_files_exist() -> None:
    for rel in ALLOWED_FILES:
        assert (ROOT / rel).exists(), rel


def test_runtime_status_projection_owner_is_canonical() -> None:
    source = (ROOT / "core/runtime/task_runtime.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    owner = next(
        (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "project_runtime_status"),
        None,
    )

    assert owner is not None, CANONICAL_OWNER_SYMBOL
    assert any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Subscript) and _status_key(target.slice)
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
        for node in ast.walk(owner)
    ), "canonical owner must perform the status projection"


def test_historical_status_writers_are_canonical_projection_clients() -> None:
    missing: list[str] = []

    for rel in sorted(CANONICAL_PROJECTION_CLIENTS):
        path = ROOT / rel
        if not path.exists() or "project_runtime_status(" not in path.read_text(encoding="utf-8-sig"):
            missing.append(rel)

    assert not missing, {
        "missing_canonical_projection_clients": missing,
        "canonical_owner": CANONICAL_OWNER_SYMBOL,
    }
