from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = ROOT / "docs/contracts/runtime/runtime_execution_mutation_boundary_v1.md"
RESPONSIBILITY = ROOT / "docs/runtime_execution_mutation_boundary_responsibility.md"
EVIDENCE = ROOT / "docs/runtime_execution_mutation_boundary_evidence.md"
AUDIT = ROOT / "docs/runtime_execution_mutation_boundary_audit.md"
READINESS = ROOT / "docs/runtime_execution_mutation_boundary_readiness_review.md"
NO_GO = ROOT / "docs/runtime_execution_mutation_boundary_no_go_review.md"
SEAL = ROOT / "docs/runtime_execution_mutation_boundary_seal.md"
SEQ = ROOT / "docs/aer_evolution_v2_package_sequence.md"


DOCS = (
    CONTRACT,
    RESPONSIBILITY,
    EVIDENCE,
    AUDIT,
    READINESS,
    NO_GO,
    SEAL,
)


def read(path):
    assert path.exists()
    return path.read_text(encoding="utf-8").lower()


def all_text():
    return "\n".join(read(path) for path in DOCS)


def test_runtime_execution_mutation_boundary_docs_exist():
    for path in DOCS:
        assert path.exists()


def test_execution_authorization_is_not_mutation_permission():
    text = all_text()
    assert "execution authorization != mutation permission" in text
    assert "execution authorization is not mutation permission" in text


def test_mutation_authorization_required():
    text = all_text()
    assert "mutation authorization required" in text
    assert "mutation authorization required before any future runtime" in text


def test_executor_cannot_directly_mutate_runtime_state():
    text = all_text()
    assert "executor cannot directly mutate runtime state" in text
    assert "executor direct runtime state write" in text


def test_executor_cannot_directly_mutate_repo_or_files():
    text = all_text()
    assert "executor cannot directly mutate repo or files" in text
    assert "executor direct repo/file mutation" in text


def test_scheduler_cannot_mutate_runtime_state():
    text = all_text()
    assert "scheduler cannot mutate runtime state" in text
    assert "scheduler mutation" in text


def test_recovery_cannot_bypass_mutation_gate():
    text = all_text()
    assert "recovery cannot bypass mutation gate" in text
    assert "recovery mutation bypass" in text


def test_self_edit_cannot_bypass_mutation_gate():
    text = all_text()
    assert "self edit cannot bypass mutation gate" in text
    assert "self-edit bypassing mutation gate" in text


def test_mutation_evidence_required():
    text = all_text()
    assert "mutation evidence required" in text
    assert "mutation evidence is missing" in text


def test_mutation_audit_required():
    text = all_text()
    assert "mutation audit required" in text
    assert "mutation audit is missing" in text


def test_rollback_boundary_required():
    text = all_text()
    assert "rollback boundary required" in text
    assert "rollback boundary is missing" in text


def test_silent_state_change_forbidden():
    text = all_text()
    assert "silent state change forbidden" in text
    assert "silent state change would occur" in text


def test_missing_mutation_authorization_cannot_mutate():
    text = all_text()
    assert "missing mutation authorization cannot mutate" in text
    assert "mutation authorization is missing" in text


def test_mutation_disabled():
    text = all_text()
    assert "runtime mutation remains disabled" in text
    assert "mutation disabled" in text


def test_no_mutation_path_created():
    text = all_text()
    assert "no mutation path created" in text
    assert "does not create mutation runtime code" in text
    assert "no mutation runtime path, executor bridge, or state write path is implemented" in text


def test_package_sequence_records_737_744():
    text = read(SEQ)
    assert "packages 737-744" in text or "packages 737–744" in text
    assert "runtime execution mutation boundary" in text
