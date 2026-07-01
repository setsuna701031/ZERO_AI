from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "docs" / "runtime_recovery_milestone_readiness_seal.md"
SEQUENCE = Path(__file__).resolve().parents[1] / "docs" / "aer_evolution_v2_package_sequence.md"


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_milestone_readiness_seal_exists_and_go() -> None:
    text = _text()
    assert "Package 198" in text
    assert "Final decision: GO" in text
    assert "disabled runtime binding skeleton work only" in text


def test_milestone_readiness_seal_preserves_disabled_state() -> None:
    text = _text()
    for phrase in [
        "Recovery remains disabled",
        "Kill switch remains off/safe by default",
        "Canonical event remains preserved without emission",
        "deterministic plain dict reports",
    ]:
        assert phrase in text


def test_milestone_readiness_seal_names_next_package() -> None:
    assert "Package 199: Runtime Recovery Disabled Binding Skeleton Contract" in _text()


def test_package_sequence_appended_for_195_through_198() -> None:
    text = SEQUENCE.read_text(encoding="utf-8")
    for package in ["Package 195", "Package 196", "Package 197", "Package 198"]:
        assert package in text
    assert "Runtime Recovery Milestone Readiness Seal" in text
