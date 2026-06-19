from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCAN_ROOTS = (
    ROOT / "core" / "runtime",
    ROOT / "core" / "tasks",
    ROOT / "core" / "adaptive",
)

ALLOWED_FILES = {
    "core/runtime/runtime_state_machine.py",
    "core/runtime/task_runtime.py",
    "core/runtime/runtime_dispatcher.py",
    "core/runtime/runtime_session_resume.py",
    "core/tasks/task_state.py",
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

EXPECTED_HIGH_RISK_FILES = {
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

    high_risk = set(findings)

    assert EXPECTED_HIGH_RISK_FILES <= high_risk, {
        "missing_expected_high_risk_files": sorted(EXPECTED_HIGH_RISK_FILES - high_risk),
        "found": sorted(findings),
    }


def test_runtime_status_owner_files_exist() -> None:
    for rel in ALLOWED_FILES:
        assert (ROOT / rel).exists(), rel