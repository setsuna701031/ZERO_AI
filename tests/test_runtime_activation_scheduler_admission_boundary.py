from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = ROOT / "docs/contracts/runtime/runtime_activation_scheduler_admission_v1.md"
RESPONSIBILITY = ROOT / "docs/runtime_activation_scheduler_admission_responsibility.md"
EVIDENCE = ROOT / "docs/runtime_activation_scheduler_admission_evidence.md"
AUDIT = ROOT / "docs/runtime_activation_scheduler_admission_audit.md"
READINESS = ROOT / "docs/runtime_activation_scheduler_admission_readiness_review.md"
NO_GO = ROOT / "docs/runtime_activation_scheduler_admission_no_go_review.md"
SEAL = ROOT / "docs/runtime_activation_scheduler_admission_seal.md"
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


def test_runtime_activation_scheduler_admission_docs_exist():
    for path in DOCS:
        assert path.exists()


def test_execution_handoff_required():
    text = all_text()
    assert "execution handoff required" in text
    assert "scheduler admission requires execution handoff" in text


def test_active_is_not_scheduler_admission():
    text = all_text()
    assert "active != scheduler admission" in text
    assert "active is not scheduler admission permission" in text


def test_scheduler_cannot_create_handoff():
    text = all_text()
    assert "scheduler cannot create handoff" in text
    assert "must not create handoff" in text


def test_scheduler_cannot_self_authorize():
    text = all_text()
    assert "scheduler cannot self authorize" in text
    assert "scheduler self-authorization" in text


def test_owner_approval_required():
    text = all_text()
    assert "owner approval required" in text
    assert "scheduler cannot approve owner decision" in text


def test_handoff_evidence_required():
    text = all_text()
    assert "handoff evidence required" in text
    assert "handoff evidence is missing" in text


def test_admission_audit_required():
    text = all_text()
    assert "admission audit required" in text
    assert "silent admission without audit" in text


def test_recovery_cannot_inject_handoff():
    text = all_text()
    assert "recovery cannot inject handoff" in text
    assert "recovery-created handoff admission" in text


def test_rejected_admission_cannot_execute():
    text = all_text()
    assert "rejected admission cannot execute" in text
    assert "admission is rejected" in text


def test_mutation_disabled():
    text = all_text()
    assert "runtime mutation remains disabled" in text
    assert "mutation disabled" in text


def test_no_dispatch_path_created():
    text = all_text()
    assert "no dispatch path created" in text
    assert "does not create scheduler runtime admission code" in text
    assert "no scheduler runtime path or executor path is implemented" in text


def test_package_sequence_records_705_712():
    text = read(SEQ)
    assert "packages 705-712" in text or "packages 705–712" in text
    assert "runtime activation scheduler admission boundary" in text
