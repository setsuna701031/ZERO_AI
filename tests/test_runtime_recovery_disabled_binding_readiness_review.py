from pathlib import Path


def test_disabled_binding_readiness_review_exists():
    text = Path("docs/runtime_recovery_disabled_binding_readiness_review.md").read_text(encoding="utf-8")
    assert "Package 202" in text
    assert "GO" in text
    assert "Package 203" in text


def test_disabled_binding_readiness_confirms_no_runtime_actions():
    text = Path("docs/runtime_recovery_disabled_binding_readiness_review.md").read_text(encoding="utf-8")
    required = [
        "Recovery execution is not implemented.",
        "Runtime binding remains disabled.",
        "Runtime hooks are not registered.",
        "Runtime binding is not applied.",
        "Runtime surfaces are not touched.",
        "Events are not emitted.",
    ]
    for phrase in required:
        assert phrase in text


def test_package_sequence_appends_199_to_202():
    text = Path("docs/aer_evolution_v2_package_sequence.md").read_text(encoding="utf-8")
    for package in ("Package 199", "Package 200", "Package 201", "Package 202"):
        assert f"## {package}" in text
    assert "Disabled Runtime Recovery binding helper" in text
    assert "binding points report helper" in text
