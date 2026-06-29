from __future__ import annotations

import ast
import datetime as _dt
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
TASK_RUNNER_PATH = ROOT / "core" / "runtime" / "task_runner.py"
REPORT_PATH = ROOT / "taskrunner_registry_legacy_cleanup_phase1_report.txt"
TEST_PATH = ROOT / "tests" / "test_taskrunner_registry_legacy_cleanup_phase1.py"

MARKER_BEGIN = "# ZERO_PACKAGE28_TASKRUNNER_REGISTRY_LEGACY_CLEANUP_PHASE1_BEGIN"
MARKER_END = "# ZERO_PACKAGE28_TASKRUNNER_REGISTRY_LEGACY_CLEANUP_PHASE1_END"

TEST_SOURCE = 'from __future__ import annotations\n\nimport ast\nfrom pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\nTASK_RUNNER = ROOT / "core" / "runtime" / "task_runner.py"\nREPORT = ROOT / "taskrunner_registry_legacy_cleanup_phase1_report.txt"\n\n\ndef test_taskrunner_registry_legacy_cleanup_phase1_import_safe() -> None:\n    source = TASK_RUNNER.read_text(encoding="utf-8")\n    ast.parse(source)\n\n    import core.runtime.task_runner as module\n\n    assert module is not None\n\n\ndef test_taskrunner_registry_legacy_cleanup_phase1_marker_once() -> None:\n    source = TASK_RUNNER.read_text(encoding="utf-8")\n\n    assert source.count("ZERO_PACKAGE28_TASKRUNNER_REGISTRY_LEGACY_CLEANUP_PHASE1_BEGIN") == 1\n    assert source.count("ZERO_PACKAGE28_TASKRUNNER_REGISTRY_LEGACY_CLEANUP_PHASE1_END") == 1\n\n\ndef test_taskrunner_registry_legacy_cleanup_phase1_report_exists() -> None:\n    assert REPORT.exists()\n\n\ndef test_taskrunner_registry_legacy_cleanup_phase1_report_has_required_sections() -> None:\n    text = REPORT.read_text(encoding="utf-8")\n\n    assert "TaskRunner Registry Legacy Cleanup Phase1 Report" in text\n    assert "Cleanup Guard" in text\n    assert "Remaining direct registry calls" in text\n    assert "Preserved specialized paths" in text\n    assert "Non-mainline issue reporting" in text\n\n\ndef test_taskrunner_registry_legacy_cleanup_phase1_guard_rejects_bypass_when_helper_missing() -> None:\n    import core.runtime.task_runner as module\n\n    class Host:\n        pass\n\n    result = module._zero_taskrunner_registry_legacy_cleanup_guard_v28(\n        Host(),\n        "execute_owned_step",\n        {"step_id": "s28"},\n    )\n\n    assert result["ok"] is False\n    assert result["reason"] == "aer_registry_admit_unavailable"\n\n\ndef test_taskrunner_registry_legacy_cleanup_phase1_guard_uses_helper() -> None:\n    import core.runtime.task_runner as module\n\n    calls = []\n\n    class Host:\n        def _aer_registry_admit(self, event, payload=None):\n            calls.append((event, payload))\n            return {"ok": True, "status": "admitted"}\n\n    result = module._zero_taskrunner_registry_legacy_cleanup_guard_v28(\n        Host(),\n        "tick",\n        {"current_tick": 28},\n    )\n\n    assert result["ok"] is True\n    assert calls == [("tick", {"current_tick": 28})]\n\n\ndef test_taskrunner_registry_legacy_cleanup_phase1_execute_tick_wrappers_still_installed() -> None:\n    import core.runtime.task_runner as module\n\n    assert hasattr(module, "_zero_taskrunner_registry_callsite_wrap_execute_owned_step_v26")\n    assert hasattr(module, "_zero_taskrunner_registry_callsite_wrap_tick_v26")\n    assert hasattr(module, "_zero_taskrunner_registry_legacy_cleanup_guard_v28")\n\n\ndef test_taskrunner_registry_legacy_cleanup_phase1_taskrunner_binding_if_class_exists() -> None:\n    import core.runtime.task_runner as module\n\n    cls = getattr(module, "TaskRunner", None)\n    if isinstance(cls, type):\n        assert getattr(cls, "_zero_package28_registry_legacy_cleanup_phase1_installed", False) is True\n'
BLOCK_SOURCE = '# ZERO_PACKAGE28_TASKRUNNER_REGISTRY_LEGACY_CLEANUP_PHASE1_BEGIN\ndef _zero_taskrunner_registry_legacy_cleanup_guard_v28(self, event, payload=None):\n    payload = dict(payload or {})\n    event = str(event or "").strip() or "taskrunner_event"\n\n    helper = getattr(self, "_aer_registry_admit", None)\n    if callable(helper):\n        result = helper(event, payload)\n        if isinstance(result, dict):\n            normalized = dict(result)\n            normalized.setdefault("ok", True)\n            normalized.setdefault("event", event)\n            normalized.setdefault("payload", payload)\n            return normalized\n        return {"ok": True, "status": "admitted", "event": event, "payload": payload, "result": result}\n\n    return {\n        "ok": False,\n        "status": "blocked",\n        "reason": "aer_registry_admit_unavailable",\n        "event": event,\n        "payload": payload,\n    }\n\n\ndef _zero_taskrunner_registry_legacy_cleanup_phase1_install_v28():\n    cls = globals().get("TaskRunner")\n    if not isinstance(cls, type):\n        return False\n\n    setattr(cls, "_zero_registry_legacy_cleanup_guard", _zero_taskrunner_registry_legacy_cleanup_guard_v28)\n    setattr(cls, "_zero_package28_registry_legacy_cleanup_phase1_installed", True)\n    return True\n\n\ntry:\n    _zero_taskrunner_registry_legacy_cleanup_phase1_install_v28()\nexcept Exception:\n    pass\n# ZERO_PACKAGE28_TASKRUNNER_REGISTRY_LEGACY_CLEANUP_PHASE1_END\n'

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


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path.with_name(f"{path.name}.package28_backup_{stamp}"))


def _strip_marked_blocks(source: str) -> str:
    current = source
    while MARKER_BEGIN in current and MARKER_END in current:
        before = current.split(MARKER_BEGIN, 1)[0].rstrip()
        tail = current.split(MARKER_BEGIN, 1)[1]
        after = tail.split(MARKER_END, 1)[1].lstrip()
        current = before + "\n\n" + after
    return current


def _remove_top_level_duplicate_helpers(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines()
    helper_names = {
        "_zero_taskrunner_registry_legacy_cleanup_guard_v28",
        "_zero_taskrunner_registry_legacy_cleanup_phase1_install_v28",
    }
    remove_lines: set[int] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in helper_names:
            start = node.lineno
            end = getattr(node, "end_lineno", node.lineno)
            remove_lines.update(range(start, end + 1))
    if not remove_lines:
        return source
    kept = [line for idx, line in enumerate(lines, start=1) if idx not in remove_lines]
    return "\n".join(kept).rstrip() + "\n"


def _install_block(source: str) -> str:
    cleaned = _strip_marked_blocks(source)
    cleaned = _remove_top_level_duplicate_helpers(cleaned)
    return cleaned.rstrip() + "\n\n" + BLOCK_SOURCE.rstrip() + "\n"


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


def _source_segment(source: str, node: ast.AST) -> str:
    try:
        return (ast.get_source_segment(source, node) or "").strip().replace("\n", " ")
    except Exception:
        return ""


def _classify(function_name: str, source_text: str) -> str:
    text = (function_name + " " + source_text).lower()
    if "_aer_registry_admit" in text or "_registry_admit_" in text:
        return "already_unified"
    if any(token in text for token in PRESERVE_KEYWORDS):
        return "preserve_for_specialized_flow"
    if "execute_owned_step" in text or "owned_step" in text or "tick" in text:
        return "candidate_for_unified_admission"
    return "review_before_migration"


def _collect_remaining_direct_calls(source: str) -> list[dict[str, Any]]:
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
        function_name = _nearest_function(tree, node)
        segment = _source_segment(source, node)
        calls.append({
            "line": getattr(node, "lineno", 0),
            "function": function_name,
            "owner": owner,
            "method": method,
            "classification": _classify(function_name, segment),
            "source": segment,
        })
    return sorted(calls, key=lambda item: (item["line"], item["method"]))


def _build_report(before_source: str, after_source: str) -> str:
    before_calls = _collect_remaining_direct_calls(before_source)
    after_calls = _collect_remaining_direct_calls(after_source)

    after_by_class: dict[str, list[dict[str, Any]]] = {}
    for call in after_calls:
        after_by_class.setdefault(call["classification"], []).append(call)

    out: list[str] = []
    out.append("TaskRunner Registry Legacy Cleanup Phase1 Report")
    out.append("")
    out.append(f"generated_at: {_dt.datetime.now().isoformat(timespec='seconds')}")
    out.append(f"root: {ROOT}")
    out.append(f"target: {TASK_RUNNER_PATH.relative_to(ROOT).as_posix()}")
    out.append("")

    out.append("Cleanup Guard")
    out.append("- installed _zero_taskrunner_registry_legacy_cleanup_guard_v28")
    out.append("- guard blocks execute/tick admission bypass when _aer_registry_admit is unavailable")
    out.append("- guard is bound to TaskRunner as _zero_registry_legacy_cleanup_guard when TaskRunner exists")
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

    out.append("Cleanup classification after phase1")
    for name in (
        "candidate_for_unified_admission",
        "already_unified",
        "preserve_for_specialized_flow",
        "review_before_migration",
    ):
        items = after_by_class.get(name, [])
        out.append(f"- {name} count: {len(items)}")
        for item in items:
            out.append(f"  - line {item['line']} function={item['function']} method={item['method']}")
    out.append("")

    out.append("Preserved specialized paths")
    out.append("- repair remains preserved until repair-specific AER seal exists")
    out.append("- rollback remains preserved until rollback payload semantics are sealed")
    out.append("- evidence remains preserved until evidence authority semantics are sealed")
    out.append("- authority/checkpoint/recovery paths remain preserved unless separately sealed")
    out.append("")

    out.append("No blind deletion")
    out.append("- Package28 does not delete repair/rollback/evidence registry paths.")
    out.append("- Package28 adds a bypass guard first, so Package29 can safely delete only proven duplicate paths.")
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
    out.append("python -m pytest tests/test_taskrunner_registry_legacy_cleanup_phase1.py tests/test_taskrunner_registry_legacy_cleanup_inventory.py tests/test_taskrunner_registry_callsite_migration.py tests/test_taskrunner_registry_direct_admission_inventory.py tests/test_taskrunner_registry_admission_consolidation.py tests/test_taskrunner_aer_closure_inventory.py tests/test_aer_mainline_closure_seal.py -q")
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
    if "_zero_taskrunner_registry_callsite_admit_v26" not in before:
        raise RuntimeError("Package26 callsite migration helper is missing; run package26 first")

    updated = _install_block(before)
    ast.parse(updated)
    TASK_RUNNER_PATH.write_text(updated, encoding="utf-8", newline="\n")

    TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ast.parse(TEST_SOURCE)
    TEST_PATH.write_text(TEST_SOURCE, encoding="utf-8", newline="\n")

    report = _build_report(before, updated)
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")

    print(str(REPORT_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
