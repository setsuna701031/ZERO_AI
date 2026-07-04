from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BOUNDARY = ROOT / "docs/runtime_activation_state_observation_boundary.md"
GAP = ROOT / "docs/runtime_activation_state_observation_gap_inventory.md"
READY = ROOT / "docs/runtime_activation_state_observation_readiness_review.md"
SEQ = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def read(p):
    assert p.exists()
    return p.read_text(encoding="utf-8").lower()


def test_state_observation_docs_exist():
    assert BOUNDARY.exists()
    assert GAP.exists()
    assert READY.exists()


def test_observed_state_is_not_execution_authority():
    text = read(BOUNDARY)
    assert "observed activation state is not execution authority" in text
    assert "observed state is not execution authority" in text


def test_observation_is_read_only():
    text = read(BOUNDARY)
    assert "activation state observation is read-only" in text
    assert "observer must not mutate activation state" in text


def test_observation_evidence_audit_lineage_required():
    text = read(BOUNDARY)
    assert "observation evidence is required" in text
    assert "observation audit is required" in text
    assert "observation lineage is required" in text


def test_scheduler_executor_recovery_are_read_only():
    text = read(BOUNDARY)
    assert "scheduler observation is read-only" in text
    assert "executor observation is read-only" in text
    assert "recovery observation is read-only" in text


def test_observation_cannot_trigger_execution_or_recovery():
    text = read(BOUNDARY)
    assert "scheduler must not execute from observed state" in text
    assert "executor must not execute from observed state" in text
    assert "recovery must not restore from observed state" in text


def test_no_observation_runtime_implementation_added():
    text = read(GAP)
    assert "no executable state observation flow exists" in text
    assert "no activation observation model exists" in text
    assert "no observation evidence model exists" in text
    assert "no observation audit model exists" in text
    assert "no observation lineage model exists" in text


def test_observation_no_go_rules_exist():
    text = read(READY)
    assert "observed state grants execution authority" in text
    assert "observer mutates activation state" in text
    assert "scheduler executes from observed state" in text
    assert "executor executes from observed state" in text
    assert "recovery restores from observed state" in text


def test_runtime_remains_disabled():
    text = read(READY)
    assert "runtime activation: disabled" in text
    assert "recovery activation: disabled" in text
    assert "runtime mutation: forbidden" in text


def test_package_sequence_records_681_688():
    text = read(SEQ)
    assert "packages 681-688" in text or "packages 681–688" in text
    assert "runtime activation state observation boundary" in text
