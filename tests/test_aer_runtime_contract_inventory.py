from pathlib import Path


def test_aer_runtime_contract_inventory_exists_and_tracks_governance():
    inventory = Path("docs/contracts/runtime/inventory.md")

    assert inventory.exists()

    text = inventory.read_text(encoding="utf-8")

    assert "AER Runtime Contract Inventory" in text
    assert "Status Vocabulary" in text
    assert "Complete" in text
    assert "Missing Spec" in text
    assert "Not Started" in text
    assert "Blocked" in text
    assert "Bootstrap" in text
    assert "Resume Summary" in text
    assert "Snapshot" in text
    assert "Migration Priority" in text
    assert "resume_summary_v1.md" in text
    assert "Inventory tracks contract governance only" in text
