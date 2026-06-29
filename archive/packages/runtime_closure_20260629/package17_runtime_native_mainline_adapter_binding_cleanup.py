from __future__ import annotations

import ast
import datetime as _dt
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MAINLINE_PATH = ROOT / "core" / "runtime" / "runtime_native_mainline.py"
TEST_PATH = ROOT / "tests" / "test_runtime_native_mainline_adapter_binding_cleanup.py"
REPORT_PATH = ROOT / "runtime_native_mainline_adapter_binding_cleanup_report.txt"

MARKER_BEGIN = "# ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN"
MARKER_END = "# ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_END"
MARKER_BEGIN_V17 = "# ZERO_PACKAGE17_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN"
MARKER_END_V17 = "# ZERO_PACKAGE17_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_END"

TEST_SOURCE = 'from __future__ import annotations\n\nimport ast\nfrom pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\nMAINLINE = ROOT / "core" / "runtime" / "runtime_native_mainline.py"\n\n\ndef test_runtime_native_mainline_adapter_binding_cleanup_single_marker_block() -> None:\n    source = MAINLINE.read_text(encoding="utf-8")\n\n    assert "ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN" not in source\n    assert "ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_END" not in source\n\n    assert source.count("ZERO_PACKAGE17_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN") == 1\n    assert source.count("ZERO_PACKAGE17_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_END") == 1\n\n\ndef test_runtime_native_mainline_adapter_binding_cleanup_import_safe() -> None:\n    source = MAINLINE.read_text(encoding="utf-8")\n    ast.parse(source)\n\n    import core.runtime.runtime_native_mainline as module\n\n    assert module is not None\n\n\ndef test_runtime_native_mainline_adapter_binding_cleanup_keeps_adapter_external() -> None:\n    source = MAINLINE.read_text(encoding="utf-8")\n\n    assert "core.runtime.runtime_native_entry_adapter" in source\n    assert "run_runtime_native_entry" in source\n    assert "normalize_runtime_native_entry_request" in source\n\n\ndef test_runtime_native_mainline_adapter_binding_cleanup_no_duplicate_binding_helpers() -> None:\n    source = MAINLINE.read_text(encoding="utf-8")\n\n    assert source.count("def _zero_runtime_native_mainline_admit_legacy_request") == 1\n    assert source.count("def _zero_runtime_native_mainline_normalize_legacy_request") == 1\n'


def _binding_source() -> str:
    return f"""{MARKER_BEGIN_V17}
try:
    from core.runtime.runtime_native_entry_adapter import (
        normalize_runtime_native_entry_request as _zero_normalize_runtime_native_entry_request,
        run_runtime_native_entry as _zero_run_runtime_native_entry,
    )

    def _zero_runtime_native_mainline_admit_legacy_request(self, payload):
        return _zero_run_runtime_native_entry(self, payload)

    def _zero_runtime_native_mainline_normalize_legacy_request(self, payload):
        return _zero_normalize_runtime_native_entry_request(payload)

    for _zero_cls_name in ("RuntimeNativeMainLine", "RuntimeNativeMainline", "RuntimeNativeMainlineV1"):
        _zero_cls = globals().get(_zero_cls_name)
        if isinstance(_zero_cls, type):
            if not hasattr(_zero_cls, "admit_legacy_request"):
                setattr(_zero_cls, "admit_legacy_request", _zero_runtime_native_mainline_admit_legacy_request)
            if not hasattr(_zero_cls, "normalize_legacy_request"):
                setattr(_zero_cls, "normalize_legacy_request", _zero_runtime_native_mainline_normalize_legacy_request)
except Exception:
    pass
{MARKER_END_V17}
"""


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path.with_name(f"{path.name}.package17_backup_{stamp}"))


def _strip_marked_blocks(source: str, begin: str, end: str) -> str:
    current = source
    while begin in current and end in current:
        before = current.split(begin, 1)[0].rstrip()
        tail = current.split(begin, 1)[1]
        after = tail.split(end, 1)[1].lstrip()
        current = before + "\n\n" + after
    return current


def _remove_unmarked_duplicate_helpers(source: str) -> str:
    tree = ast.parse(source)
    lines = source.splitlines()
    helper_names = {
        "_zero_runtime_native_mainline_admit_legacy_request",
        "_zero_runtime_native_mainline_normalize_legacy_request",
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


def _install_single_binding(source: str) -> str:
    cleaned = source
    cleaned = _strip_marked_blocks(cleaned, MARKER_BEGIN, MARKER_END)
    cleaned = _strip_marked_blocks(cleaned, MARKER_BEGIN_V17, MARKER_END_V17)
    cleaned = _remove_unmarked_duplicate_helpers(cleaned)
    return cleaned.rstrip() + "\n\n" + _binding_source().rstrip() + "\n"


def main() -> int:
    if not MAINLINE_PATH.exists():
        raise FileNotFoundError(f"Missing runtime mainline: {MAINLINE_PATH}")

    _backup(MAINLINE_PATH)
    _backup(TEST_PATH)

    source = MAINLINE_PATH.read_text(encoding="utf-8")
    updated = _install_single_binding(source)
    ast.parse(updated)
    MAINLINE_PATH.write_text(updated, encoding="utf-8", newline="\n")

    TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ast.parse(TEST_SOURCE)
    TEST_PATH.write_text(TEST_SOURCE, encoding="utf-8", newline="\n")

    report = "\n".join([
        "Package17 Runtime Native Mainline Adapter Binding Cleanup Report",
        "",
        f"root: {ROOT}",
        f"mainline: {MAINLINE_PATH.relative_to(ROOT)}",
        f"test: {TEST_PATH.relative_to(ROOT)}",
        "",
        "Completed:",
        "- removed Package16 adapter binding marker block",
        "- removed duplicate Package17 adapter binding marker block if present",
        "- installed exactly one Package17 import-safe adapter binding",
        "- added cleanup seal test",
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
        "python -m pytest tests/test_runtime_native_mainline_adapter_binding_cleanup.py tests/test_runtime_native_compatibility_adapter_extraction.py tests/test_runtime_native_compatibility_entry_semantics.py tests/test_runtime_route_registry_admission.py tests/test_aer_mainline_closure_seal.py -q",
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
