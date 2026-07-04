from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BOUNDARY_DOC = ROOT / "docs" / "runtime_activation_evidence_boundary.md"
GAP_DOC = ROOT / "docs" / "runtime_activation_evidence_gap_inventory.md"
READINESS_DOC = ROOT / "docs" / "runtime_activation_evidence_readiness_review.md"
PACKAGE_SEQUENCE = ROOT / "docs" / "aer_evolution_v2_package_sequence.md"


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected file: {path}"
    return path.read_text(encoding="utf-8")


def test_activation_evidence_docs_exist():
    assert BOUNDARY_DOC.exists()
    assert GAP_DOC.exists()
    assert READINESS_DOC.exists()


def test_authorization_without_evidence_is_not_valid_authority():
    text = _read(BOUNDARY_DOC).lower()
    assert "authorization without evidence is not valid authority" in text
    assert "operator approval and activation authorization must both be backed by deterministic evidence" in text


def test_required_activation_evidence_is_defined():
    text = _read(BOUNDARY_DOC).lower()
    required = [
        "activation request identity is required",
        "operator approval evidence is required",
        "authorization evidence is required",
        "authority lineage evidence is required",
        "missing evidence is no-go",
    ]
    for item in required:
        assert item in text


def test_scheduler_executor_and_recovery_cannot_create_or_reuse_evidence():
    combined = "\n".join(
        [
            _read(BOUNDARY_DOC).lower(),
            _read(READINESS_DOC).lower(),
        ]
    )
    assert "evidence must not be fabricated by scheduler" in combined
    assert "evidence must not be fabricated by executor" in combined
    assert "evidence must not be reused by recovery" in combined
    assert "recovery reuses stale evidence" in combined


def test_stale_or_unscoped_evidence_is_no_go():
    combined = "\n".join(
        [
            _read(BOUNDARY_DOC).lower(),
            _read(READINESS_DOC).lower(),
        ]
    )
    assert "stale evidence must not activate runtime" in combined
    assert "stale evidence activates runtime" in combined
    assert "evidence must be scoped to one activation request" in combined
    assert "evidence is not scoped to one activation request" in combined


def test_recovery_activation_and_runtime_mutation_remain_disabled():
    combined = "\n".join(
        [
            _read(BOUNDARY_DOC).lower(),
            _read(GAP_DOC).lower(),
            _read(READINESS_DOC).lower(),
        ]
    )
    assert "runtime activation remains disabled" in combined
    assert "recovery activation" in combined
    assert "runtime mutation remains forbidden" in combined


def test_no_evidence_runtime_implementation_is_introduced():
    combined = "\n".join(
        [
            _read(BOUNDARY_DOC).lower(),
            _read(GAP_DOC).lower(),
        ]
    )
    required_gaps = [
        "no executable activation evidence flow exists",
        "no activation request identity model exists",
        "no operator approval evidence store exists",
        "no authorization evidence store exists",
        "no authority lineage evidence model exists",
        "no stale evidence rejection flow exists",
        "no recovery evidence reuse blocker exists",
    ]
    for gap in required_gaps:
        assert gap in combined


def test_readiness_review_defines_evidence_no_go_criteria():
    text = _read(READINESS_DOC).lower()
    required = [
        "activation request identity is missing",
        "operator approval evidence is missing",
        "authorization evidence is missing",
        "authority lineage evidence is missing",
        "evidence is fabricated by scheduler",
        "evidence is fabricated by executor",
        "recovery reuses stale evidence",
        "runtime mutation occurs",
    ]
    for item in required:
        assert item in text


def test_package_sequence_records_packages_609_to_616():
    text = _read(PACKAGE_SEQUENCE)
    assert "Packages 609-616" in text or "Packages 609–616" in text
    assert "Runtime Activation Evidence Boundary" in text
    assert "Runtime activation remains disabled" in text
    assert "Recovery activation remains disabled" in text
