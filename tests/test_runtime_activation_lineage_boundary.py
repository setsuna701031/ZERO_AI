from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BOUNDARY = ROOT / "docs/runtime_activation_lineage_boundary.md"
GAP = ROOT / "docs/runtime_activation_lineage_gap_inventory.md"
READY = ROOT / "docs/runtime_activation_lineage_readiness_review.md"
SEQ = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def read(p):
    assert p.exists()
    return p.read_text(encoding="utf-8").lower()


def test_lineage_docs_exist():
    assert BOUNDARY.exists()
    assert GAP.exists()
    assert READY.exists()


def test_activation_lineage_chain_required():
    text = read(BOUNDARY)
    assert "activation request lineage is required" in text
    assert "operator approval lineage is required" in text
    assert "authorization lineage is required" in text
    assert "evidence lineage is required" in text


def test_lineage_continuity_required():
    text = read(BOUNDARY)
    assert "lineage continuity is required" in text
    assert "broken lineage is no-go" in text
    assert "cross-request lineage reuse is no-go" in text


def test_scheduler_executor_cannot_fabricate_lineage():
    text = read(BOUNDARY)
    assert "lineage must not be fabricated by scheduler" in text
    assert "lineage must not be fabricated by executor" in text


def test_recovery_cannot_reuse_lineage():
    text = read(BOUNDARY)
    assert "recovery must not reuse previous activation lineage" in text


def test_no_runtime_lineage_implementation_added():
    text = read(GAP)
    assert "no executable activation lineage flow exists" in text
    assert "no lineage storage exists" in text
    assert "no lineage verification exists" in text


def test_runtime_remains_disabled():
    combined = read(BOUNDARY) + read(READY)
    assert "runtime activation: disabled" in combined
    assert "recovery activation: disabled" in combined
    assert "runtime mutation: forbidden" in combined


def test_package_sequence_records_617_624():
    text = read(SEQ)
    assert "packages 617-624" in text or "packages 617–624" in text
    assert "runtime activation lineage boundary" in text
