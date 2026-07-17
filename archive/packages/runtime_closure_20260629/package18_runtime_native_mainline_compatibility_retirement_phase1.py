from __future__ import annotations

import ast
import datetime as _dt
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MAINLINE_PATH = ROOT / "core" / "runtime" / "runtime_native_mainline.py"
ADAPTER_PATH = ROOT / "core" / "runtime" / "runtime_native_entry_adapter.py"
TEST_PATH = ROOT / "tests" / "test_runtime_native_mainline_compatibility_retirement_phase1.py"
REPORT_PATH = ROOT / "runtime_native_mainline_compatibility_retirement_phase1_report.txt"

OLD_MARKERS = [
    (
        "# ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN",
        "# ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_END",
    ),
    (
        "# ZERO_PACKAGE17_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN",
        "# ZERO_PACKAGE17_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_END",
    ),
]

MARKER_BEGIN = "# ZERO_PACKAGE18_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_BEGIN"
MARKER_END = "# ZERO_PACKAGE18_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_END"

TEST_SOURCE = 'from __future__ import annotations\n\nimport ast\nfrom pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\nMAINLINE = ROOT / "core" / "runtime" / "runtime_native_mainline.py"\nADAPTER = ROOT / "core" / "runtime" / "runtime_native_entry_adapter.py"\n\n\ndef test_runtime_native_mainline_compatibility_retirement_phase1_single_marker() -> None:\n    source = MAINLINE.read_text(encoding="utf-8")\n\n    assert "ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN" not in source\n    assert "ZERO_PACKAGE17_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN" not in source\n\n    assert source.count("ZERO_PACKAGE18_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_BEGIN") == 1\n    assert source.count("ZERO_PACKAGE18_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_END") == 1\n\n\ndef test_runtime_native_mainline_compatibility_retirement_phase1_import_safe() -> None:\n    ast.parse(MAINLINE.read_text(encoding="utf-8"))\n    ast.parse(ADAPTER.read_text(encoding="utf-8"))\n\n    import core.runtime.runtime_native_mainline as mainline\n    import core.runtime.runtime_native_entry_adapter as adapter\n\n    assert mainline is not None\n    assert adapter is not None\n\n\ndef test_runtime_native_mainline_compatibility_retirement_phase1_keeps_adapter_as_owner() -> None:\n    mainline_source = MAINLINE.read_text(encoding="utf-8")\n    adapter_source = ADAPTER.read_text(encoding="utf-8")\n\n    assert "core.runtime.runtime_native_entry_adapter" in mainline_source\n    assert "run_runtime_native_entry" in adapter_source\n    assert "normalize_runtime_native_entry_request" in adapter_source\n\n\ndef test_runtime_native_mainline_compatibility_retirement_phase1_no_duplicate_bridge_helpers() -> None:\n    source = MAINLINE.read_text(encoding="utf-8")\n\n    assert source.count("def _zero_runtime_native_mainline_admit_legacy_request") == 1\n    assert source.count("def _zero_runtime_native_mainline_normalize_legacy_request") == 1\n    assert source.count("def _zero_runtime_native_mainline_retire_legacy_entry") == 1\n\n\ndef test_runtime_native_mainline_compatibility_retirement_phase1_adapter_dispatches_legacy_payload() -> None:\n    from core.runtime.runtime_native_entry_adapter import run_runtime_native_entry\n\n    class FakeMainline:\n        def run(self, payload):\n            return {"ok": True, "status": "success", "payload": payload}\n\n    result = run_runtime_native_entry(\n        FakeMainline(),\n        {"payload": {"instruction": "retire compatibility phase1", "session_id": "s18"}},\n    )\n\n    assert result["ok"] is True\n    assert result["status"] == "finished"\n    assert result["payload"]["goal"] == "retire compatibility phase1"\n    assert result["payload"]["session_id"] == "s18"\n'


def _binding_source() -> str:
    return f"""{MARKER_BEGIN}
try:
    from core.runtime.runtime_native_entry_adapter import (
        normalize_runtime_native_entry_request as _zero_normalize_runtime_native_entry_request,
        run_runtime_native_entry as _zero_run_runtime_native_entry,
    )

    def _zero_runtime_native_mainline_admit_legacy_request(self, payload):
        return _zero_run_runtime_native_entry(self, payload)

    def _zero_runtime_native_mainline_normalize_legacy_request(self, payload):
        return _zero_normalize_runtime_native_entry_request(payload)

    def _zero_runtime_native_mainline_retire_legacy_entry(self, payload):
        return _zero_run_runtime_native_entry(self, payload)

    for _zero_cls_name in ("RuntimeNativeMainLine", "RuntimeNativeMainline", "RuntimeNativeMainlineV1"):
        _zero_cls = globals().get(_zero_cls_name)
        if isinstance(_zero_cls, type):
            for _zero_method_name, _zero_method in (
                ("admit_legacy_request", _zero_runtime_native_mainline_admit_legacy_request),
                ("normalize_legacy_request", _zero_runtime_native_mainline_normalize_legacy_request),
                ("retire_legacy_entry", _zero_runtime_native_mainline_retire_legacy_entry),
            ):
                if not hasattr(_zero_cls, _zero_method_name):
                    setattr(_zero_cls, _zero_method_name, _zero_method)
except Exception:
    pass
{MARKER_END}
"""


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path.with_name(f"{path.name}.package18_backup_{stamp}"))


def _strip_marked_blocks(source: str, begin: str, end: str) -> str:
    current = source
    while begin in current and end in current:
        before = current.split(begin, 1)[0].rstrip()
        tail = current.split(begin, 1)[1]
        after = tail.split(end, 1)[1].lstrip()
        current = before + "\n\n" + after
    return current


def _remove_top_level_duplicate_helpers(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines()
    helper_names = {
        "_zero_runtime_native_mainline_admit_legacy_request",
        "_zero_runtime_native_mainline_normalize_legacy_request",
        "_zero_runtime_native_mainline_retire_legacy_entry",
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


def _install_phase1_binding(source: str) -> str:
    cleaned = source
    for begin, end in OLD_MARKERS:
        cleaned = _strip_marked_blocks(cleaned, begin, end)
    cleaned = _strip_marked_blocks(cleaned, MARKER_BEGIN, MARKER_END)
    cleaned = _remove_top_level_duplicate_helpers(cleaned)
    return cleaned.rstrip() + "\n\n" + _binding_source().rstrip() + "\n"


def main() -> int:
    if not MAINLINE_PATH.exists():
        raise FileNotFoundError(f"Missing runtime mainline: {MAINLINE_PATH}")
    if not ADAPTER_PATH.exists():
        raise FileNotFoundError(f"Missing runtime entry adapter: {ADAPTER_PATH}")

    _backup(MAINLINE_PATH)
    _backup(TEST_PATH)

    adapter_source = ADAPTER_PATH.read_text(encoding="utf-8")
    ast.parse(adapter_source)
    if "run_runtime_native_entry" not in adapter_source:
        raise RuntimeError("runtime_native_entry_adapter.py is missing run_runtime_native_entry")
    if "normalize_runtime_native_entry_request" not in adapter_source:
        raise RuntimeError("runtime_native_entry_adapter.py is missing normalize_runtime_native_entry_request")

    mainline_source = MAINLINE_PATH.read_text(encoding="utf-8")
    updated_mainline = _install_phase1_binding(mainline_source)
    ast.parse(updated_mainline)
    MAINLINE_PATH.write_text(updated_mainline, encoding="utf-8", newline="\n")

    TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ast.parse(TEST_SOURCE)
    TEST_PATH.write_text(TEST_SOURCE, encoding="utf-8", newline="\n")

    report = "\n".join([
        "Package18 Runtime Native Mainline Compatibility Retirement Phase1 Report",
        "",
        f"root: {ROOT}",
        f"mainline: {MAINLINE_PATH.relative_to(ROOT)}",
        f"adapter: {ADAPTER_PATH.relative_to(ROOT)}",
        f"test: {TEST_PATH.relative_to(ROOT)}",
        "",
        "Completed:",
        "- retired Package16/Package17 marker blocks from runtime_native_mainline.py",
        "- installed one Package18 compatibility-retirement bridge block",
        "- kept runtime_native_entry_adapter.py as compatibility owner",
        "- added retire_legacy_entry bridge for phase1 callers",
        "- added phase1 seal test",
        "",
        "Not touched:",
        "- Scheduler",
        "- TaskRunner",
        "- AgentLoop",
        "- CLI",
        "- RuntimeRouteRegistry",
        "",
        "Validation:",
        "python -m compileall core/runtime tests",
        "python -m pytest tests/test_runtime_native_mainline_compatibility_retirement_phase1.py tests/test_runtime_native_mainline_adapter_binding_cleanup.py tests/test_runtime_native_compatibility_adapter_extraction.py tests/test_runtime_native_compatibility_entry_semantics.py tests/test_runtime_route_registry_admission.py tests/test_aer_mainline_closure_seal.py -q",
        "",
        "Non-mainline issue reporting:",
        "Any unrelated issue discovered during validation must be reported explicitly and not silently skipped.",
        "",
    ])
    REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")
    print(str(REPORT_PATH))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
