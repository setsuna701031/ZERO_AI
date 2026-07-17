from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BOUNDARY_DOC = ROOT / "docs" / "runtime_activation_authorization_boundary.md"
GAP_DOC = ROOT / "docs" / "runtime_activation_authorization_gap_inventory.md"
READINESS_DOC = ROOT / "docs" / "runtime_activation_authorization_readiness_review.md"
PACKAGE_SEQUENCE = ROOT / "docs" / "aer_evolution_v2_package_sequence.md"


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected file: {path}"
    return path.read_text(encoding="utf-8")


def test_activation_authorization_docs_exist():
    assert BOUNDARY_DOC.exists()
    assert GAP_DOC.exists()
    assert READINESS_DOC.exists()


def test_approval_is_not_execution_authority():
    text = _read(BOUNDARY_DOC).lower()
    assert "approval is not execution authority" in text
    assert "approval without authorization is no-go" in text
    assert "activation authorization is required after operator approval" in text


def test_activation_without_authorization_is_no_go():
    text = _read(BOUNDARY_DOC).lower()
    assert "activation without authorization is no-go" in text
    assert "authorization must be scoped" in text
    assert "authorization must be auditable" in text


def test_authorization_not_inferred_from_scheduler_executor_or_recovery():
    combined = "\n".join(
        [
            _read(BOUNDARY_DOC).lower(),
            _read(READINESS_DOC).lower(),
        ]
    )
    assert "authorization must not be inferred from scheduler state" in combined
    assert "authorization must not be inferred from executor state" in combined
    assert "authorization must not be inferred from recovery state" in combined


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


def test_no_runtime_authorization_implementation_is_introduced():
    combined = "\n".join(
        [
            _read(BOUNDARY_DOC).lower(),
            _read(GAP_DOC).lower(),
        ]
    )
    required_gaps = [
        "no executable activation authorization flow exists",
        "no authorization token exists",
        "no activation authority resolver exists",
        "no authorization evidence store exists",
        "no launcher exists",
        "no runtime loop exists",
    ]
    for gap in required_gaps:
        assert gap in combined


def test_readiness_review_defines_authorization_no_go_criteria():
    text = _read(READINESS_DOC).lower()
    required = [
        "activation authorization is missing",
        "approval is treated as execution authority",
        "authorization is inferred from scheduler state",
        "authorization is inferred from executor state",
        "authorization is inferred from recovery state",
        "runtime mutation occurs",
    ]
    for item in required:
        assert item in text


def test_package_sequence_records_packages_601_to_608():
    text = _read(PACKAGE_SEQUENCE)
    assert "Packages 601-608" in text or "Packages 601–608" in text
    assert "Runtime Activation Authorization Boundary" in text
    assert "Runtime activation remains disabled" in text
    assert "Recovery activation remains disabled" in text
