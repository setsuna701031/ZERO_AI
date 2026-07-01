from __future__ import annotations

from pathlib import Path

DOC = Path("docs/runtime_recovery_preflight_readiness_review.md")
SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_preflight_readiness_review_exists() -> None:
    assert DOC.exists()
    assert "# Runtime Recovery Preflight Readiness Review" in _text()


def test_preflight_readiness_review_closes_packages_183_through_185() -> None:
    text = _text()
    for phrase in (
        "Package 183: Runtime Recovery Preflight Eligibility Contract",
        "Package 184: Runtime Recovery Preflight Eligibility Helper",
        "Package 185: Runtime Recovery Preflight Report Contract",
    ):
        assert phrase in text


def test_preflight_readiness_review_preserves_non_execution_boundaries() -> None:
    text = _text()
    for phrase in (
        "Recovery remains disabled",
        "Runtime binding remains disallowed",
        "Runtime mainline wiring remains disallowed",
        "Recovery execution remains disallowed",
        "Event emission remains disallowed",
        "Runtime surfaces remain untouched",
        "does not activate Recovery",
        "does not emit runtime events or mutate runtime state",
    ):
        assert phrase in text


def test_preflight_readiness_review_go_next_package() -> None:
    text = _text()
    assert "Final decision: GO." in text
    assert "Package 187: Runtime Recovery Controlled Binding Candidate." in text


def test_package_sequence_appends_183_to_186() -> None:
    text = SEQUENCE.read_text(encoding="utf-8")
    for package in ("Package 183", "Package 184", "Package 185", "Package 186"):
        assert f"## {package}" in text
    assert "Next package: Package 187." in text
