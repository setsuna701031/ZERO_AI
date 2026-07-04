from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = ROOT / "docs/contracts/runtime/runtime_activation_execution_handoff_v1.md"
RESPONSIBILITY = ROOT / "docs/runtime_activation_execution_handoff_responsibility.md"
EVIDENCE = ROOT / "docs/runtime_activation_execution_handoff_evidence.md"
AUDIT = ROOT / "docs/runtime_activation_execution_handoff_audit.md"
SCHEDULER_READY = ROOT / "docs/runtime_scheduler_handoff_readiness_review.md"
EXECUTOR_READY = ROOT / "docs/runtime_executor_handoff_readiness_review.md"
SEAL = ROOT / "docs/runtime_activation_execution_handoff_seal.md"
SEQ = ROOT / "docs/aer_evolution_v2_package_sequence.md"


DOCS = (
    CONTRACT,
    RESPONSIBILITY,
    EVIDENCE,
    AUDIT,
    SCHEDULER_READY,
    EXECUTOR_READY,
    SEAL,
)


def read(path):
    assert path.exists()
    return path.read_text(encoding="utf-8").lower()


def all_text():
    return "\n".join(read(path) for path in DOCS)


def test_runtime_activation_execution_handoff_docs_exist():
    for path in DOCS:
        assert path.exists()


def test_execution_handoff_required():
    text = all_text()
    assert "execution requires handoff object" in text
    assert "execution handoff required" in text
    assert "handoff_id" in text
    assert "handoff_state" in text


def test_active_is_not_execution_permission():
    text = all_text()
    assert "active is not execution permission" in text
    assert "active != execution permission" in text
    assert "execution_permission` default: `false" in text


def test_runtime_owner_is_not_executor():
    text = all_text()
    assert "runtime owner != executor" in text
    assert "owner != executor" in text
    assert "must not execute" in text


def test_scheduler_requires_handoff():
    text = all_text()
    assert "scheduler requires handoff" in text
    assert "scheduler may consume approved handoff" in text
    assert "scheduler must not create handoff" in text
    assert "scheduler self authorization" in text


def test_executor_requires_handoff():
    text = all_text()
    assert "executor requires handoff" in text
    assert "executor requires handoff before accepting work" in text
    assert "executor cannot accept activation directly" in text
    assert "permission explicit" in text


def test_evidence_required():
    text = all_text()
    assert "handoff evidence is required" in text
    assert "ownership evidence is required" in text
    assert "decision evidence is required" in text
    assert "missing evidence: no-go" in text
    assert "evidence_reference" in text


def test_audit_required():
    text = all_text()
    assert "audit trail is required" in text
    assert "audit must record" in text
    assert "who activated" in text
    assert "who approved handoff" in text
    assert "who scheduled" in text
    assert "who executed" in text
    assert "audit_reference" in text


def test_recovery_cannot_create_handoff():
    text = all_text()
    assert "recovery cannot create handoff" in text
    assert "recovery != handoff authority" in text
    assert "recovery request only" in text


def test_mutation_disabled():
    text = all_text()
    assert "runtime mutation remains disabled" in text
    assert "mutation disabled" in text


def test_package_sequence_records_697_704():
    text = read(SEQ)
    assert "packages 697-704" in text or "packages 697–704" in text
    assert "runtime activation execution handoff boundary" in text
