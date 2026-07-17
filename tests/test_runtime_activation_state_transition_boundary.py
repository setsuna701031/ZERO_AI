from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BOUNDARY = ROOT / "docs/runtime_activation_state_transition_boundary.md"
GAP = ROOT / "docs/runtime_activation_state_transition_gap_inventory.md"
READY = ROOT / "docs/runtime_activation_state_transition_readiness_review.md"
SEQ = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def read(p):
    assert p.exists()
    return p.read_text(encoding="utf-8").lower()


def test_state_transition_docs_exist():
    assert BOUNDARY.exists()
    assert GAP.exists()
    assert READY.exists()


def test_disabled_cannot_jump_directly_to_active():
    text = read(BOUNDARY)
    assert "runtime activation state must not jump directly from disabled to active" in text
    assert "disabled transitions directly to active" in read(READY)


def test_required_state_order_defined():
    text = read(BOUNDARY)
    required_states = [
        "disabled",
        "requested",
        "approved",
        "authorized",
        "evidence_verified",
        "lineage_verified",
        "replay_checked",
        "lifetime_checked",
        "audited",
        "committed",
        "active",
    ]
    for state in required_states:
        assert state in text


def test_transition_validation_and_guards_required():
    text = read(BOUNDARY)
    assert "activation state transition validation is required" in text
    assert "illegal transition is forbidden" in text
    assert "skipped activation state is forbidden" in text


def test_transition_evidence_audit_and_lineage_required():
    text = read(BOUNDARY)
    assert "transition evidence is required" in text
    assert "transition audit is required" in text
    assert "transition lineage is required" in text


def test_scheduler_executor_recovery_cannot_force_transition():
    text = read(BOUNDARY)
    assert "scheduler must not force activation transition" in text
    assert "executor must not force activation transition" in text
    assert "recovery must not jump activation state" in text


def test_no_transition_runtime_implementation_added():
    text = read(GAP)
    assert "no executable state transition flow exists" in text
    assert "no activation state model exists" in text
    assert "no transition validator exists" in text
    assert "no illegal transition blocker exists" in text
    assert "no skipped state blocker exists" in text
    assert "no recovery state jump blocker exists" in text


def test_transition_no_go_rules_exist():
    text = read(READY)
    assert "activation state transition validation is missing" in text
    assert "illegal transition occurs" in text
    assert "skipped activation state occurs" in text
    assert "transition evidence is missing" in text
    assert "transition audit is missing" in text
    assert "transition lineage is missing" in text
    assert "scheduler forces activation transition" in text
    assert "executor forces activation transition" in text
    assert "recovery jumps activation state" in text


def test_runtime_remains_disabled():
    text = read(READY)
    assert "runtime activation: disabled" in text
    assert "recovery activation: disabled" in text
    assert "runtime mutation: forbidden" in text


def test_package_sequence_records_673_680():
    text = read(SEQ)
    assert "packages 673-680" in text or "packages 673–680" in text
    assert "runtime activation state transition boundary" in text
