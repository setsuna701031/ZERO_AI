from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = ROOT / "docs/contracts/runtime/runtime_executor_admission_v1.md"
RESPONSIBILITY = ROOT / "docs/runtime_executor_admission_responsibility.md"
EVIDENCE = ROOT / "docs/runtime_executor_admission_evidence.md"
AUDIT = ROOT / "docs/runtime_executor_admission_audit.md"
READINESS = ROOT / "docs/runtime_executor_admission_readiness_review.md"
NO_GO = ROOT / "docs/runtime_executor_admission_no_go_review.md"
SEAL = ROOT / "docs/runtime_executor_admission_seal.md"
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


def test_runtime_executor_admission_docs_exist():
    for path in DOCS:
        assert path.exists()


def test_dispatch_authorization_is_not_execution_permission():
    text = all_text()
    assert "dispatch authorization != execution permission" in text
    assert "dispatch authorization is not execution permission" in text


def test_executor_admission_required():
    text = all_text()
    assert "executor admission required" in text
    assert "executor admission required before any future executor execution" in text


def test_scheduler_cannot_call_executor_directly():
    text = all_text()
    assert "scheduler cannot call executor directly" in text
    assert "scheduler direct executor call" in text


def test_scheduler_is_not_executor_owner():
    text = all_text()
    assert "scheduler is not executor owner" in text
    assert "scheduler claims executor ownership" in text


def test_executor_cannot_self_admit():
    text = all_text()
    assert "executor cannot self admit" in text
    assert "executor self-admission" in text


def test_handoff_chain_evidence_required():
    text = all_text()
    assert "handoff chain evidence required" in text
    assert "handoff chain evidence is missing" in text


def test_dispatch_authorization_required():
    text = all_text()
    assert "dispatch authorization required" in text
    assert "dispatch authorization is missing" in text


def test_dispatch_evidence_required():
    text = all_text()
    assert "dispatch evidence required" in text
    assert "dispatch evidence is missing" in text


def test_executor_admission_decision_required():
    text = all_text()
    assert "executor admission decision required" in text
    assert "executor admission decision is missing" in text


def test_executor_admission_audit_required():
    text = all_text()
    assert "executor admission audit required" in text
    assert "executor admission audit is missing" in text


def test_recovery_cannot_call_executor():
    text = all_text()
    assert "recovery cannot call executor" in text
    assert "recovery direct executor call" in text


def test_missing_executor_admission_cannot_execute():
    text = all_text()
    assert "missing executor admission cannot execute" in text
    assert "executor admission is missing" in text


def test_mutation_disabled():
    text = all_text()
    assert "runtime mutation remains disabled" in text
    assert "mutation disabled" in text


def test_no_executor_path_created():
    text = all_text()
    assert "no executor path created" in text
    assert "does not create executor admission runtime code" in text
    assert "no executor runtime path, execution path, or mutation path is implemented" in text


def test_package_sequence_records_721_728():
    text = read(SEQ)
    assert "packages 721-728" in text or "packages 721–728" in text
    assert "runtime executor admission boundary" in text
