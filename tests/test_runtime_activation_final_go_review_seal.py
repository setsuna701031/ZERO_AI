from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = ROOT / "docs/contracts/runtime/runtime_activation_final_go_review_v1.md"
MATRIX = ROOT / "docs/runtime_activation_final_go_review_matrix.md"
EVIDENCE = ROOT / "docs/runtime_activation_final_go_review_evidence.md"
AUDIT = ROOT / "docs/runtime_activation_final_go_review_audit.md"
NO_GO = ROOT / "docs/runtime_activation_final_go_review_no_go_review.md"
SEAL = ROOT / "docs/runtime_activation_final_go_review_seal.md"
READINESS = ROOT / "docs/runtime_activation_final_go_review_readiness.md"
SEQ = ROOT / "docs/aer_evolution_v2_package_sequence.md"


DOCS = (
    CONTRACT,
    MATRIX,
    EVIDENCE,
    AUDIT,
    NO_GO,
    SEAL,
    READINESS,
)


def read(path):
    assert path.exists()
    return path.read_text(encoding="utf-8").lower()


def all_text():
    return "\n".join(read(path) for path in DOCS)


def test_runtime_activation_final_go_review_docs_exist():
    for path in DOCS:
        assert path.exists()


def test_final_activation_go_requires_all_boundaries_go():
    text = all_text()
    assert "final activation go requires all boundaries go" in text
    assert "every required prior boundary is go" in text


def test_missing_boundary_means_no_go():
    text = all_text()
    assert "missing boundary means no-go" in text


def test_unclear_ownership_means_no_go():
    text = all_text()
    assert "unclear ownership means no-go" in text


def test_missing_evidence_means_no_go():
    text = all_text()
    assert "missing evidence means no-go" in text


def test_missing_audit_means_no_go():
    text = all_text()
    assert "missing audit means no-go" in text


def test_bypass_path_means_no_go():
    text = all_text()
    assert "bypass path means no-go" in text


def test_active_does_not_imply_execution():
    text = all_text()
    assert "active does not imply execution" in text


def test_scheduler_admission_does_not_imply_dispatch():
    text = all_text()
    assert "scheduler admission does not imply dispatch" in text


def test_dispatch_authorization_does_not_imply_execution():
    text = all_text()
    assert "dispatch authorization does not imply execution" in text


def test_executor_admission_does_not_imply_execution():
    text = all_text()
    assert "executor admission does not imply execution" in text


def test_execution_authorization_does_not_imply_mutation():
    text = all_text()
    assert "execution authorization does not imply mutation" in text


def test_recovery_cannot_create_or_resume_execution():
    text = all_text()
    assert "recovery cannot create or resume execution" in text


def test_mutation_authorization_required():
    text = all_text()
    assert "mutation authorization required" in text


def test_mutation_disabled():
    text = all_text()
    assert "runtime mutation remains disabled" in text
    assert "mutation disabled" in text


def test_no_activation_runtime_path_created():
    text = all_text()
    assert "no activation runtime path created" in text
    assert "does not create activation runtime code" in text


def test_package_sequence_records_753_760():
    text = read(SEQ)
    assert "packages 753-760" in text or "packages 753–760" in text
    assert "runtime activation final go review seal" in text
