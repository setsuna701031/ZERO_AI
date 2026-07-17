from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = ROOT / "docs/contracts/runtime/runtime_executor_execution_authorization_v1.md"
RESPONSIBILITY = ROOT / "docs/runtime_executor_execution_authorization_responsibility.md"
EVIDENCE = ROOT / "docs/runtime_executor_execution_authorization_evidence.md"
AUDIT = ROOT / "docs/runtime_executor_execution_authorization_audit.md"
READINESS = ROOT / "docs/runtime_executor_execution_authorization_readiness_review.md"
NO_GO = ROOT / "docs/runtime_executor_execution_authorization_no_go_review.md"
SEAL = ROOT / "docs/runtime_executor_execution_authorization_seal.md"
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


def test_runtime_executor_execution_authorization_docs_exist():
    for path in DOCS:
        assert path.exists()


def test_executor_admission_is_not_execution_permission():
    text = all_text()
    assert "executor admission != execution permission" in text
    assert "executor admission is not execution permission" in text


def test_execution_authorization_required():
    text = all_text()
    assert "execution authorization required" in text
    assert "execution authorization required before any future execution" in text


def test_executor_cannot_self_authorize_execution():
    text = all_text()
    assert "executor cannot self authorize execution" in text
    assert "executor self-authorized execution" in text


def test_scheduler_cannot_authorize_execution():
    text = all_text()
    assert "scheduler cannot authorize execution" in text
    assert "scheduler-authorized execution" in text


def test_recovery_cannot_issue_execution_authorization():
    text = all_text()
    assert "recovery cannot issue execution authorization" in text
    assert "recovery-issued execution authorization" in text


def test_full_activation_chain_required():
    text = all_text()
    assert "full activation chain required" in text
    assert "full activation chain is missing" in text


def test_activation_evidence_required():
    text = all_text()
    assert "activation evidence required" in text
    assert "activation evidence is missing" in text


def test_handoff_evidence_required():
    text = all_text()
    assert "handoff evidence required" in text
    assert "handoff evidence is missing" in text


def test_scheduler_admission_evidence_required():
    text = all_text()
    assert "scheduler admission evidence required" in text
    assert "scheduler admission evidence is missing" in text


def test_dispatch_authorization_evidence_required():
    text = all_text()
    assert "dispatch authorization evidence required" in text
    assert "dispatch authorization evidence is missing" in text


def test_executor_admission_evidence_required():
    text = all_text()
    assert "executor admission evidence required" in text
    assert "executor admission evidence is missing" in text


def test_execution_evidence_required():
    text = all_text()
    assert "execution evidence required" in text
    assert "execution evidence is missing" in text


def test_execution_audit_required():
    text = all_text()
    assert "execution audit required" in text
    assert "execution audit is missing" in text


def test_missing_execution_authorization_cannot_execute():
    text = all_text()
    assert "missing execution authorization cannot execute" in text
    assert "execution authorization is missing" in text


def test_mutation_disabled():
    text = all_text()
    assert "runtime mutation remains disabled" in text
    assert "mutation disabled" in text


def test_no_execution_path_created():
    text = all_text()
    assert "no execution path created" in text
    assert "does not create execution authorization runtime code" in text
    assert "no executor execution runtime path, bridge, or mutation path is implemented" in text


def test_package_sequence_records_729_736():
    text = read(SEQ)
    assert "packages 729-736" in text or "packages 729–736" in text
    assert "runtime executor execution authorization boundary" in text
