from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BOUNDARY = ROOT / "docs/runtime_activation_expiration_boundary.md"
GAP = ROOT / "docs/runtime_activation_expiration_gap_inventory.md"
READY = ROOT / "docs/runtime_activation_expiration_readiness_review.md"
SEQ = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def read(p):
    assert p.exists()
    return p.read_text(encoding="utf-8").lower()


def test_expiration_docs_exist():
    assert BOUNDARY.exists()
    assert GAP.exists()
    assert READY.exists()


def test_activation_expiration_chain_required():
    text = read(BOUNDARY)
    assert "activation expiration is required" in text
    assert "operator approval expiration is required" in text
    assert "authorization expiration is required" in text
    assert "evidence expiration is required" in text
    assert "lineage expiration is required" in text


def test_expired_activation_authority_cannot_execute():
    text = read(BOUNDARY)
    assert "expired activation must not execute" in text
    assert "expired approval must not authorize activation" in text
    assert "expired authorization must not grant execution authority" in text
    assert "expired evidence must not validate activation" in text
    assert "expired lineage must not preserve authority" in text


def test_recovery_scheduler_executor_cannot_ignore_expiration():
    text = read(BOUNDARY)
    assert "recovery must not restore expired authority" in text
    assert "scheduler must not ignore expiration" in text
    assert "executor must not ignore expiration" in text


def test_no_expiration_runtime_implementation_added():
    text = read(GAP)
    assert "no executable expiration flow exists" in text
    assert "no activation expiration model exists" in text
    assert "no approval expiration model exists" in text
    assert "no authorization expiration model exists" in text
    assert "no evidence expiration model exists" in text
    assert "no lineage expiration model exists" in text
    assert "no expiration storage exists" in text
    assert "no expiration validation exists" in text


def test_expiration_no_go_rules_exist():
    text = read(READY)
    assert "expired activation executes" in text
    assert "expired approval authorizes activation" in text
    assert "expired authorization grants execution authority" in text
    assert "expired evidence validates activation" in text
    assert "expired lineage preserves authority" in text


def test_runtime_remains_disabled():
    text = read(READY)
    assert "runtime activation: disabled" in text
    assert "recovery activation: disabled" in text
    assert "runtime mutation: forbidden" in text


def test_package_sequence_records_641_648():
    text = read(SEQ)
    assert "packages 641-648" in text or "packages 641–648" in text
    assert "runtime activation expiration boundary" in text
