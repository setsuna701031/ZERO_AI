from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BOUNDARY = ROOT / "docs/runtime_activation_final_commit_boundary.md"
GAP = ROOT / "docs/runtime_activation_final_commit_gap_inventory.md"
READY = ROOT / "docs/runtime_activation_final_commit_readiness_review.md"
SEQ = ROOT / "docs/aer_evolution_v2_package_sequence.md"


def read(p):
    assert p.exists()
    return p.read_text(encoding="utf-8").lower()


def test_final_commit_docs_exist():
    assert BOUNDARY.exists()
    assert GAP.exists()
    assert READY.exists()


def test_authorization_is_not_commit_authority():
    text = read(BOUNDARY)
    assert "authorization is not commit authority" in text
    assert "commit authority is separate from authorization" in text


def test_activation_final_commit_required():
    text = read(BOUNDARY)
    assert "activation final commit is required" in text
    assert "commit evidence is required" in text
    assert "commit audit is required" in text
    assert "commit lineage is required" in text


def test_commit_must_be_deterministic_and_scoped():
    text = read(BOUNDARY)
    assert "commit must be deterministic" in text
    assert "commit must be scoped to one activation request" in text


def test_scheduler_executor_recovery_cannot_commit_activation():
    text = read(BOUNDARY)
    assert "scheduler must not commit activation" in text
    assert "executor must not commit activation" in text
    assert "recovery must not commit activation" in text


def test_no_commit_runtime_implementation_added():
    text = read(GAP)
    assert "no executable final commit flow exists" in text
    assert "no activation commit model exists" in text
    assert "no commit authority model exists" in text
    assert "no commit evidence model exists" in text
    assert "no commit audit model exists" in text
    assert "no commit lineage model exists" in text
    assert "no commit storage exists" in text
    assert "no commit writer exists" in text


def test_commit_no_go_rules_exist():
    text = read(READY)
    assert "activation final commit is missing" in text
    assert "authorization is treated as commit authority" in text
    assert "commit evidence is missing" in text
    assert "commit audit is missing" in text
    assert "commit lineage is missing" in text
    assert "scheduler commits activation" in text
    assert "executor commits activation" in text
    assert "recovery commits activation" in text


def test_runtime_remains_disabled():
    text = read(READY)
    assert "runtime activation: disabled" in text
    assert "recovery activation: disabled" in text
    assert "runtime mutation: forbidden" in text


def test_package_sequence_records_657_664():
    text = read(SEQ)
    assert "packages 657-664" in text or "packages 657–664" in text
    assert "runtime activation final commit boundary" in text
