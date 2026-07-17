from __future__ import annotations

import ast
import datetime as _dt
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
TASK_RUNNER_PATH = ROOT / "core" / "runtime" / "task_runner.py"
REPORT_PATH = ROOT / "taskrunner_registry_legacy_cleanup_phase2_report.txt"
TEST_PATH = ROOT / "tests" / "test_taskrunner_registry_legacy_cleanup_phase2.py"

TEST_SOURCE = 'from __future__ import annotations\n\nimport ast\nfrom pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\nTASK_RUNNER = ROOT / "core" / "runtime" / "task_runner.py"\nREPORT = ROOT / "taskrunner_registry_legacy_cleanup_phase2_report.txt"\n\n\ndef test_taskrunner_registry_legacy_cleanup_phase2_import_safe() -> None:\n    source = TASK_RUNNER.read_text(encoding="utf-8")\n    ast.parse(source)\n\n    import core.runtime.task_runner as module\n\n    assert module is not None\n\n\ndef test_taskrunner_registry_legacy_cleanup_phase2_report_exists() -> None:\n    assert REPORT.exists()\n\n\ndef test_taskrunner_registry_legacy_cleanup_phase2_report_has_required_sections() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "TaskRunner Registry Legacy Cleanup Phase2 Report" in text\n    assert "Removed standalone candidate calls" in text\n    assert "Skipped non-standalone candidate calls" in text\n    assert "Remaining direct registry calls" in text\n    assert "Preserved specialized paths" in text\n    assert "Non-mainline issue reporting" in text\n\n\ndef test_taskrunner_registry_legacy_cleanup_phase2_no_standalone_candidate_expr_calls() -> None:\n    source = TASK_RUNNER.read_text(encoding="utf-8")\n    tree = ast.parse(source)\n\n    registry_methods = {"run_observer", "admit", "observe", "record", "register", "dispatch"}\n    registry_hints = ("registry", "route_registry", "runtime_route_registry")\n    candidate_names = ("execute_owned_step", "owned_step", "tick")\n\n    def chain(node: ast.AST) -> str:\n        parts = []\n        current = node\n        while isinstance(current, ast.Attribute):\n            parts.append(current.attr)\n            current = current.value\n        if isinstance(current, ast.Name):\n            parts.append(current.id)\n        else:\n            parts.append(type(current).__name__)\n        return ".".join(reversed(parts))\n\n    def nearest_function(target: ast.AST) -> str:\n        line = getattr(target, "lineno", -1)\n        best = ("", -1)\n        for node in ast.walk(tree):\n            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):\n                start = getattr(node, "lineno", -1)\n                end = getattr(node, "end_lineno", start)\n                if start <= line <= end and start > best[1]:\n                    best = (node.name, start)\n        return best[0]\n\n    offenders = []\n    for node in ast.walk(tree):\n        if not isinstance(node, ast.Expr):\n            continue\n        value = node.value\n        if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Attribute):\n            continue\n        if value.func.attr not in registry_methods:\n            continue\n        owner = chain(value.func.value).lower()\n        if not any(hint in owner for hint in registry_hints):\n            continue\n        fname = nearest_function(node).lower()\n        if any(token in fname for token in candidate_names):\n            offenders.append((node.lineno, fname, value.func.attr, owner))\n\n    assert offenders == []\n\n\ndef test_taskrunner_registry_legacy_cleanup_phase2_keeps_unified_helpers() -> None:\n    source = TASK_RUNNER.read_text(encoding="utf-8")\n\n    assert "_aer_registry_admit" in source\n    assert "_zero_taskrunner_registry_callsite_admit_v26" in source\n    assert "_zero_taskrunner_registry_legacy_cleanup_guard_v28" in source\n'

REGISTRY_METHODS = {
    "run_observer",
    "admit",
    "observe",
    "record",
    "register",
    "dispatch",
}

REGISTRY_NAME_HINTS = (
    "registry",
    "route_registry",
    "runtime_route_registry",
)

CANDIDATE_KEYWORDS = (
    "execute_owned_step",
    "owned_step",
    "tick",
)

PRESERVE_KEYWORDS = (
    "repair",
    "rollback",
    "evidence",
    "audit",
    "authority",
    "checkpoint",
    "recovery",
)


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path.with_name(f"{path.name}.package29_backup_{stamp}"))


def _attr_chain(node: ast.AST) -> str:
    parts: list[str] = []
    current: ast.AST | None = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    else:
        parts.append(type(current).__name__)
    return ".".join(reversed(parts))


def _is_registry_like(chain: str) -> bool:
    lowered = chain.lower()
    return any(hint in lowered for hint in REGISTRY_NAME_HINTS)


def _source_segment(source: str, node: ast.AST) -> str:
    try:
        return (ast.get_source_segment(source, node) or "").strip().replace("\n", " ")
    except Exception:
        return ""


def _nearest_function(tree: ast.AST, target: ast.AST) -> str:
    target_line = getattr(target, "lineno", -1)
    best_name = "<module>"
    best_line = -1
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = getattr(node, "lineno", -1)
            end = getattr(node, "end_lineno", start)
            if start <= target_line <= end and start > best_line:
                best_name = node.name
                best_line = start
    return best_name


def _classify(function_name: str, source_text: str) -> str:
    text = (function_name + " " + source_text).lower()
    if "_aer_registry_admit" in text or "_registry_admit_" in text:
        return "already_unified"
    if any(token in text for token in PRESERVE_KEYWORDS):
        return "preserve_for_specialized_flow"
    if any(token in text for token in CANDIDATE_KEYWORDS):
        return "candidate_for_unified_admission"
    return "review_before_migration"


def _is_direct_registry_call(call: ast.Call) -> bool:
    if not isinstance(call.func, ast.Attribute):
        return False
    if call.func.attr not in REGISTRY_METHODS:
        return False
    owner = _attr_chain(call.func.value)
    return _is_registry_like(owner)


def _collect_direct_calls(source: str) -> list[dict[str, Any]]:
    tree = ast.parse(source)
    calls: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_direct_registry_call(node):
            continue
        function_name = _nearest_function(tree, node)
        segment = _source_segment(source, node)
        calls.append({
            "line": getattr(node, "lineno", 0),
            "end_line": getattr(node, "end_lineno", getattr(node, "lineno", 0)),
            "function": function_name,
            "owner": _attr_chain(node.func.value) if isinstance(node.func, ast.Attribute) else "",
            "method": node.func.attr if isinstance(node.func, ast.Attribute) else "",
            "classification": _classify(function_name, segment),
            "source": segment,
        })
    return sorted(calls, key=lambda item: (item["line"], item["method"]))


def _find_standalone_candidate_expr_calls(source: str) -> list[dict[str, Any]]:
    tree = ast.parse(source)
    removals: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr):
            continue
        value = node.value
        if not isinstance(value, ast.Call) or not _is_direct_registry_call(value):
            continue
        function_name = _nearest_function(tree, node)
        classification = _classify(function_name, _source_segment(source, value))
        if classification != "candidate_for_unified_admission":
            continue
        removals.append({
            "line": getattr(node, "lineno", 0),
            "end_line": getattr(node, "end_lineno", getattr(node, "lineno", 0)),
            "function": function_name,
            "method": value.func.attr if isinstance(value.func, ast.Attribute) else "",
            "source": _source_segment(source, node),
        })
    return sorted(removals, key=lambda item: item["line"])


def _apply_removals(source: str, removals: list[dict[str, Any]]) -> str:
    if not removals:
        return source

    remove_lines: set[int] = set()
    for item in removals:
        remove_lines.update(range(item["line"], item["end_line"] + 1))

    lines = source.splitlines()
    kept: list[str] = []
    for idx, line in enumerate(lines, start=1):
        if idx in remove_lines:
            continue
        kept.append(line)
    return "\n".join(kept).rstrip() + "\n"


def _non_standalone_candidates(source: str, removed_lines: set[int]) -> list[dict[str, Any]]:
    calls = _collect_direct_calls(source)
    skipped: list[dict[str, Any]] = []
    for call in calls:
        if call["classification"] != "candidate_for_unified_admission":
            continue
        if call["line"] in removed_lines:
            continue
        skipped.append(call)
    return skipped


def _build_report(before: str, after: str, removals: list[dict[str, Any]], skipped: list[dict[str, Any]]) -> str:
    before_calls = _collect_direct_calls(before)
    after_calls = _collect_direct_calls(after)

    out: list[str] = []
    out.append("TaskRunner Registry Legacy Cleanup Phase2 Report")
    out.append("")
    out.append(f"generated_at: {_dt.datetime.now().isoformat(timespec='seconds')}")
    out.append(f"root: {ROOT}")
    out.append(f"target: {TASK_RUNNER_PATH.relative_to(ROOT).as_posix()}")
    out.append("")

    out.append("Removed standalone candidate calls")
    out.append(f"- removed count: {len(removals)}")
    for item in removals:
        out.append(
            f"  - line {item['line']} | function={item['function']} | "
            f"method={item['method']} | source={item['source']}"
        )
    if not removals:
        out.append("  - none")
    out.append("")

    out.append("Skipped non-standalone candidate calls")
    out.append(f"- skipped count: {len(skipped)}")
    for item in skipped:
        out.append(
            f"  - line {item['line']} | function={item['function']} | method={item['method']} | "
            f"classification={item['classification']} | source={item['source']}"
        )
    if not skipped:
        out.append("  - none")
    out.append("")

    out.append("Remaining direct registry calls")
    out.append(f"- before count: {len(before_calls)}")
    out.append(f"- after count: {len(after_calls)}")
    for call in after_calls:
        out.append(
            f"  - line {call['line']} | function={call['function']} | owner={call['owner']} | "
            f"method={call['method']} | classification={call['classification']} | source={call['source']}"
        )
    out.append("")

    out.append("Preserved specialized paths")
    out.append("- repair remains preserved")
    out.append("- rollback remains preserved")
    out.append("- evidence remains preserved")
    out.append("- authority/checkpoint/recovery remain preserved")
    out.append("")

    out.append("No blind deletion")
    out.append("- only standalone candidate expression calls were removed")
    out.append("- assignment/return/conditional registry calls were not rewritten in this package")
    out.append("- specialized repair/rollback/evidence paths were not modified")
    out.append("")

    out.append("Not touched")
    out.append("- Scheduler")
    out.append("- AgentLoop")
    out.append("- CLI")
    out.append("- RuntimeRouteRegistry")
    out.append("- Runtime Native marker chain")
    out.append("")

    out.append("Validation")
    out.append("python -m compileall core/runtime tests")
    out.append("python -m pytest tests/test_taskrunner_registry_legacy_cleanup_phase2.py tests/test_taskrunner_registry_legacy_cleanup_phase1.py tests/test_taskrunner_registry_legacy_cleanup_inventory.py tests/test_taskrunner_registry_callsite_migration.py tests/test_taskrunner_registry_direct_admission_inventory.py tests/test_taskrunner_registry_admission_consolidation.py tests/test_taskrunner_aer_closure_inventory.py tests/test_aer_mainline_closure_seal.py -q")
    out.append("")

    out.append("Non-mainline issue reporting")
    out.append("Any unrelated issue discovered during validation must be reported explicitly and not silently skipped.")
    out.append("")

    return "\n".join(out)


def main() -> int:
    if not TASK_RUNNER_PATH.exists():
        raise FileNotFoundError(f"Missing TaskRunner target: {TASK_RUNNER_PATH}")

    _backup(TASK_RUNNER_PATH)
    _backup(TEST_PATH)
    _backup(REPORT_PATH)

    before = TASK_RUNNER_PATH.read_text(encoding="utf-8")
    for required in (
        "_zero_taskrunner_registry_callsite_admit_v26",
        "_zero_taskrunner_registry_legacy_cleanup_guard_v28",
    ):
        if required not in before:
            raise RuntimeError(f"Required helper is missing: {required}")

    removals = _find_standalone_candidate_expr_calls(before)
    removed_lines = set()
    for item in removals:
        removed_lines.update(range(item["line"], item["end_line"] + 1))

    after = _apply_removals(before, removals)
    ast.parse(after)
    skipped = _non_standalone_candidates(after, removed_lines)

    TASK_RUNNER_PATH.write_text(after, encoding="utf-8", newline="\n")

    TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ast.parse(TEST_SOURCE)
    TEST_PATH.write_text(TEST_SOURCE, encoding="utf-8", newline="\n")

    report = _build_report(before, after, removals, skipped)
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")

    print(str(REPORT_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
