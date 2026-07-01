from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "docs" / "runtime_recovery_architecture_milestone_review.md"


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_milestone_review_exists_and_go() -> None:
    text = _text()
    assert "Package 195" in text
    assert "Final decision: GO" in text
    assert "GO for Runtime Recovery integration preparation" in text


def test_milestone_review_preserves_non_executing_boundary() -> None:
    text = _text()
    required = [
        "do not execute Recovery",
        "do not enable Recovery by default",
        "do not activate runtime mainline wiring",
        "do not apply binding",
        "do not register runtime hooks",
        "do not emit real runtime events",
        "do not mutate runtime state",
    ]
    for phrase in required:
        assert phrase in text


def test_milestone_review_lists_completed_layers() -> None:
    text = _text()
    for phrase in [
        "Recovery activation contract",
        "Passive adapters",
        "Kill switch",
        "Canonical event route",
        "Binding approval report",
    ]:
        assert phrase in text


def test_milestone_review_points_to_gap_inventory() -> None:
    assert "GO for Package 196" in _text()
