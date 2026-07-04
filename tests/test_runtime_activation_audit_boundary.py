from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BOUNDARY = ROOT / "docs/runtime_activation_audit_boundary.md"
GAP = ROOT / "docs/runtime_activation_audit_gap_inventory.md"
READY = ROOT / "docs/runtime_activation_audit_readiness_review.md"
SEQ = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def read(p):
    assert p.exists()
    return p.read_text(encoding="utf-8").lower()


def test_audit_docs_exist():
    assert BOUNDARY.exists()
    assert GAP.exists()
    assert READY.exists()


def test_activation_audit_chain_required():
    text = read(BOUNDARY)
    assert "activation request audit is required" in text
    assert "operator approval audit is required" in text
    assert "authorization audit is required" in text
    assert "evidence audit is required" in text
    assert "lineage audit is required" in text


def test_lifecycle_audit_required():
    text = read(BOUNDARY)
    assert "replay rejection audit is required" in text
    assert "revocation audit is required" in text
    assert "expiration audit is required" in text


def test_audit_records_are_deterministic_and_append_only():
    text = read(BOUNDARY)
    assert "audit records must be deterministic" in text
    assert "audit records must be append-only" in text


def test_scheduler_executor_recovery_cannot_modify_audit():
    text = read(BOUNDARY)
    assert "scheduler must not modify activation audit" in text
    assert "executor must not modify activation audit" in text
    assert "recovery must not rewrite activation audit history" in text


def test_no_audit_runtime_implementation_added():
    text = read(GAP)
    assert "no executable activation audit flow exists" in text
    assert "no activation audit model exists" in text
    assert "no approval audit model exists" in text
    assert "no authorization audit model exists" in text
    assert "no evidence audit model exists" in text
    assert "no lineage audit model exists" in text
    assert "no audit storage exists" in text
    assert "no audit writer exists" in text


def test_audit_no_go_rules_exist():
    text = read(READY)
    assert "activation request audit is missing" in text
    assert "operator approval audit is missing" in text
    assert "authorization audit is missing" in text
    assert "evidence audit is missing" in text
    assert "lineage audit is missing" in text
    assert "scheduler modifies activation audit" in text
    assert "executor modifies activation audit" in text
    assert "recovery rewrites activation audit history" in text


def test_runtime_remains_disabled():
    text = read(READY)
    assert "runtime activation: disabled" in text
    assert "recovery activation: disabled" in text
    assert "runtime mutation: forbidden" in text


def test_package_sequence_records_649_656():
    text = read(SEQ)
    assert "packages 649-656" in text or "packages 649–656" in text
    assert "runtime activation audit boundary" in text
