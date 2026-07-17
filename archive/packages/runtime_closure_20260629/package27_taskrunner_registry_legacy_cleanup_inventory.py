from __future__ import annotations

import ast
import datetime as _dt
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
TASK_RUNNER_PATH = ROOT / "core" / "runtime" / "task_runner.py"
REPORT_PATH = ROOT / "taskrunner_registry_legacy_cleanup_inventory.txt"
TEST_PATH = ROOT / "tests" / "test_taskrunner_registry_legacy_cleanup_inventory.py"

TEST_SOURCE = 'from __future__ import annotations\n\nfrom pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\nREPORT = ROOT / "taskrunner_registry_legacy_cleanup_inventory.txt"\n\n\ndef test_taskrunner_registry_legacy_cleanup_inventory_report_exists() -> None:\n    assert REPORT.exists()\n\n\ndef test_taskrunner_registry_legacy_cleanup_inventory_has_required_sections() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "TaskRunner Registry Legacy Cleanup Inventory" in text\n    assert "Package24/26 Helper Presence" in text\n    assert "Remaining Direct Registry Calls" in text\n    assert "Cleanup Classification" in text\n    assert "Recommended Package28" in text\n    assert "Non-mainline issue reporting" in text\n\n\ndef test_taskrunner_registry_legacy_cleanup_inventory_mentions_preserved_paths() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "repair" in text\n    assert "rollback" in text\n    assert "evidence" in text\n\n\ndef test_taskrunner_registry_legacy_cleanup_inventory_mentions_target() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "core/runtime/task_runner.py" in text\n    assert "_aer_registry_admit" in text\n'

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

PRESERVE_KEYWORDS = (
    "repair",
    "rollback",
    "evidence",
    "audit",
    "authority",
    "checkpoint",
    "recovery",
)

MIGRATE_KEYWORDS = (
    "execute_owned_step",
    "owned_step",
    "tick",
)


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path.with_name(f"{path.name}.package27_backup_{stamp}"))


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


def _nearest_function(tree: ast.AST, target: ast.AST) -> tuple[str, int]:
    target_line = getattr(target, "lineno", -1)
    best = ("<module>", -1)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = getattr(node, "lineno", -1)
            end = getattr(node, "end_lineno", start)
            if start <= target_line <= end and start > best[1]:
                best = (node.name, start)
    return best


def _classify(function_name: str, source_text: str) -> str:
    text = (function_name + " " + source_text).lower()
    if any(token in text for token in PRESERVE_KEYWORDS):
        return "preserve_for_specialized_flow"
    if any(token in text for token in MIGRATE_KEYWORDS):
        return "candidate_for_unified_admission"
    if "_aer_registry_admit" in text or "_registry_admit_" in text:
        return "already_unified"
    return "review_before_migration"


def _collect_direct_calls(source: str) -> list[dict[str, Any]]:
    tree = ast.parse(source)
    calls: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        method = node.func.attr
        if method not in REGISTRY_METHODS:
            continue
        owner = _attr_chain(node.func.value)
        if not _is_registry_like(owner):
            continue
        function_name, function_line = _nearest_function(tree, node)
        segment = _source_segment(source, node)
        calls.append({
            "line": getattr(node, "lineno", 0),
            "function": function_name,
            "function_line": function_line,
            "owner": owner,
            "method": method,
            "classification": _classify(function_name, segment),
            "source": segment,
        })
    return sorted(calls, key=lambda item: (item["line"], item["method"]))


def _helper_presence(source: str) -> dict[str, int]:
    symbols = [
        "_zero_taskrunner_registry_admit_aer_closure_v24",
        "_zero_taskrunner_registry_admit_owned_step_v24",
        "_zero_taskrunner_registry_admit_tick_v24",
        "_zero_taskrunner_registry_callsite_admit_v26",
        "_zero_taskrunner_registry_callsite_wrap_execute_owned_step_v26",
        "_zero_taskrunner_registry_callsite_wrap_tick_v26",
        "_aer_registry_admit",
        "_registry_admit_owned_step",
        "_registry_admit_tick",
        "_zero_package26_registry_callsite_migration_installed",
    ]
    return {symbol: source.count(symbol) for symbol in symbols}


def _build_report() -> str:
    if not TASK_RUNNER_PATH.exists():
        raise FileNotFoundError(f"Missing TaskRunner target: {TASK_RUNNER_PATH}")

    source = TASK_RUNNER_PATH.read_text(encoding="utf-8", errors="replace")
    ast.parse(source)

    calls = _collect_direct_calls(source)
    helper_counts = _helper_presence(source)

    by_classification: dict[str, list[dict[str, Any]]] = {}
    for call in calls:
        by_classification.setdefault(call["classification"], []).append(call)

    out: list[str] = []
    out.append("TaskRunner Registry Legacy Cleanup Inventory")
    out.append("")
    out.append(f"generated_at: {_dt.datetime.now().isoformat(timespec='seconds')}")
    out.append(f"root: {ROOT}")
    out.append(f"target: {TASK_RUNNER_PATH.relative_to(ROOT).as_posix()}")
    out.append("")

    out.append("Package24/26 Helper Presence")
    for symbol, count in helper_counts.items():
        out.append(f"- {symbol} count: {count}")
    out.append("")

    out.append("Remaining Direct Registry Calls")
    out.append(f"total_remaining_direct_registry_calls: {len(calls)}")
    if calls:
        for call in calls:
            out.append(
                f"- line {call['line']} | function={call['function']} | owner={call['owner']} | "
                f"method={call['method']} | classification={call['classification']} | source={call['source']}"
            )
    else:
        out.append("- no remaining direct registry calls found")
    out.append("")

    out.append("Cleanup Classification")
    for name in (
        "candidate_for_unified_admission",
        "already_unified",
        "preserve_for_specialized_flow",
        "review_before_migration",
    ):
        items = by_classification.get(name, [])
        out.append(f"- {name} count: {len(items)}")
        for item in items:
            out.append(f"  - line {item['line']} function={item['function']} method={item['method']}")
    out.append("")

    out.append("Preserved specialized paths")
    out.append("- repair: preserve until repair-specific AER seal exists")
    out.append("- rollback: preserve until rollback payload semantics are sealed")
    out.append("- evidence: preserve until evidence authority semantics are sealed")
    out.append("- audit/authority/recovery/checkpoint: preserve unless separately inventoried and sealed")
    out.append("")

    out.append("Recommended Package28")
    out.append("- migrate only candidate_for_unified_admission call sites")
    out.append("- do not change preserve_for_specialized_flow call sites")
    out.append("- add a seal that fails if execute_owned_step/tick bypass _aer_registry_admit")
    out.append("- update inventory after migration so remaining calls are only preserve/review classes")
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
    out.append("python -m pytest tests/test_taskrunner_registry_legacy_cleanup_inventory.py tests/test_taskrunner_registry_callsite_migration.py tests/test_taskrunner_registry_direct_admission_inventory.py tests/test_taskrunner_registry_admission_consolidation.py tests/test_taskrunner_aer_closure_inventory.py tests/test_aer_mainline_closure_seal.py -q")
    out.append("")

    out.append("Non-mainline issue reporting")
    out.append("Any unrelated issue discovered during validation must be reported explicitly and not silently skipped.")
    out.append("")

    return "\n".join(out)


def main() -> int:
    _backup(REPORT_PATH)
    _backup(TEST_PATH)

    report = _build_report()
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")

    TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ast.parse(TEST_SOURCE)
    TEST_PATH.write_text(TEST_SOURCE, encoding="utf-8", newline="\n")

    print(str(REPORT_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
