from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "docs" / "runtime_recovery_gap_closure_inventory.md"


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_gap_closure_inventory_exists() -> None:
    text = _text()
    assert "Package 196" in text
    assert "Runtime Recovery Gap Closure Inventory" in text


def test_gap_closure_inventory_records_known_gap_closure() -> None:
    text = _text()
    assert "Package 181 binding policy was missing" in text
    assert "Package 183 through Package 185" in text
    assert "were closed" in text


def test_gap_closure_inventory_reports_no_new_blocking_gap() -> None:
    text = _text()
    assert "No new blocking Recovery planning gap" in text
    assert "Runtime integration may start only as disabled skeleton work" in text


def test_gap_closure_inventory_keeps_non_mainline_reporting() -> None:
    assert "must not be silently skipped" in _text()
