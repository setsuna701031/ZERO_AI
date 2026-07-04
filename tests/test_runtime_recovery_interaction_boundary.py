from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = ROOT / "docs/contracts/runtime/runtime_recovery_interaction_boundary_v1.md"
RESPONSIBILITY = ROOT / "docs/runtime_recovery_interaction_boundary_responsibility.md"
EVIDENCE = ROOT / "docs/runtime_recovery_interaction_boundary_evidence.md"
AUDIT = ROOT / "docs/runtime_recovery_interaction_boundary_audit.md"
READINESS = ROOT / "docs/runtime_recovery_interaction_boundary_readiness_review.md"
NO_GO = ROOT / "docs/runtime_recovery_interaction_boundary_no_go_review.md"
SEAL = ROOT / "docs/runtime_recovery_interaction_boundary_seal.md"
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


def test_runtime_recovery_interaction_boundary_docs_exist():
    for path in DOCS:
        assert path.exists()


def test_recovery_is_not_activation_authority():
    text = all_text()
    assert "recovery != activation authority" in text
    assert "recovery is not activation authority" in text


def test_recovery_is_not_execution_authority():
    text = all_text()
    assert "recovery != execution authority" in text
    assert "recovery is not execution authority" in text


def test_recovery_cannot_create_execution_handoff():
    text = all_text()
    assert "recovery cannot create execution handoff" in text
    assert "recovery creates execution handoff" in text


def test_recovery_cannot_approve_scheduler_admission():
    text = all_text()
    assert "recovery cannot approve scheduler admission" in text
    assert "recovery approves scheduler admission" in text


def test_recovery_cannot_issue_dispatch_authorization():
    text = all_text()
    assert "recovery cannot issue dispatch authorization" in text
    assert "recovery issues dispatch authorization" in text


def test_recovery_cannot_admit_executor():
    text = all_text()
    assert "recovery cannot admit executor" in text
    assert "recovery admits executor" in text


def test_recovery_cannot_issue_execution_authorization():
    text = all_text()
    assert "recovery cannot issue execution authorization" in text
    assert "recovery issues execution authorization" in text


def test_recovery_cannot_issue_mutation_authorization():
    text = all_text()
    assert "recovery cannot issue mutation authorization" in text
    assert "recovery issues mutation authorization" in text


def test_recovery_cannot_bypass_mutation_gate():
    text = all_text()
    assert "recovery cannot bypass mutation gate" in text
    assert "recovery bypasses mutation gate" in text


def test_recovery_cannot_restart_execution_directly():
    text = all_text()
    assert "recovery cannot restart execution directly" in text
    assert "recovery restarts execution directly" in text


def test_recovery_cannot_mutate_runtime_state_directly():
    text = all_text()
    assert "recovery cannot mutate runtime state directly" in text
    assert "recovery mutates runtime state directly" in text


def test_recovery_may_request_review():
    text = all_text()
    assert "recovery may request review" in text


def test_recovery_may_recommend_safe_state_restore():
    text = all_text()
    assert "recovery may recommend safe-state restore" in text


def test_recovery_may_block_activation_continuation():
    text = all_text()
    assert "recovery may block activation continuation" in text


def test_recovery_evidence_required():
    text = all_text()
    assert "recovery evidence required" in text
    assert "recovery evidence is missing" in text


def test_recovery_audit_required():
    text = all_text()
    assert "recovery audit required" in text
    assert "recovery audit is missing" in text


def test_mutation_disabled():
    text = all_text()
    assert "runtime mutation remains disabled" in text
    assert "mutation disabled" in text


def test_no_recovery_execution_path_created():
    text = all_text()
    assert "no recovery execution path created" in text
    assert "does not create recovery runtime code" in text


def test_package_sequence_records_745_752():
    text = read(SEQ)
    assert "packages 745-752" in text or "packages 745–752" in text
    assert "runtime recovery interaction boundary" in text
