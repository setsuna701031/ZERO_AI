from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BOUNDARY = ROOT / "docs/runtime_activation_commit_rollback_boundary.md"
GAP = ROOT / "docs/runtime_activation_commit_rollback_gap_inventory.md"
READY = ROOT / "docs/runtime_activation_commit_rollback_readiness_review.md"
SEQ = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def read(p):
    assert p.exists()
    return p.read_text(encoding="utf-8").lower()


def test_commit_rollback_docs_exist():
    assert BOUNDARY.exists()
    assert GAP.exists()
    assert READY.exists()


def test_commit_rollback_required_and_partial_activation_forbidden():
    text = read(BOUNDARY)
    assert "commit rollback is required" in text
    assert "partial activation is forbidden" in text
    assert "failed commit must not mutate runtime" in text
    assert "failed commit must not activate runtime" in text


def test_rollback_evidence_audit_and_lineage_required():
    text = read(BOUNDARY)
    assert "rollback evidence is required" in text
    assert "rollback audit is required" in text
    assert "rollback lineage is required" in text


def test_rollback_must_be_deterministic_and_scoped():
    text = read(BOUNDARY)
    assert "rollback must be deterministic" in text
    assert "rollback must be scoped to one activation request" in text


def test_scheduler_executor_recovery_cannot_bypass_rollback():
    text = read(BOUNDARY)
    assert "scheduler must not bypass rollback" in text
    assert "executor must not bypass rollback" in text
    assert "recovery must not convert failed commit into activation" in text


def test_no_rollback_runtime_implementation_added():
    text = read(GAP)
    assert "no executable commit rollback flow exists" in text
    assert "no activation rollback model exists" in text
    assert "no rollback evidence model exists" in text
    assert "no rollback audit model exists" in text
    assert "no rollback lineage model exists" in text
    assert "no rollback storage exists" in text
    assert "no rollback writer exists" in text
    assert "no partial activation detector exists" in text


def test_rollback_no_go_rules_exist():
    text = read(READY)
    assert "commit rollback is missing" in text
    assert "partial activation occurs" in text
    assert "failed commit mutates runtime" in text
    assert "failed commit activates runtime" in text
    assert "rollback evidence is missing" in text
    assert "rollback audit is missing" in text
    assert "rollback lineage is missing" in text
    assert "scheduler bypasses rollback" in text
    assert "executor bypasses rollback" in text
    assert "recovery converts failed commit into activation" in text


def test_runtime_remains_disabled():
    text = read(READY)
    assert "runtime activation: disabled" in text
    assert "recovery activation: disabled" in text
    assert "runtime mutation: forbidden" in text


def test_package_sequence_records_665_672():
    text = read(SEQ)
    assert "packages 665-672" in text or "packages 665–672" in text
    assert "runtime activation commit rollback boundary" in text
