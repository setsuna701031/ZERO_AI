from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASK_RUNNER = ROOT / "core" / "runtime" / "task_runner.py"
REPORT = ROOT / "taskrunner_registry_legacy_cleanup_phase2_report.txt"


def test_taskrunner_registry_legacy_cleanup_phase2_import_safe() -> None:
    source = TASK_RUNNER.read_text(encoding="utf-8")
    ast.parse(source)

    import core.runtime.task_runner as module

    assert module is not None


def test_taskrunner_registry_legacy_cleanup_phase2_report_exists() -> None:
    assert REPORT.exists()


def test_taskrunner_registry_legacy_cleanup_phase2_report_has_required_sections() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "TaskRunner Registry Legacy Cleanup Phase2 Report" in text
    assert "Removed standalone candidate calls" in text
    assert "Skipped non-standalone candidate calls" in text
    assert "Remaining direct registry calls" in text
    assert "Preserved specialized paths" in text
    assert "Non-mainline issue reporting" in text


def test_taskrunner_registry_legacy_cleanup_phase2_no_standalone_candidate_expr_calls() -> None:
    source = TASK_RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(source)

    registry_methods = {"run_observer", "admit", "observe", "record", "register", "dispatch"}
    registry_hints = ("registry", "route_registry", "runtime_route_registry")
    candidate_names = ("execute_owned_step", "owned_step", "tick")

    def chain(node: ast.AST) -> str:
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        else:
            parts.append(type(current).__name__)
        return ".".join(reversed(parts))

    def nearest_function(target: ast.AST) -> str:
        line = getattr(target, "lineno", -1)
        best = ("", -1)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = getattr(node, "lineno", -1)
                end = getattr(node, "end_lineno", start)
                if start <= line <= end and start > best[1]:
                    best = (node.name, start)
        return best[0]

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr):
            continue
        value = node.value
        if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Attribute):
            continue
        if value.func.attr not in registry_methods:
            continue
        owner = chain(value.func.value).lower()
        if not any(hint in owner for hint in registry_hints):
            continue
        fname = nearest_function(node).lower()
        if any(token in fname for token in candidate_names):
            offenders.append((node.lineno, fname, value.func.attr, owner))

    assert offenders == []


def test_taskrunner_registry_legacy_cleanup_phase2_keeps_unified_helpers() -> None:
    source = TASK_RUNNER.read_text(encoding="utf-8")

    assert "_aer_registry_admit" in source
    assert "_zero_taskrunner_registry_callsite_admit_v26" in source
    assert "_zero_taskrunner_registry_legacy_cleanup_guard_v28" in source
