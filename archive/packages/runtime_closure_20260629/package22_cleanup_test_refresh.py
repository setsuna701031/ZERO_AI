from __future__ import annotations

import ast
import datetime as _dt
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TEST_PATH = ROOT / "tests" / "test_runtime_native_mainline_adapter_binding_cleanup.py"
REPORT_PATH = ROOT / "runtime_native_mainline_adapter_binding_cleanup_package22_refresh_report.txt"

TEST_SOURCE = 'from __future__ import annotations\n\nimport ast\nfrom pathlib import Path\n\n\nROOT = Path(__file__).resolve().parents[1]\nMAINLINE = ROOT / "core" / "runtime" / "runtime_native_mainline.py"\nADAPTER = ROOT / "core" / "runtime" / "runtime_native_entry_adapter.py"\n\n\ndef test_runtime_native_mainline_adapter_binding_cleanup_single_active_marker_block() -> None:\n    source = MAINLINE.read_text(encoding="utf-8")\n\n    assert "ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN" not in source\n    assert "ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_END" not in source\n    assert "ZERO_PACKAGE17_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN" not in source\n    assert "ZERO_PACKAGE17_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_END" not in source\n    assert "ZERO_PACKAGE18_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_BEGIN" not in source\n    assert "ZERO_PACKAGE18_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_END" not in source\n    assert "ZERO_PACKAGE19_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_PHASE2_BEGIN" not in source\n    assert "ZERO_PACKAGE19_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_PHASE2_END" not in source\n    assert "ZERO_PACKAGE21_RUNTIME_NATIVE_COMPATIBILITY_TOKEN_COMPACTION_BEGIN" not in source\n    assert "ZERO_PACKAGE21_RUNTIME_NATIVE_COMPATIBILITY_TOKEN_COMPACTION_END" not in source\n\n    assert source.count("ZERO_PACKAGE22_RUNTIME_NATIVE_COMPATIBILITY_CALL_COMPACTION_BEGIN") == 1\n    assert source.count("ZERO_PACKAGE22_RUNTIME_NATIVE_COMPATIBILITY_CALL_COMPACTION_END") == 1\n\n\ndef test_runtime_native_mainline_adapter_binding_cleanup_import_safe() -> None:\n    source = MAINLINE.read_text(encoding="utf-8")\n    ast.parse(source)\n\n    import core.runtime.runtime_native_mainline as module\n\n    assert module is not None\n\n\ndef test_runtime_native_mainline_adapter_binding_cleanup_keeps_adapter_external() -> None:\n    mainline_source = MAINLINE.read_text(encoding="utf-8")\n    adapter_source = ADAPTER.read_text(encoding="utf-8")\n\n    assert "core.runtime.runtime_native_entry_adapter" in mainline_source\n    assert "run_runtime_native_entry" in adapter_source\n    assert "normalize_runtime_native_entry_request" in adapter_source\n\n\ndef test_runtime_native_mainline_adapter_binding_cleanup_no_duplicate_binding_helpers() -> None:\n    source = MAINLINE.read_text(encoding="utf-8")\n\n    assert source.count("def _zero_runtime_native_mainline_admit_legacy_request") == 1\n    assert source.count("def _zero_runtime_native_mainline_normalize_legacy_request") == 1\n'


def _backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, path.with_name(f"{path.name}.package22_refresh_backup_{stamp}"))


def main() -> int:
    _backup(TEST_PATH)

    TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    ast.parse(TEST_SOURCE)
    TEST_PATH.write_text(TEST_SOURCE, encoding="utf-8", newline="\n")

    report = "\n".join([
        "Package22 Cleanup Test Refresh Report",
        "",
        f"root: {ROOT}",
        f"test: {TEST_PATH.relative_to(ROOT)}",
        "",
        "Completed:",
        "- refreshed cleanup seal to accept Package22 call-compacted bridge",
        "- moved run_runtime_native_entry / normalize_runtime_native_entry_request ownership checks to adapter file",
        "- retained mainline marker retirement checks",
        "- retained no-duplicate-helper checks",
        "",
        "Not touched:",
        "- core/runtime/runtime_native_mainline.py",
        "- core/runtime/runtime_native_entry_adapter.py",
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
