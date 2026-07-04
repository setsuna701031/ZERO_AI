from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BOUNDARY = ROOT / "docs/runtime_activation_revocation_boundary.md"
GAP = ROOT / "docs/runtime_activation_revocation_gap_inventory.md"
READY = ROOT / "docs/runtime_activation_revocation_readiness_review.md"
SEQ = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def read(p):
    assert p.exists()
    return p.read_text(encoding="utf-8").lower()


def test_revocation_docs_exist():
    assert BOUNDARY.exists()
    assert GAP.exists()
    assert READY.exists()


def test_activation_revocation_chain_required():
    text = read(BOUNDARY)
    assert "operator approval revocation is required" in text
    assert "authorization revocation is required" in text
    assert "evidence revocation is required" in text
    assert "lineage revocation is required" in text


def test_revoked_activation_authority_cannot_execute():
    text = read(BOUNDARY)
    assert "revoked activation must not execute" in text
    assert "revoked approval must not authorize activation" in text
    assert "revoked authorization must not grant execution authority" in text
    assert "revoked evidence must not validate activation" in text
    assert "revoked lineage must not preserve authority" in text


def test_recovery_scheduler_executor_cannot_ignore_revocation():
    text = read(BOUNDARY)
    assert "recovery must not restore revoked authority" in text
    assert "scheduler must not ignore revocation" in text
    assert "executor must not ignore revocation" in text


def test_no_revocation_runtime_implementation_added():
    text = read(GAP)
    assert "no executable revocation flow exists" in text
    assert "no approval revocation model exists" in text
    assert "no authorization revocation model exists" in text
    assert "no evidence revocation model exists" in text
    assert "no lineage revocation model exists" in text
    assert "no revocation storage exists" in text
    assert "no revocation validation exists" in text


def test_revocation_no_go_rules_exist():
    text = read(READY)
    assert "revoked activation executes" in text
    assert "revoked approval authorizes activation" in text
    assert "revoked authorization grants execution authority" in text
    assert "revoked evidence validates activation" in text
    assert "revoked lineage preserves authority" in text


def test_runtime_remains_disabled():
    text = read(READY)
    assert "runtime activation: disabled" in text
    assert "recovery activation: disabled" in text
    assert "runtime mutation: forbidden" in text


def test_package_sequence_records_633_640():
    text = read(SEQ)
    assert "packages 633-640" in text or "packages 633–640" in text
    assert "runtime activation revocation boundary" in text
