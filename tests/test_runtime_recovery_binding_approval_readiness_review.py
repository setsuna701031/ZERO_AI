from pathlib import Path


def test_binding_approval_readiness_review_exists_and_is_go():
    text = Path("docs/runtime_recovery_binding_approval_readiness_review.md").read_text(encoding="utf-8")
    assert "Package 194" in text
    assert "GO for passive binding approval readiness" in text
    assert "Recovery remains disabled" in text
    assert "Event emission remains disabled" in text
    assert "Runtime mainline wiring remains disabled" in text
    assert "Package 195" in text


def test_sequence_append_documents_packages_191_to_194():
    text = Path("docs/aer_evolution_v2_package_sequence_191_194_append.md").read_text(encoding="utf-8")
    for package in ("Package 191", "Package 192", "Package 193", "Package 194"):
        assert package in text
    assert "Final decision: GO" in text
    assert "Next package: Package 195" in text


def test_readiness_review_keeps_runtime_behavior_forbidden():
    text = Path("docs/runtime_recovery_binding_approval_readiness_review.md").read_text(encoding="utf-8")
    required = [
        "Binding application remains prohibited",
        "Runtime hook registration remains prohibited",
        "Recovery remains disabled",
        "Scheduler, Operator, Dispatcher, Supervisor, and Native Runtime are not called",
    ]
    for phrase in required:
        assert phrase in text
