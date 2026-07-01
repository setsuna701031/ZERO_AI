from pathlib import Path


def test_aer_runtime_contract_spec_layer_readme_exists_and_seals_authority():
    readme = Path("docs/contracts/runtime/README.md")

    assert readme.exists()

    text = readme.read_text(encoding="utf-8")

    assert "AER Runtime Contract Specifications" in text
    assert "Authority Order" in text
    assert "Dedicated contract specification" in text
    assert "Architecture constitutions define cross-layer rules only" in text
    assert "Layer-specific vocabulary belongs in dedicated contract specs" in text
    assert "Required Contract Spec Sections" in text
    assert "Fixed public keys" in text
    assert "Error projection rules" in text
    assert "Forbidden leaks" in text
    assert "Object independence" in text
    assert "Future Runtime Contracts" in text
    assert "resume_summary_v1.md" in text
    assert "snapshot_v1.md" in text
    assert "do not infer vocabulary" in text
