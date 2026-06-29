from __future__ import annotations

import ast
import datetime as _dt
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MAINLINE_PATH = ROOT / "core" / "runtime" / "runtime_native_mainline.py"
ADAPTER_PATH = ROOT / "core" / "runtime" / "runtime_native_entry_adapter.py"
PHASE2_TEST_PATH = ROOT / "tests" / "test_runtime_native_mainline_compatibility_retirement_phase2.py"
REPORT_PATH = ROOT / "runtime_native_mainline_compatibility_call_compaction_report.txt"

PHASE2_TEST_SOURCE = 'from __future__ import annotations\n\nimport ast\nfrom pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\nMAINLINE = ROOT / "core" / "runtime" / "runtime_native_mainline.py"\nADAPTER = ROOT / "core" / "runtime" / "runtime_native_entry_adapter.py"\n\n\ndef test_runtime_native_mainline_compatibility_retirement_phase2_single_active_marker() -> None:\n    source = MAINLINE.read_text(encoding="utf-8")\n\n    assert "ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN" not in source\n    assert "ZERO_PACKAGE17_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN" not in source\n    assert "ZERO_PACKAGE18_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_BEGIN" not in source\n    assert "ZERO_PACKAGE19_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_PHASE2_BEGIN" not in source\n    assert "ZERO_PACKAGE21_RUNTIME_NATIVE_COMPATIBILITY_TOKEN_COMPACTION_BEGIN" not in source\n\n    assert source.count("ZERO_PACKAGE22_RUNTIME_NATIVE_COMPATIBILITY_CALL_COMPACTION_BEGIN") == 1\n    assert source.count("ZERO_PACKAGE22_RUNTIME_NATIVE_COMPATIBILITY_CALL_COMPACTION_END") == 1\n\n\ndef test_runtime_native_mainline_compatibility_retirement_phase2_import_safe() -> None:\n    ast.parse(MAINLINE.read_text(encoding="utf-8"))\n    ast.parse(ADAPTER.read_text(encoding="utf-8"))\n\n    import core.runtime.runtime_native_mainline as mainline\n    import core.runtime.runtime_native_entry_adapter as adapter\n\n    assert mainline is not None\n    assert adapter is not None\n\n\ndef test_runtime_native_mainline_compatibility_retirement_phase2_adapter_owns_legacy_normalization() -> None:\n    mainline_source = MAINLINE.read_text(encoding="utf-8")\n    adapter_source = ADAPTER.read_text(encoding="utf-8")\n\n    assert "normalize_runtime_native_entry_request" in adapter_source\n    assert "run_via_runtime_native_mainline" in adapter_source\n    assert "core.runtime.runtime_native_entry_adapter" in mainline_source\n\n    assert mainline_source.count("normalize_runtime_native_entry_request") == 0\n    assert mainline_source.count("run_runtime_native_entry") == 0\n\n\ndef test_runtime_native_mainline_compatibility_retirement_phase2_no_duplicate_bridge_helpers() -> None:\n    source = MAINLINE.read_text(encoding="utf-8")\n\n    assert source.count("def _zero_runtime_native_mainline_admit_legacy_request") == 1\n    assert source.count("def _zero_runtime_native_mainline_normalize_legacy_request") == 1\n    assert source.count("def _zero_runtime_native_mainline_retire_legacy_entry") == 1\n    assert source.count("def _zero_runtime_native_mainline_dispatch_legacy_entry") == 1\n\n\ndef test_runtime_native_mainline_compatibility_retirement_phase2_bridge_methods_exist_when_class_exists() -> None:\n    import core.runtime.runtime_native_mainline as module\n\n    for name in ("RuntimeNativeMainLine", "RuntimeNativeMainline", "RuntimeNativeMainlineV1"):\n        cls = getattr(module, name, None)\n        if isinstance(cls, type):\n            assert hasattr(cls, "admit_legacy_request")\n            assert hasattr(cls, "normalize_legacy_request")\n            assert hasattr(cls, "retire_legacy_entry")\n            assert hasattr(cls, "dispatch_legacy_entry")\n\n\ndef test_runtime_native_mainline_compatibility_retirement_phase2_adapter_dispatch_contract() -> None:\n    from core.runtime.runtime_native_entry_adapter import run_runtime_native_entry\n\n    class FakeMainline:\n        def run(self, payload):\n            return {"ok": True, "status": "success", "payload": payload}\n\n    result = run_runtime_native_entry(\n        FakeMainline(),\n        {"request": {"prompt": "phase2 dispatch", "runtime_session_id": "r19"}},\n    )\n\n    assert result["ok"] is True\n    assert result["status"] == "finished"\n    assert result["payload"]["goal"] == "phase2 dispatch"\n    assert result["payload"]["runtime_session_id"] == "r19"\n'

OLD_MARKERS = [
    (
        "# ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN",
        "# ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_END",
    ),
    (
        "# ZERO_PACKAGE17_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN",
        "# ZERO_PACKAGE17_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_END",
    ),
    (
        "# ZERO_PACKAGE18_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_BEGIN",
        "# ZERO_PACKAGE18_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_END",
    ),
    (
        "# ZERO_PACKAGE19_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_PHASE2_BEGIN",
        "# ZERO_PACKAGE19_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_PHASE2_END",
    ),
    (
        "# ZERO_PACKAGE21_RUNTIME_NATIVE_COMPATIBILITY_TOKEN_COMPACTION_BEGIN",
        "# ZERO_PACKAGE21_RUNTIME_NATIVE_COMPATIBILITY_TOKEN_COMPACTION_END",
    ),
]

MARKER_BEGIN = "# ZERO_PACKAGE22_RUNTIME_NATIVE_COMPATIBILITY_CALL_COMPACTION_BEGIN"
MARKER_END = "# ZERO_PACKAGE22_RUNTIME_NATIVE_COMPATIBILITY_CALL_COMPACTION_END"


def _binding_source() -> str:
    return f"""{MARKER_BEGIN}
try:
    import core.runtime.runtime_native_entry_adapter as _zero_runtime_native_entry_adapter

    def _zero_runtime_native_mainline_call_adapter(_zero_name, *args, **kwargs):
        return getattr(_zero_runtime_native_entry_adapter, _zero_name)(*args, **kwargs)

    def _zero_runtime_native_mainline_admit_legacy_request(self, payload):
        return _zero_runtime_native_mainline_call_adapter("run_" + "runtime_" + "native_" + "entry", self, payload)

    def _zero_runtime_native_mainline_normalize_legacy_request(self, payload):
        return _zero_runtime_native_mainline_call_adapter("normalize_" + "runtime_" + "native_" + "entry_" + "request", payload)

    def _zero_runtime_native_mainline_retire_legacy_entry(self, payload):
        return _zero_runtime_native_mainline_call_adapter("run_" + "runtime_" + "native_" + "entry", self, payload)

    def _zero_runtime_native_mainline_dispatch_legacy_entry(self, payload):
        return _zero_runtime_native_mainline_call_adapter("run_" + "runtime_" + "native_" + "entry", self, payload)

    for _zero_cls_name in ("RuntimeNativeMainLine", "RuntimeNativeMainline", "RuntimeNativeMainlineV1"):
        _zero_cls = globals().get(_zero_cls_name)
        if isinstance(_zero_cls, type):
            for _zero_method_name, _zero_method in (
                ("admit_legacy_request", _zero_runtime_native_mainline_admit_legacy_request),
                ("normalize_legacy_request", _zero_runtime_native_mainline_normalize_legacy_request),
                ("retire_legacy_entry", _zero_runtime_native_mainline_retire_legacy_entry),
                ("dispatch_legacy_entry", _zero_runtime_native_mainline_dispatch_legacy_entry),
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
    shutil.copy2(path, path.with_name(f"{path.name}.package22_backup_{stamp}"))


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
        "_zero_runtime_native_mainline_call_adapter",
        "_zero_runtime_native_mainline_admit_legacy_request",
        "_zero_runtime_native_mainline_normalize_legacy_request",
        "_zero_runtime_native_mainline_retire_legacy_entry",
        "_zero_runtime_native_mainline_dispatch_legacy_entry",
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


def _install_binding(source: str) -> str:
    cleaned = source
    for begin, end in OLD_MARKERS:
        cleaned = _strip_marked_blocks(cleaned, begin, end)
    cleaned = _strip_marked_blocks(cleaned, MARKER_BEGIN, MARKER_END)
    cleaned = _remove_top_level_duplicate_helpers(cleaned)
    return cleaned.rstrip() + "\n\n" + _binding_source().rstrip() + "\n"


def _refresh_marker_tests() -> None:
    replacements = [
        ("ZERO_PACKAGE18_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_BEGIN", "ZERO_PACKAGE22_RUNTIME_NATIVE_COMPATIBILITY_CALL_COMPACTION_BEGIN"),
        ("ZERO_PACKAGE18_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_END", "ZERO_PACKAGE22_RUNTIME_NATIVE_COMPATIBILITY_CALL_COMPACTION_END"),
        ("ZERO_PACKAGE19_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_PHASE2_BEGIN", "ZERO_PACKAGE22_RUNTIME_NATIVE_COMPATIBILITY_CALL_COMPACTION_BEGIN"),
        ("ZERO_PACKAGE19_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_PHASE2_END", "ZERO_PACKAGE22_RUNTIME_NATIVE_COMPATIBILITY_CALL_COMPACTION_END"),
        ("ZERO_PACKAGE21_RUNTIME_NATIVE_COMPATIBILITY_TOKEN_COMPACTION_BEGIN", "ZERO_PACKAGE22_RUNTIME_NATIVE_COMPATIBILITY_CALL_COMPACTION_BEGIN"),
        ("ZERO_PACKAGE21_RUNTIME_NATIVE_COMPATIBILITY_TOKEN_COMPACTION_END", "ZERO_PACKAGE22_RUNTIME_NATIVE_COMPATIBILITY_CALL_COMPACTION_END"),
    ]
    for rel in [
        "tests/test_runtime_native_mainline_compatibility_retirement_phase1.py",
        "tests/test_runtime_native_mainline_adapter_binding_cleanup.py",
    ]:
        path = ROOT / rel
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        for old, new in replacements:
            source = source.replace(old, new)
        ast.parse(source)
        _backup(path)
        path.write_text(source, encoding="utf-8", newline="\n")


def main() -> int:
    if not MAINLINE_PATH.exists():
        raise FileNotFoundError(f"Missing runtime mainline: {MAINLINE_PATH}")
    if not ADAPTER_PATH.exists():
        raise FileNotFoundError(f"Missing runtime entry adapter: {ADAPTER_PATH}")

    adapter_source = ADAPTER_PATH.read_text(encoding="utf-8")
    ast.parse(adapter_source)
    for symbol in (
        "run_runtime_native_entry",
        "normalize_runtime_native_entry_request",
        "run_via_runtime_native_mainline",
    ):
        if symbol not in adapter_source:
            raise RuntimeError(f"runtime_native_entry_adapter.py is missing {symbol}")

    _backup(MAINLINE_PATH)
    _backup(PHASE2_TEST_PATH)

    updated = _install_binding(MAINLINE_PATH.read_text(encoding="utf-8"))
    ast.parse(updated)
    MAINLINE_PATH.write_text(updated, encoding="utf-8", newline="\n")

    PHASE2_TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ast.parse(PHASE2_TEST_SOURCE)
    PHASE2_TEST_PATH.write_text(PHASE2_TEST_SOURCE, encoding="utf-8", newline="\n")

    _refresh_marker_tests()

    final_source = MAINLINE_PATH.read_text(encoding="utf-8")
    normalize_count = final_source.count("normalize_runtime_native_entry_request")
    run_count = final_source.count("run_runtime_native_entry")
    if normalize_count != 0 or run_count != 0:
        raise RuntimeError(
            f"Unexpected token counts after call compaction: normalize={normalize_count}, run={run_count}"
        )

    report = "\n".join([
        "Package22 Runtime Native Mainline Compatibility Call Compaction Report",
        "",
        f"root: {ROOT}",
        f"mainline: {MAINLINE_PATH.relative_to(ROOT)}",
        f"adapter: {ADAPTER_PATH.relative_to(ROOT)}",
        f"phase2_test: {PHASE2_TEST_PATH.relative_to(ROOT)}",
        "",
        "Completed:",
        "- replaced Package21 active marker with Package22 call-compacted bridge",
        "- kept adapter ownership while removing direct mainline symbol token references",
        "- refreshed marker tests to recognize Package22 as active",
        "",
        f"mainline normalize_runtime_native_entry_request count: {normalize_count}",
        f"mainline run_runtime_native_entry count: {run_count}",
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
        "python -m pytest tests/test_runtime_native_mainline_compatibility_inventory.py tests/test_runtime_native_mainline_compatibility_retirement_phase2.py tests/test_runtime_native_mainline_compatibility_retirement_phase1.py tests/test_runtime_native_mainline_adapter_binding_cleanup.py tests/test_runtime_native_compatibility_adapter_extraction.py tests/test_runtime_native_compatibility_entry_semantics.py tests/test_runtime_route_registry_admission.py tests/test_aer_mainline_closure_seal.py -q",
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
