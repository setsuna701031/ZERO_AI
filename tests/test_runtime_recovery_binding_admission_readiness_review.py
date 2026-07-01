from pathlib import Path


def test_binding_admission_readiness_review_exists():
    text = Path("docs/runtime_recovery_binding_admission_readiness_review.md").read_text(encoding="utf-8")
    assert "Package 206" in text
    assert "GO" in text
    assert "Package 207" in text


def test_binding_admission_readiness_confirms_disabled_admission():
    text = Path("docs/runtime_recovery_binding_admission_readiness_review.md").read_text(encoding="utf-8")
    required = [
        "Runtime binding admission remains disabled",
        "Runtime does not accept binding",
        "Runtime hooks are not registered",
        "Runtime binding is not applied",
        "Recovery remains disabled",
        "Events are not emitted",
        "Runtime state is not mutated",
    ]
    for phrase in required:
        assert phrase in text


def test_readiness_review_references_203_to_205():
    text = Path("docs/runtime_recovery_binding_admission_readiness_review.md").read_text(encoding="utf-8")
    for package in ("Package 203", "Package 204", "Package 205"):
        assert package in text
