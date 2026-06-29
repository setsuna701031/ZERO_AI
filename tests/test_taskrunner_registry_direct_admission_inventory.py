from __future__ import annotations

from pathlib import Path
import pytest

pytestmark = [pytest.mark.contract]




ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "taskrunner_registry_direct_admission_inventory.txt"


def test_taskrunner_registry_direct_admission_inventory_report_exists() -> None:
    assert REPORT.exists()


def test_taskrunner_registry_direct_admission_inventory_has_required_sections() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "TaskRunner Registry Direct Admission Inventory" in text
    assert "Direct Registry Call Inventory" in text
    assert "Package24 Helper Presence" in text
    assert "Recommended Package26" in text
    assert "Non-mainline issue reporting" in text


def test_taskrunner_registry_direct_admission_inventory_mentions_package24_helper() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "_zero_taskrunner_registry_admit_aer_closure_v24" in text
    assert "_aer_registry_admit" in text


def test_taskrunner_registry_direct_admission_inventory_mentions_target() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "core/runtime/task_runner.py" in text
