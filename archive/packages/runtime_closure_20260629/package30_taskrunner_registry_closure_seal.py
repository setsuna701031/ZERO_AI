from __future__ import annotations

import ast
import datetime as _dt
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
TASK_RUNNER_PATH = ROOT / "core" / "runtime" / "task_runner.py"
REPORT_PATH = ROOT / "taskrunner_registry_closure_seal_report.txt"
TEST_PATH = ROOT / "tests" / "test_taskrunner_registry_closure_seal.py"

TEST_SOURCE = 'from __future__ import annotations\n\nimport ast\nfrom pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\nTASK_RUNNER = ROOT / "core" / "runtime" / "task_runner.py"\nREPORT = ROOT / "taskrunner_registry_closure_seal_report.txt"\n\n\ndef test_taskrunner_registry_closure_seal_import_safe() -> None:\n    source = TASK_RUNNER.read_text(encoding="utf-8")\n    ast.parse(source)\n\n    import core.runtime.task_runner as module\n\n    assert module is not None\n\n\ndef test_taskrunner_registry_closure_seal_report_exists() -> None:\n    assert REPORT.exists()\n\n\ndef test_taskrunner_registry_closure_seal_report_has_required_sections() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "TaskRunner Registry Closure Seal Report" in text\n    assert "Candidate count" in text\n    assert "Remaining registry calls" in text\n    assert "Preserved specialized flows" in text\n    assert "Ready for final cleanup" in text\n    assert "Non-mainline issue reporting" in text\n\n\ndef test_taskrunner_registry_closure_seal_candidate_count_zero() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "candidate_for_unified_admission count: 0" in text\n\n\ndef test_taskrunner_registry_closure_seal_no_execute_tick_direct_registry_bypass() -> None:\n    source = TASK_RUNNER.read_text(encoding="utf-8")\n    tree = ast.parse(source)\n\n    registry_methods = {"run_observer", "admit", "observe", "record", "register", "dispatch"}\n    registry_hints = ("registry", "route_registry", "runtime_route_registry")\n    forbidden_names = ("execute_owned_step", "owned_step", "tick")\n\n    def chain(node: ast.AST) -> str:\n        parts = []\n        current = node\n        while isinstance(current, ast.Attribute):\n            parts.append(current.attr)\n            current = current.value\n        if isinstance(current, ast.Name):\n            parts.append(current.id)\n        else:\n            parts.append(type(current).__name__)\n        return ".".join(reversed(parts))\n\n    def nearest_function(target: ast.AST) -> str:\n        line = getattr(target, "lineno", -1)\n        best = ("<module>", -1)\n        for node in ast.walk(tree):\n            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):\n                start = getattr(node, "lineno", -1)\n                end = getattr(node, "end_lineno", start)\n                if start <= line <= end and start > best[1]:\n                    best = (node.name, start)\n        return best[0]\n\n    offenders = []\n    for node in ast.walk(tree):\n        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):\n            continue\n        if node.func.attr not in registry_methods:\n            continue\n        owner = chain(node.func.value).lower()\n        if not any(hint in owner for hint in registry_hints):\n            continue\n        function_name = nearest_function(node).lower()\n        if any(name in function_name for name in forbidden_names):\n            offenders.append((node.lineno, function_name, node.func.attr, owner))\n\n    assert offenders == []\n\n\ndef test_taskrunner_registry_closure_seal_unified_entrypoints_present() -> None:\n    source = TASK_RUNNER.read_text(encoding="utf-8")\n\n    assert "_aer_registry_admit" in source\n    assert "_zero_taskrunner_registry_callsite_admit_v26" in source\n    assert "_zero_taskrunner_registry_legacy_cleanup_guard_v28" in source\n'

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
    shutil.copy2(path, path.with_name(f"{path.name}.package30_backup_{stamp}"))


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
            "function": function_name,
            "owner": _attr_chain(node.func.value) if isinstance(node.func, ast.Attribute) else "",
            "method": node.func.attr if isinstance(node.func, ast.Attribute) else "",
            "classification": _classify(function_name, segment),
            "source": segment,
        })
    return sorted(calls, key=lambda item: (item["line"], item["method"]))


def _build_report(source: str) -> str:
    calls = _collect_direct_calls(source)
    by_class: dict[str, list[dict[str, Any]]] = {}
    for call in calls:
        by_class.setdefault(call["classification"], []).append(call)

    candidate_count = len(by_class.get("candidate_for_unified_admission", []))

    out: list[str] = []
    out.append("TaskRunner Registry Closure Seal Report")
    out.append("")
    out.append(f"generated_at: {_dt.datetime.now().isoformat(timespec='seconds')}")
    out.append(f"root: {ROOT}")
    out.append(f"target: {TASK_RUNNER_PATH.relative_to(ROOT).as_posix()}")
    out.append("")

    out.append("Candidate count")
    out.append(f"- candidate_for_unified_admission count: {candidate_count}")
    out.append("")

    out.append("Remaining registry calls")
    out.append(f"- total count: {len(calls)}")
    for call in calls:
        out.append(
            f"  - line {call['line']} | function={call['function']} | owner={call['owner']} | "
            f"method={call['method']} | classification={call['classification']} | source={call['source']}"
        )
    if not calls:
        out.append("  - none")
    out.append("")

    out.append("Classification")
    for name in (
        "candidate_for_unified_admission",
        "already_unified",
        "preserve_for_specialized_flow",
        "review_before_migration",
    ):
        items = by_class.get(name, [])
        out.append(f"- {name} count: {len(items)}")
        for item in items:
            out.append(f"  - line {item['line']} function={item['function']} method={item['method']}")
    out.append("")

    out.append("Preserved specialized flows")
    out.append("- repair")
    out.append("- rollback")
    out.append("- evidence")
    out.append("- authority")
    out.append("- checkpoint")
    out.append("- recovery")
    out.append("")

    if candidate_count == 0:
        out.append("Ready for final cleanup")
        out.append("- yes: execute_owned_step/owned_step/tick candidate registry bypasses are sealed at zero")
    else:
        out.append("Ready for final cleanup")
        out.append("- no: candidate registry bypasses remain")
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
    out.append("python -m pytest tests/test_taskrunner_registry_closure_seal.py tests/test_taskrunner_registry_legacy_cleanup_phase2.py tests/test_taskrunner_registry_legacy_cleanup_phase1.py tests/test_taskrunner_registry_legacy_cleanup_inventory.py tests/test_taskrunner_registry_callsite_migration.py tests/test_taskrunner_registry_direct_admission_inventory.py tests/test_taskrunner_registry_admission_consolidation.py tests/test_taskrunner_aer_closure_inventory.py tests/test_aer_mainline_closure_seal.py -q")
    out.append("")

    out.append("Non-mainline issue reporting")
    out.append("Any unrelated issue discovered during validation must be reported explicitly and not silently skipped.")
    out.append("")

    return "\n".join(out)


def main() -> int:
    if not TASK_RUNNER_PATH.exists():
        raise FileNotFoundError(f"Missing TaskRunner target: {TASK_RUNNER_PATH}")

    _backup(REPORT_PATH)
    _backup(TEST_PATH)

    source = TASK_RUNNER_PATH.read_text(encoding="utf-8")
    ast.parse(source)

    for required in (
        "_zero_taskrunner_registry_admit_aer_closure_v24",
        "_zero_taskrunner_registry_callsite_admit_v26",
        "_zero_taskrunner_registry_legacy_cleanup_guard_v28",
    ):
        if required not in source:
            raise RuntimeError(f"Required registry closure helper is missing: {required}")

    report = _build_report(source)
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")

    TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ast.parse(TEST_SOURCE)
    TEST_PATH.write_text(TEST_SOURCE, encoding="utf-8", newline="\n")

    if "candidate_for_unified_admission count: 0" not in report:
        raise RuntimeError("TaskRunner registry closure seal failed: candidate registry bypasses remain")

    print(str(REPORT_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
