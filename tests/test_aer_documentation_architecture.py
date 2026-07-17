from pathlib import Path


def test_aer_documentation_architecture_exists_and_defines_boundaries():
    document = Path("docs/aer_documentation_architecture.md")

    assert document.exists()

    text = document.read_text(encoding="utf-8")

    assert "AER Documentation Architecture" in text
    assert "Documentation Layers" in text
    assert "Constitution" in text
    assert "Contract Specification" in text
    assert "Inventory" in text
    assert "Package Sequence" in text
    assert "Template" in text
    assert "Roadmap" in text
    assert "Authority Flow" in text
    assert "Lifecycle" in text
    assert "Single Responsibility Rule" in text
    assert "Do not use Constitution as API reference" in text
    assert "Do not use Inventory as roadmap" in text
    assert "Do not use Package Sequence as contract specification" in text
    assert "Runtime Contract Governance" in text
    assert "If no spec exists" in text
    assert "Migration Rule" in text
