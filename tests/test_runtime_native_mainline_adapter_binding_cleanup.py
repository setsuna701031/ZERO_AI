from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAINLINE = ROOT / "core" / "runtime" / "runtime_native_mainline.py"
ADAPTER = ROOT / "core" / "runtime" / "runtime_native_entry_adapter.py"


def test_runtime_native_mainline_adapter_binding_cleanup_single_active_marker_block() -> None:
    source = MAINLINE.read_text(encoding="utf-8")

    assert "ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN" not in source
    assert "ZERO_PACKAGE16_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_END" not in source
    assert "ZERO_PACKAGE17_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_BEGIN" not in source
    assert "ZERO_PACKAGE17_RUNTIME_NATIVE_ENTRY_ADAPTER_BINDING_END" not in source
    assert "ZERO_PACKAGE18_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_BEGIN" not in source
    assert "ZERO_PACKAGE18_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_END" not in source
    assert "ZERO_PACKAGE19_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_PHASE2_BEGIN" not in source
    assert "ZERO_PACKAGE19_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_PHASE2_END" not in source
    assert "ZERO_PACKAGE21_RUNTIME_NATIVE_COMPATIBILITY_TOKEN_COMPACTION_BEGIN" not in source
    assert "ZERO_PACKAGE21_RUNTIME_NATIVE_COMPATIBILITY_TOKEN_COMPACTION_END" not in source

    assert source.count("ZERO_PACKAGE22_RUNTIME_NATIVE_COMPATIBILITY_CALL_COMPACTION_BEGIN") == 1
    assert source.count("ZERO_PACKAGE22_RUNTIME_NATIVE_COMPATIBILITY_CALL_COMPACTION_END") == 1


def test_runtime_native_mainline_adapter_binding_cleanup_import_safe() -> None:
    source = MAINLINE.read_text(encoding="utf-8")
    ast.parse(source)

    import core.runtime.runtime_native_mainline as module

    assert module is not None


def test_runtime_native_mainline_adapter_binding_cleanup_keeps_adapter_external() -> None:
    mainline_source = MAINLINE.read_text(encoding="utf-8")
    adapter_source = ADAPTER.read_text(encoding="utf-8")

    assert "core.runtime.runtime_native_entry_adapter" in mainline_source
    assert "run_runtime_native_entry" in adapter_source
    assert "normalize_runtime_native_entry_request" in adapter_source


def test_runtime_native_mainline_adapter_binding_cleanup_no_duplicate_binding_helpers() -> None:
    source = MAINLINE.read_text(encoding="utf-8")

    assert source.count("def _zero_runtime_native_mainline_admit_legacy_request") == 1
    assert source.count("def _zero_runtime_native_mainline_normalize_legacy_request") == 1
