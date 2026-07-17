from pathlib import Path


def test_activation_gate_readiness_review_exists_and_is_go() -> None:
    text = Path("docs/runtime_recovery_activation_gate_readiness_review.md").read_text(encoding="utf-8")
    assert "Package 214" in text
    assert "Final decision: GO" in text
    assert "Package 215" in text


def test_activation_gate_readiness_review_keeps_recovery_disabled() -> None:
    text = Path("docs/runtime_recovery_activation_gate_readiness_review.md").read_text(encoding="utf-8")
    for phrase in [
        "gate is closed",
        "Recovery is disabled",
        "Runtime mainline wiring is still disabled",
        "endpoint invocation remains prohibited",
        "runtime hook registration",
        "runtime binding application",
        "Recovery execution",
    ]:
        assert phrase in text


def test_package_sequence_includes_211_to_214() -> None:
    text = Path("docs/aer_evolution_v2_package_sequence.md").read_text(encoding="utf-8")
    for package in ["Package 211", "Package 212", "Package 213", "Package 214"]:
        assert package in text
    assert "Runtime Recovery Activation Gate Contract" in text
    assert "Runtime Recovery Activation Gate Helper" in text
    assert "Runtime Recovery Activation Gate Report" in text
    assert "Runtime Recovery Activation Gate Readiness Review" in text
