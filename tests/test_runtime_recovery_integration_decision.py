from pathlib import Path

DOC = Path("docs/runtime_recovery_integration_decision.md")


def test_integration_decision_go_for_disabled_only():
    text = DOC.read_text(encoding="utf-8")
    assert "Package 221" in text
    assert "GO for disabled runtime wiring entry readiness review" in text
    assert "NO-GO for active Recovery execution" in text
    assert "runtime_recovery_single_entry" in text


def test_integration_decision_rejects_active_paths():
    text = DOC.read_text(encoding="utf-8")
    for phrase in [
        "active runtime wiring",
        "Recovery execution",
        "scheduler integration",
        "operator integration",
        "event emission",
        "persistence, replay, audit, journal",
    ]:
        assert phrase in text
