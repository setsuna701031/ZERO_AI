from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BOUNDARY = ROOT / "docs" / "runtime_activation_gate_boundary.md"
GAPS = ROOT / "docs" / "runtime_activation_gate_gap_inventory.md"
REVIEW = ROOT / "docs" / "runtime_activation_gate_readiness_review.md"
SEQUENCE = ROOT / "docs" / "aer_evolution_v2_package_sequence.md"


def read(path: Path) -> str:
    assert path.exists(), f"missing expected file: {path}"
    return path.read_text(encoding="utf-8")


def test_activation_gate_docs_exist():
    assert BOUNDARY.exists()
    assert GAPS.exists()
    assert REVIEW.exists()


def test_activation_gate_is_boundary_only():
    text = read(BOUNDARY).lower()
    assert "documentation and focused tests only" in text
    assert "not an activation implementation" in text
    assert "go for boundary definition only" in text


def test_activation_gate_has_no_runtime_execution_authority():
    text = read(BOUNDARY).lower()
    required = [
        "must not",
        "execute activation",
        "start scheduler",
        "start executor",
        "dispatch work",
        "execute plans",
        "start a runtime loop",
    ]
    for phrase in required:
        assert phrase in text


def test_operator_approval_required():
    text = read(BOUNDARY).lower() + "\n" + read(REVIEW).lower()
    assert "operator approval is required" in text
    assert "no configuration value" in text
    assert "silently substitute for operator approval" in text


def test_scheduler_and_executor_ownership_unchanged():
    text = read(BOUNDARY).lower() + "\n" + read(REVIEW).lower()
    assert "scheduler ownership remains unchanged" in text
    assert "executor ownership remains unchanged" in text
    assert "does not own scheduler authority" in text
    assert "does not own executor authority" in text


def test_recovery_activation_remains_disabled():
    text = read(BOUNDARY).lower() + "\n" + read(REVIEW).lower()
    assert "recovery activation remains disabled" in text
    assert "does not own recovery authority" in text
    assert "activate recovery" in text


def test_runtime_mutation_forbidden():
    text = read(BOUNDARY).lower() + "\n" + read(REVIEW).lower()
    assert "runtime mutation remains forbidden" in text
    assert "does not own runtime mutation authority" in text
    assert "mutate runtime state" in text


def test_gap_inventory_records_required_future_gaps():
    text = read(GAPS).lower()
    required = [
        "activation request schema",
        "operator approval capture",
        "readiness verification",
        "launch handoff",
        "rollback requirement",
        "audit evidence requirement",
    ]
    for phrase in required:
        assert phrase in text


def test_gap_inventory_forbids_shortcuts():
    text = read(GAPS).lower()
    forbidden_shortcuts = [
        "adding a startup script",
        "adding a cli start command",
        "adding a service",
        "bypassing scheduler ownership",
        "bypassing executor ownership",
        "bypassing operator approval",
        "enabling recovery activation",
    ]
    for phrase in forbidden_shortcuts:
        assert phrase in text


def test_readiness_review_has_go_no_go():
    text = read(REVIEW).lower()
    assert "go / no-go criteria" in text
    assert "decision: go for runtime activation gate boundary definition only" in text
    assert "no executable launcher, cli command, service, or runtime loop is introduced" in text


def test_launch_contract_inheritance_present():
    text = read(BOUNDARY).lower() + "\n" + read(REVIEW).lower()
    inherited = [
        "runtime launch contract boundary",
        "runtime wrapper boundary",
        "runtime environment resolver boundary",
        "runtime production configuration boundary",
        "runtime rc freeze seal",
    ]
    for phrase in inherited:
        assert phrase in text


def test_package_sequence_updated():
    text = read(SEQUENCE)
    assert "Package 585" in text
    assert "Package 592" in text
    assert "Runtime Activation Gate Boundary" in text
