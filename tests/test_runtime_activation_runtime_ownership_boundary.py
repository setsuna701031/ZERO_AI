from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BOUNDARY = ROOT / "docs/runtime_activation_runtime_ownership_boundary.md"
GAP = ROOT / "docs/runtime_activation_runtime_ownership_gap_inventory.md"
READY = ROOT / "docs/runtime_activation_runtime_ownership_readiness_review.md"
SEQ = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def read(p):
    assert p.exists()
    return p.read_text(encoding="utf-8").lower()


def test_runtime_ownership_docs_exist():
    assert BOUNDARY.exists()
    assert GAP.exists()
    assert READY.exists()


def test_active_state_is_not_ownership_authority():
    text = read(BOUNDARY)
    assert "active state is not ownership authority" in text
    assert "active state is not scheduler ownership" in text
    assert "active state is not executor ownership" in text
    assert "active state is not recovery ownership" in text
    assert "active state is not operator ownership" in text


def test_active_runtime_ownership_must_be_explicit():
    text = read(BOUNDARY)
    assert "active runtime ownership must be explicitly defined" in text
    assert "runtime owner must be separate from scheduler and executor" in text


def test_scheduler_executor_recovery_cannot_claim_ownership():
    text = read(BOUNDARY)
    assert "scheduler must not claim runtime ownership" in text
    assert "executor must not claim runtime ownership" in text
    assert "recovery must not claim runtime ownership" in text


def test_operator_remains_approval_only():
    text = read(BOUNDARY)
    assert "operator remains approval authority only" in text
    assert "operator remains owner of approval only" in text


def test_no_runtime_ownership_implementation_added():
    text = read(GAP)
    assert "no executable runtime ownership flow exists" in text
    assert "no active runtime ownership model exists" in text
    assert "no runtime owner resolver exists" in text
    assert "no ownership evidence model exists" in text
    assert "no ownership audit model exists" in text
    assert "no ownership lineage model exists" in text


def test_runtime_ownership_no_go_rules_exist():
    text = read(READY)
    assert "active runtime ownership is missing" in text
    assert "active state grants scheduler ownership" in text
    assert "active state grants executor ownership" in text
    assert "active state grants recovery ownership" in text
    assert "active state grants operator ownership" in text
    assert "scheduler claims runtime ownership" in text
    assert "executor claims runtime ownership" in text
    assert "recovery claims runtime ownership" in text


def test_runtime_remains_disabled():
    text = read(READY)
    assert "runtime activation: disabled" in text
    assert "recovery activation: disabled" in text
    assert "runtime mutation: forbidden" in text


def test_package_sequence_records_689_696():
    text = read(SEQ)
    assert "packages 689-696" in text or "packages 689–696" in text
    assert "runtime activation runtime ownership boundary" in text
