from __future__ import annotations

import ast
import datetime as _dt
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
TASK_RUNNER_PATH = ROOT / "core" / "runtime" / "task_runner.py"
REPORT_PATH = ROOT / "taskrunner_registry_direct_admission_inventory.txt"
TEST_PATH = ROOT / "tests" / "test_taskrunner_registry_direct_admission_inventory.py"

TEST_SOURCE = 'from __future__ import annotations\n\nfrom pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\nREPORT = ROOT / "taskrunner_registry_direct_admission_inventory.txt"\n\n\ndef test_taskrunner_registry_direct_admission_inventory_report_exists() -> None:\n    assert REPORT.exists()\n\n\ndef test_taskrunner_registry_direct_admission_inventory_has_required_sections() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "TaskRunner Registry Direct Admission Inventory" in text\n    assert "Direct Registry Call Inventory" in text\n    assert "Package24 Helper Presence" in text\n    assert "Recommended Package26" in text\n    assert "Non-mainline issue reporting" in text\n\n\ndef test_taskrunner_registry_direct_admission_inventory_mentions_package24_helper() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "_zero_taskrunner_registry_admit_aer_closure_v24" in text\n    assert "_aer_registry_admit" in text\n\n\ndef test_taskrunner_registry_direct_admission_inventory_mentions_target() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "core/runtime/task_runner.py" in text\n'

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


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path.with_name(f"{path.name}.package25_backup_{stamp}"))


def _safe_segment(source: str, node: ast.AST) -> str:
    try:
        return ast.get_source_segment(source, node) or ""
    except Exception:
        return ""


def _attr_chain(node: ast.AST) -> str:
    parts: list[str] = []
    current: ast.AST | None = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    elif isinstance(current, ast.Constant):
        parts.append(repr(current.value))
    else:
        parts.append(type(current).__name__)
    return ".".join(reversed(parts))


def _is_registry_like(chain: str) -> bool:
    lowered = chain.lower()
    return any(hint in lowered for hint in REGISTRY_NAME_HINTS)


def _nearest_function_name(tree: ast.AST, target: ast.AST) -> str:
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


def _collect_direct_calls(source: str) -> list[dict[str, Any]]:
    tree = ast.parse(source)
    calls: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        method = func.attr
        if method not in REGISTRY_METHODS:
            continue
        owner = _attr_chain(func.value)
        if not _is_registry_like(owner):
            continue

        calls.append(
            {
                "line": getattr(node, "lineno", 0),
                "function": _nearest_function_name(tree, node),
                "owner": owner,
                "method": method,
                "source": _safe_segment(source, node).strip().replace("\n", " "),
            }
        )

    return sorted(calls, key=lambda item: (item["line"], item["method"]))


def _collect_helper_presence(source: str) -> dict[str, int]:
    symbols = [
        "_zero_taskrunner_registry_admit_aer_closure_v24",
        "_zero_taskrunner_registry_admit_owned_step_v24",
        "_zero_taskrunner_registry_admit_tick_v24",
        "_aer_registry_admit",
        "_registry_admit_owned_step",
        "_registry_admit_tick",
    ]
    return {symbol: source.count(symbol) for symbol in symbols}


def _build_report() -> str:
    if not TASK_RUNNER_PATH.exists():
        raise FileNotFoundError(f"Missing TaskRunner target: {TASK_RUNNER_PATH}")

    source = TASK_RUNNER_PATH.read_text(encoding="utf-8", errors="replace")
    ast.parse(source)

    direct_calls = _collect_direct_calls(source)
    helper_presence = _collect_helper_presence(source)

    out: list[str] = []
    out.append("TaskRunner Registry Direct Admission Inventory")
    out.append("")
    out.append(f"generated_at: {_dt.datetime.now().isoformat(timespec='seconds')}")
    out.append(f"root: {ROOT}")
    out.append(f"target: {TASK_RUNNER_PATH.relative_to(ROOT)}")
    out.append("")

    out.append("Package24 Helper Presence")
    for symbol, count in helper_presence.items():
        out.append(f"- {symbol} count: {count}")
    out.append("")

    out.append("Direct Registry Call Inventory")
    out.append(f"total_direct_registry_calls: {len(direct_calls)}")
    if direct_calls:
        for item in direct_calls:
            out.append(
                f"- line {item['line']} | function={item['function']} | "
                f"owner={item['owner']} | method={item['method']} | source={item['source']}"
            )
    else:
        out.append("- no direct registry calls found")
    out.append("")

    out.append("Classification")
    out.append("- Package24 installed the unified TaskRunner admission helper.")
    out.append("- Package25 does not rewrite call sites blindly; it records exact direct registry call sites for the next reduction package.")
    out.append("- Calls in execute_owned_step/tick-related functions are the first Package26 migration candidates.")
    out.append("- Calls in repair/rollback/evidence paths must be reviewed before replacement because they may carry specialized payload semantics.")
    out.append("")

    out.append("Recommended Package26")
    out.append("- migrate direct registry calls in execute_owned_step and tick paths to _aer_registry_admit or the Package24 wrapper helpers")
    out.append("- preserve payload shape verified by tests/test_aer_mainline_closure_seal.py")
    out.append("- add a focused seal that monkeypatches _aer_registry_admit and proves owned-step/tick paths enter it")
    out.append("- keep repair/rollback registry calls unchanged until separately sealed")
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
    out.append("python -m pytest tests/test_taskrunner_registry_direct_admission_inventory.py tests/test_taskrunner_registry_admission_consolidation.py tests/test_taskrunner_aer_closure_inventory.py tests/test_aer_mainline_closure_seal.py -q")
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
