from pathlib import Path

DOC = Path("docs/runtime_recovery_wiring_entry_readiness_review.md")


def test_wiring_entry_readiness_review_go_and_next_package():
    text = DOC.read_text(encoding="utf-8")
    assert "Package 222" in text
    assert "Final Decision" in text
    assert "GO" in text
    assert "Package 223: Disabled Runtime Wiring Entry Contract" in text


def test_wiring_entry_readiness_review_does_not_authorize_activation():
    text = DOC.read_text(encoding="utf-8")
    for phrase in [
        "does not authorize Recovery execution",
        "runtime mainline activation",
        "hook registration",
        "event emission",
        "runtime mutation",
    ]:
        assert phrase in text
