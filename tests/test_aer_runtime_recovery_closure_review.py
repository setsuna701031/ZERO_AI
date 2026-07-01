from pathlib import Path


REVIEW = Path("docs/aer_runtime_recovery_closure_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
RECOVERY_IMPLEMENTATION = Path("core/runtime/aer_runtime_recovery.py")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_143_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 143")
    end = text.find("## Package 144", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_closure_review_document_exists():
    assert REVIEW.exists()


def test_required_review_sections_exist():
    text = _text(REVIEW)
    for section in (
        "## Purpose",
        "## Ownership Matrix",
        "## Dependency Graph",
        "## Responsibility Matrix",
        "## Architecture Validation",
        "## Forbidden Dependency Review",
        "## Forbidden Behavior Review",
        "## Implementation Readiness",
        "## GO / NO-GO Decision",
        "## Rationale",
        "## Risks",
        "## Remaining Implementation Packages",
    ):
        assert section in text


def test_dependency_graph_present_and_ordered():
    text = _text(REVIEW)
    assert "Package 137 Domain Lifecycle Standard" in text
    assert "Package 138 Runtime Recovery Blueprint" in text
    assert "Package 139 Runtime Recovery Contract" in text
    assert "Package 140 Runtime Recovery Validation" in text
    assert "Package 141 Runtime Recovery Planner / Builder" in text
    assert "Package 142 Runtime Recovery Consumer Boundary" in text
    assert "Package 143 Runtime Recovery Closure Review" in text
    assert "Package 144 Runtime Recovery Integration Blueprint" in text
    assert "core.runtime.aer_runtime_recovery_validation" in text
    assert "core.runtime.aer_runtime_recovery_planner" in text
    assert "core.runtime.aer_runtime_recovery_consumer_boundary" in text
    assert "The implementation graph is one-way" in text


def test_go_no_go_and_implementation_readiness_exist():
    text = _text(REVIEW)
    assert "Final decision: GO" in text
    assert "## Implementation Readiness" in text
    assert "Recovery governance is complete enough" in text
    assert "Runtime Recovery implementation has not started" in text
    assert "Execution authority remains intentionally absent" in text
    assert "Next package: Package 144: Runtime Recovery Integration Blueprint" in text


def test_forbidden_behavior_list_exists():
    text = _text(REVIEW)
    for behavior in (
        "recovery execution",
        "scheduler integration",
        "dispatcher integration",
        "persistence writes",
        "replay behavior",
        "audit emission",
        "journal emission",
        "subprocess calls",
        "file IO",
        "runtime mutation",
        "runtime orchestration",
    ):
        assert behavior in text
    assert "Review result: PASS" in text


def test_architecture_matrix_exists_and_contains_required_checks():
    text = _text(REVIEW)
    assert "| Check | Result | Evidence |" in text
    for check in (
        "Layer ordering is complete.",
        "Each layer has exactly one responsibility.",
        "No layer performs execution.",
        "Dependency direction is one-way only.",
        "No circular dependency exists.",
        "Planner depends on Validation only.",
        "Consumer Boundary depends on Planner / Validation only.",
        "Execution authority is intentionally absent.",
        "Recovery Runtime implementation has not started.",
        "Recovery governance is complete enough for implementation.",
    ):
        assert check in text


def test_recovery_runtime_implementation_has_not_started():
    assert not RECOVERY_IMPLEMENTATION.exists()


def test_package_sequence_contains_package_143_and_144_next():
    entry = _package_143_entry()
    assert "## Package 143" in entry
    assert "Package 143: Runtime Recovery Closure Review" in entry
    assert "architecture/governance review only" in entry
    assert "Runtime Recovery implementation has not started" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 144: Runtime Recovery Integration Blueprint" in entry
