from pathlib import Path


def test_aer_runtime_snapshot_contract_spec_exists_and_defines_boundary():
    spec = Path("docs/contracts/runtime/snapshot_v1.md")

    assert spec.exists()

    text = spec.read_text(encoding="utf-8")

    assert "aer.runtime.snapshot.v1" in text
    assert "Purpose" in text
    assert "Inputs" in text
    assert "Outputs" in text
    assert "Fixed public keys" in text
    assert "Vocabulary" in text
    assert "Forbidden leaks" in text
    assert "Object independence" in text
    assert "invalid upstream contract" in text
    assert "runtime_resume_marker" in text


def test_inventory_marks_snapshot_contract_spec_exists():
    inventory = Path("docs/contracts/runtime/inventory.md")

    assert inventory.exists()

    text = inventory.read_text(encoding="utf-8")

    assert "Snapshot" in text
    assert "docs/contracts/runtime/snapshot_v1.md" in text
    assert "Builder Implemented" in text
    assert "core/runtime/aer_runtime_snapshot.py" in text


def test_package_sequence_records_package_117():
    package_sequence = Path("docs/aer_evolution_v2_package_sequence.md")

    assert package_sequence.exists()

    text = package_sequence.read_text(encoding="utf-8")

    assert "Package 117: Snapshot Architecture + Contract Specification" in text
    assert "no runtime behavior changes" in text
    assert "no Snapshot implementation" in text
