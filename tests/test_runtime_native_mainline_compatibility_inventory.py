from __future__ import annotations

from pathlib import Path
import pytest

pytestmark = [pytest.mark.contract]




ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "runtime_native_mainline_compatibility_inventory.txt"


def test_runtime_native_mainline_compatibility_inventory_report_exists() -> None:
    assert REPORT.exists()


def test_runtime_native_mainline_compatibility_inventory_has_required_sections() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "Runtime Native Mainline Compatibility Inventory" in text
    assert "Token Inventory" in text
    assert "Marked Blocks" in text
    assert "Function Inventory" in text
    assert "Classification" in text
    assert "Non-mainline issue reporting" in text


def test_runtime_native_mainline_compatibility_inventory_records_phase2_marker() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "ZERO_PACKAGE19_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_PHASE2_BEGIN" in text
    assert "ZERO_PACKAGE19_RUNTIME_NATIVE_COMPATIBILITY_RETIREMENT_PHASE2_END" in text


def test_runtime_native_mainline_compatibility_inventory_records_normalize_count() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "normalize_runtime_native_entry_request" in text
    assert "count:" in text
