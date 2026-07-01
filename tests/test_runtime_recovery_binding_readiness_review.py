from pathlib import Path


def test_binding_readiness_review_exists_and_is_go() -> None:
    text = Path("docs/runtime_recovery_binding_readiness_review.md").read_text(encoding="utf-8")

    assert "Package 190" in text
    assert "GO for passive Runtime Recovery binding framework closure" in text
    assert "Package 191" in text


def test_binding_readiness_review_preserves_passive_boundaries() -> None:
    text = Path("docs/runtime_recovery_binding_readiness_review.md").read_text(encoding="utf-8")

    for phrase in (
        "The framework is single-entry only",
        "The registry is passive and does not register runtime hooks",
        "The plan is passive and does not apply runtime binding",
        "Recovery remains disabled",
        "Runtime mainline wiring remains disallowed",
        "Event emission remains disallowed",
        "Runtime mutation remains disallowed",
        "Canonical event data remains preserved as contract data only",
    ):
        assert phrase in text


def test_binding_readiness_review_lists_no_go_conditions() -> None:
    text = Path("docs/runtime_recovery_binding_readiness_review.md").read_text(encoding="utf-8")

    for token in (
        "registers a runtime hook",
        "enables Recovery",
        "emits an event",
        "mutates runtime state",
        "calls runtime behavior",
        "performs file IO",
    ):
        assert token in text
