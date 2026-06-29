from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASK_RUNNER = ROOT / "core" / "runtime" / "task_runner.py"
REPORT = ROOT / "taskrunner_registry_closure_seal_report.txt"


def test_taskrunner_registry_closure_seal_import_safe() -> None:
    source = TASK_RUNNER.read_text(encoding="utf-8")
    ast.parse(source)

    import core.runtime.task_runner as module

    assert module is not None


def test_taskrunner_registry_closure_seal_report_exists() -> None:
    assert REPORT.exists()


def test_taskrunner_registry_closure_seal_report_has_required_sections() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "TaskRunner Registry Closure Seal Report" in text
    assert "Candidate count" in text
    assert "Remaining registry calls" in text
    assert "Preserved specialized flows" in text
    assert "Ready for final cleanup" in text
    assert "Non-mainline issue reporting" in text


def test_taskrunner_registry_closure_seal_candidate_count_zero() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "candidate_for_unified_admission count: 0" in text


def test_taskrunner_registry_closure_seal_no_execute_tick_direct_registry_bypass() -> None:
    source = TASK_RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(source)

    registry_methods = {"run_observer", "admit", "observe", "record", "register", "dispatch"}
    registry_hints = ("registry", "route_registry", "runtime_route_registry")
    forbidden_names = ("execute_owned_step", "owned_step", "tick")

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
        best = ("<module>", -1)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = getattr(node, "lineno", -1)
                end = getattr(node, "end_lineno", start)
                if start <= line <= end and start > best[1]:
                    best = (node.name, start)
        return best[0]

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in registry_methods:
            continue
        owner = chain(node.func.value).lower()
        if not any(hint in owner for hint in registry_hints):
            continue
        function_name = nearest_function(node).lower()
        if any(name in function_name for name in forbidden_names):
            offenders.append((node.lineno, function_name, node.func.attr, owner))

    assert offenders == []


def test_taskrunner_registry_closure_seal_unified_entrypoints_present() -> None:
    source = TASK_RUNNER.read_text(encoding="utf-8")

    assert "_aer_registry_admit" in source
    assert "_zero_taskrunner_registry_callsite_admit_v26" in source
    assert "_zero_taskrunner_registry_legacy_cleanup_guard_v28" in source
