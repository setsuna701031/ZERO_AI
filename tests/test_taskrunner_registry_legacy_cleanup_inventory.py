from __future__ import annotations

from pathlib import Path
import pytest

pytestmark = [pytest.mark.contract]




ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "taskrunner_registry_legacy_cleanup_inventory.txt"


def test_taskrunner_registry_legacy_cleanup_inventory_report_exists() -> None:
    assert REPORT.exists()


def test_taskrunner_registry_legacy_cleanup_inventory_has_required_sections() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "TaskRunner Registry Legacy Cleanup Inventory" in text
    assert "Package24/26 Helper Presence" in text
    assert "Remaining Direct Registry Calls" in text
    assert "Cleanup Classification" in text
    assert "Recommended Package28" in text
    assert "Non-mainline issue reporting" in text


def test_taskrunner_registry_legacy_cleanup_inventory_mentions_preserved_paths() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "repair" in text
    assert "rollback" in text
    assert "evidence" in text


def test_taskrunner_registry_legacy_cleanup_inventory_mentions_target() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "core/runtime/task_runner.py" in text
    assert "_aer_registry_admit" in text
