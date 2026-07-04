from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BOUNDARY_DOC = ROOT / "docs" / "runtime_activation_approval_boundary.md"
GAP_DOC = ROOT / "docs" / "runtime_activation_approval_gap_inventory.md"
READINESS_DOC = ROOT / "docs" / "runtime_activation_approval_readiness_review.md"
PACKAGE_SEQUENCE = ROOT / "docs" / "aer_evolution_v2_package_sequence.md"


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected file: {path}"
    return path.read_text(encoding="utf-8")


def test_activation_approval_docs_exist():
    assert BOUNDARY_DOC.exists()
    assert GAP_DOC.exists()
    assert READINESS_DOC.exists()


def test_operator_approval_required_and_bypass_forbidden():
    text = _read(BOUNDARY_DOC).lower()
    assert "operator approval is required" in text
    assert "activation without operator approval is no-go" in text
    assert "operator bypass is forbidden" in text


def test_scheduler_and_executor_bypass_forbidden():
    text = _read(BOUNDARY_DOC).lower()
    assert "scheduler bypass is forbidden" in text
    assert "executor bypass is forbidden" in text
    assert "scheduler remains owner of scheduling only" in text
    assert "executor remains owner of execution only" in text


def test_recovery_activation_and_runtime_mutation_remain_disabled():
    combined = "\n".join(
        [
            _read(BOUNDARY_DOC).lower(),
            _read(GAP_DOC).lower(),
            _read(READINESS_DOC).lower(),
        ]
    )
    assert "recovery activation remains disabled" in combined
    assert "runtime activation remains disabled" in combined
    assert "runtime mutation remains forbidden" in combined


def test_no_executable_launcher_or_runtime_loop_is_introduced():
    combined = "\n".join(
        [
            _read(BOUNDARY_DOC).lower(),
            _read(GAP_DOC).lower(),
            _read(READINESS_DOC).lower(),
        ]
    )
    forbidden_markers = [
        "no launcher exists",
        "no start script exists",
        "no cli execution command exists",
        "no service connection exists",
        "no runtime loop exists",
    ]
    for marker in forbidden_markers:
        assert marker in combined


def test_readiness_review_defines_no_go_criteria():
    text = _read(READINESS_DOC).lower()
    required = [
        "operator approval is missing",
        "operator approval is bypassed",
        "scheduler ownership is bypassed",
        "executor ownership is bypassed",
        "recovery activation is enabled",
        "runtime mutation occurs",
    ]
    for item in required:
        assert item in text


def test_package_sequence_records_packages_593_to_600():
    text = _read(PACKAGE_SEQUENCE)
    assert "Packages 593-600" in text or "Packages 593–600" in text
    assert "Runtime Activation Approval Boundary" in text
    assert "Runtime activation remains disabled" in text
    assert "Recovery activation remains disabled" in text
