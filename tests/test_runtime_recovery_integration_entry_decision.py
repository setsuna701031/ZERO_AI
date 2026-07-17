from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "docs" / "runtime_recovery_integration_entry_decision.md"


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_entry_decision_exists_and_go() -> None:
    text = _text()
    assert "Package 197" in text
    assert "Final decision: GO" in text
    assert "disabled runtime binding skeleton work" in text


def test_entry_decision_allows_only_disabled_skeleton() -> None:
    text = _text()
    assert "inert runtime binding skeleton surfaces" in text
    assert "consume approved binding reports as plain data" in text
    assert "deterministic plain dict reports" in text


def test_entry_decision_forbids_active_runtime_work() -> None:
    text = _text()
    for phrase in [
        "active runtime hooks",
        "runtime hook registration",
        "Recovery execution",
        "state mutation",
        "event emission",
        "automatic enablement",
    ]:
        assert phrase in text


def test_entry_decision_preserves_gates() -> None:
    text = _text()
    for phrase in [
        "single-entry only",
        "kill switch safe/off by default",
        "canonical event schema preservation",
        "binding approval as data only",
    ]:
        assert phrase in text
