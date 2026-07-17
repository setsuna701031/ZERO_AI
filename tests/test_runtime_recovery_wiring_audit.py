from pathlib import Path

DOC = Path("docs/runtime_recovery_wiring_audit.md")


def test_wiring_audit_exists_and_is_non_executing():
    text = DOC.read_text(encoding="utf-8")
    assert "Package 219" in text
    assert "Runtime Wiring Audit" in text
    assert "Runtime Called | Recovery Executed" in text
    assert "primary entry candidate" in text
    assert "Final Decision" in text
    assert "GO" in text


def test_wiring_audit_forbids_runtime_behavior():
    text = DOC.read_text(encoding="utf-8")
    for phrase in [
        "No package in this audit may register hooks",
        "mutate runtime",
        "emit events",
        "execute Recovery",
        "not called",
    ]:
        assert phrase in text
