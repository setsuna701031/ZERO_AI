from pathlib import Path


REVIEW = Path("docs/runtime_recovery_wiring_readiness_review.md")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_264_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 264")
    end = text.find("## Package 265", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_package_264_readiness_review_exists():
    assert REVIEW.exists()
    text = _text(REVIEW)
    assert "Runtime Recovery Wiring Readiness Review" in text
    assert "Review/documentation only." in text
    assert "This package still does not implement runtime wiring." in text


def test_reviewed_contracts_are_listed():
    text = _text(REVIEW)
    for contract in (
        "Recovery Execution Contract",
        "Recovery Execution Plan Contract",
        "Recovery Executor Contract",
        "Recovery State Transition Contract",
        "Recovery Checkpoint Contract",
        "Recovery Rollback Contract",
        "Recovery Retry Contract",
    ):
        assert contract in text


def test_review_required_sections_exist():
    text = _text(REVIEW)
    for heading in (
        "## Readiness Decision",
        "## Reviewed Contracts",
        "## Required Contracts Checklist",
        "## Runtime Wiring Prerequisites",
        "## Forbidden Wiring Before Readiness",
        "## Boundary Matrix",
        "## Dependency Graph",
        "## Non-mainline Issues Found",
        "## Forbidden Implementation Behaviors",
    ):
        assert heading in text


def test_readiness_decision_and_no_runtime_wiring_statement_exist():
    text = _text(REVIEW)
    assert "Readiness decision: GO for future Package 265 planning only." in text
    assert "GO / NO-GO result: GO." in text
    assert "The GO result means the contract layer is sufficiently documented for a future package to plan wiring prerequisites." in text
    assert "It does not authorize runtime wiring" in text
    assert "Package 264 does not satisfy implementation prerequisites and does not wire runtime behavior." in text


def test_forbidden_runtime_behaviors_are_explicit():
    text = _text(REVIEW)
    for phrase in (
        "Package 264 is Review/documentation only.",
        "Package 264 must not create runtime modules.",
        "Package 264 must not modify runtime code.",
        "Package 264 must not modify gateway code.",
        "Package 264 must not implement executor behavior.",
        "Package 264 must not implement state transition behavior.",
        "Package 264 must not implement checkpoint behavior.",
        "Package 264 must not implement rollback behavior.",
        "Package 264 must not implement retry behavior.",
        "Package 264 must not wire recovery runtime modules.",
        "Package 264 must not call or import existing recovery bridge, executor, adapter, or integration modules.",
        "Package 264 must not add public runtime APIs.",
        "Package 264 must not add persistence.",
        "Package 264 must not spawn subprocesses.",
        "Package 264 must not perform filesystem mutation.",
        "Package 264 must not invoke endpoints.",
        "Package 264 must not register hooks.",
        "Package 264 must not mutate runtime state.",
    ):
        assert phrase in text


def test_inventory_contains_recovery_rollback_and_retry_contracts():
    text = _text(INVENTORY)
    assert "recovery_rollback_v1" in text
    assert "recovery_retry_v1" in text


def test_package_sequence_contains_262_263_264():
    text = _text(PACKAGE_SEQUENCE)
    assert "## Package 262" in text
    assert "## Package 263" in text
    assert "## Package 264" in text
    assert "Package 262: Runtime Recovery Rollback Contract" in text
    assert "Package 263: Runtime Recovery Retry Contract" in text
    assert "Package 264: Runtime Recovery Wiring Readiness Review" in text


def test_package_264_sequence_entry_exists():
    section = _package_264_entry()
    assert "## Package 264" in section
    assert "Package 264: Runtime Recovery Wiring Readiness Review" in section
    assert "Review/documentation only." in section
    assert "Final decision: GO. Next package: Package 265." in section
