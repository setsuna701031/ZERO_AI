from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CONTRACT = ROOT / "docs/contracts/runtime/runtime_scheduler_dispatch_authorization_v1.md"
RESPONSIBILITY = ROOT / "docs/runtime_scheduler_dispatch_authorization_responsibility.md"
EVIDENCE = ROOT / "docs/runtime_scheduler_dispatch_authorization_evidence.md"
AUDIT = ROOT / "docs/runtime_scheduler_dispatch_authorization_audit.md"
READINESS = ROOT / "docs/runtime_scheduler_dispatch_authorization_readiness_review.md"
NO_GO = ROOT / "docs/runtime_scheduler_dispatch_authorization_no_go_review.md"
SEAL = ROOT / "docs/runtime_scheduler_dispatch_authorization_seal.md"
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


def test_runtime_scheduler_dispatch_authorization_docs_exist():
    for path in DOCS:
        assert path.exists()


def test_scheduler_admission_is_not_dispatch_permission():
    text = all_text()
    assert "scheduler admission != dispatch permission" in text
    assert "scheduler admission is not dispatch permission" in text


def test_dispatch_authorization_required():
    text = all_text()
    assert "dispatch authorization required" in text
    assert "must require dispatch authorization before dispatch" in text


def test_scheduler_cannot_self_authorize_dispatch():
    text = all_text()
    assert "scheduler cannot self authorize dispatch" in text
    assert "must not self authorize dispatch" in text


def test_scheduler_cannot_dispatch_from_admission_alone():
    text = all_text()
    assert "scheduler cannot dispatch from admission alone" in text
    assert "must not dispatch from admission alone" in text


def test_owner_approved_handoff_required():
    text = all_text()
    assert "owner-approved handoff required" in text
    assert "dispatch authorization requires owner-approved handoff" in text


def test_dispatch_evidence_required():
    text = all_text()
    assert "dispatch evidence required" in text
    assert "dispatch evidence is missing" in text


def test_dispatch_audit_required():
    text = all_text()
    assert "dispatch audit required" in text
    assert "dispatch audit is missing" in text


def test_executor_remains_unavailable():
    text = all_text()
    assert "executor remains unavailable" in text
    assert "executor execution from admission alone" in text


def test_recovery_cannot_issue_dispatch_authorization():
    text = all_text()
    assert "recovery cannot issue dispatch authorization" in text
    assert "recovery-issued dispatch authorization" in text


def test_missing_dispatch_authorization_cannot_execute():
    text = all_text()
    assert "missing dispatch authorization cannot execute" in text
    assert "dispatch authorization is missing" in text


def test_mutation_disabled():
    text = all_text()
    assert "runtime mutation remains disabled" in text
    assert "mutation disabled" in text


def test_no_dispatch_path_created():
    text = all_text()
    assert "no dispatch path created" in text
    assert "does not create scheduler dispatch code" in text
    assert "no scheduler dispatch runtime path or executor path is implemented" in text


def test_package_sequence_records_713_720():
    text = read(SEQ)
    assert "packages 713-720" in text or "packages 713–720" in text
    assert "runtime scheduler dispatch authorization boundary" in text
