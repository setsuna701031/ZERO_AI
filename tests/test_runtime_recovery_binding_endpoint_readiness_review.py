from pathlib import Path


def test_endpoint_readiness_review_exists_and_allows_disabled_layer_only() -> None:
    text = Path("docs/runtime_recovery_binding_endpoint_readiness_review.md").read_text(encoding="utf-8")
    assert "Package 210" in text
    assert "runtime_recovery_binding_endpoint" in text
    assert "GO for Package 210 readiness as a disabled endpoint layer" in text
    assert "NO-GO for active Runtime wiring" in text
    assert "No Runtime hook registration" in text
    assert "No Recovery execution" in text


def test_endpoint_readiness_review_points_to_next_package() -> None:
    text = Path("docs/runtime_recovery_binding_endpoint_readiness_review.md").read_text(encoding="utf-8")
    assert "Package 211" in text
    assert "disabled Runtime wiring request intake" in text
