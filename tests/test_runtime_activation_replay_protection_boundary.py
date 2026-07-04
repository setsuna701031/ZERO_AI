from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BOUNDARY = ROOT / "docs/runtime_activation_replay_protection_boundary.md"
GAP = ROOT / "docs/runtime_activation_replay_protection_gap_inventory.md"
READY = ROOT / "docs/runtime_activation_replay_protection_readiness_review.md"
SEQ = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def read(p):
    assert p.exists()
    return p.read_text(encoding="utf-8").lower()


def test_replay_docs_exist():
    assert BOUNDARY.exists()
    assert GAP.exists()
    assert READY.exists()


def test_activation_chain_replay_forbidden():
    text = read(BOUNDARY)
    assert "activation request replay is forbidden" in text
    assert "operator approval replay is forbidden" in text
    assert "authorization replay is forbidden" in text
    assert "evidence replay is forbidden" in text
    assert "lineage replay is forbidden" in text


def test_stale_and_expired_authority_invalid():
    text = read(BOUNDARY)
    assert "stale activation chains are forbidden" in text
    assert "expired activation authority is invalid" in text


def test_scheduler_executor_recovery_cannot_replay():
    text = read(BOUNDARY)
    assert "recovery must not replay activation authority" in text
    assert "scheduler must not replay activation authority" in text
    assert "executor must not replay activation authority" in text


def test_no_replay_runtime_implementation_added():
    text = read(GAP)
    assert "no executable replay protection flow exists" in text
    assert "no activation replay detector exists" in text
    assert "no replay storage exists" in text
    assert "no replay validation exists" in text


def test_replay_no_go_rules_exist():
    text = read(READY)
    assert "activation request is replayed" in text
    assert "operator approval is replayed" in text
    assert "authorization is replayed" in text
    assert "evidence is replayed" in text
    assert "lineage is replayed" in text


def test_runtime_remains_disabled():
    text = read(READY)
    assert "runtime activation: disabled" in text
    assert "recovery activation: disabled" in text
    assert "runtime mutation: forbidden" in text


def test_package_sequence_records_625_632():
    text = read(SEQ)
    assert "packages 625-632" in text or "packages 625–632" in text
    assert "runtime activation replay protection boundary" in text
