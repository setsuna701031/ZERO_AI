from pathlib import Path


def test_aer_governance_closure_review_exists_and_records_go_decision():
    document = Path("docs/aer_governance_closure_review.md")

    assert document.exists()

    text = document.read_text(encoding="utf-8")

    assert "AER Governance Closure Review" in text
    assert "Authority Closure" in text
    assert "Responsibility Closure" in text
    assert "Contract Closure" in text
    assert "Workflow Closure" in text
    assert "Runtime Resumption Decision" in text
    assert "GO" in text
    assert "NO-GO" in text
    assert "Package 117: AER Runtime Snapshot Contract Specification" in text
    assert "Do not implement Snapshot in this package" in text
    assert "Constitution is not API reference" in text
    assert "Inventory is not vocabulary authority" in text
    assert "Package sequence is not contract authority" in text
