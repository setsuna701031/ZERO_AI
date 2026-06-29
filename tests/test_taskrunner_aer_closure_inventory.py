from __future__ import annotations

from pathlib import Path
import pytest

pytestmark = [pytest.mark.contract]




ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "taskrunner_aer_closure_inventory.txt"


def test_taskrunner_aer_closure_inventory_report_exists() -> None:
    assert REPORT.exists()


def test_taskrunner_aer_closure_inventory_has_required_sections() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "TaskRunner AER Closure Inventory" in text
    assert "Target Files" in text
    assert "Token Inventory" in text
    assert "Function Inventory" in text
    assert "Classification" in text
    assert "Recommended Package24" in text


def test_taskrunner_aer_closure_inventory_mentions_task_runner() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "core/runtime/task_runner.py" in text
    assert "tests/test_aer_mainline_closure_seal.py" in text


def test_taskrunner_aer_closure_inventory_records_non_mainline_issue_rule() -> None:
    text = REPORT.read_text(encoding="utf-8")

    assert "Non-mainline issue reporting" in text
    assert "must be reported explicitly" in text
