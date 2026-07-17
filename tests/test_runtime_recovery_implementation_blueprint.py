from pathlib import Path


BLUEPRINT = Path("docs/runtime_recovery_implementation_blueprint.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_265_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 265")
    end = text.find("## Package 266", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_package_265_blueprint_exists_and_includes_required_components():
    assert BLUEPRINT.exists()
    text = _text(BLUEPRINT)
    assert "Runtime Recovery Implementation Blueprint" in text
    for component in (
        "Runtime Component Map",
        "Gateway",
        "RecoveryExecutionPlan",
        "RecoveryExecutor",
        "RecoveryStateTransition",
        "RecoveryCheckpoint",
        "RecoveryRollback",
        "RecoveryRetry",
        "Supervisor",
        "Operator",
        "Native Runtime",
    ):
        assert component in text


def test_package_265_flow_and_planning_sections_exist():
    text = _text(BLUEPRINT)
    assert "Gateway\n  -> RecoveryExecutionPlan\n  -> RecoveryExecutor\n  -> RecoveryStateTransition\n  -> RecoveryCheckpoint\n  -> RecoveryRollback\n  -> RecoveryRetry" in text
    for heading in (
        "## Ownership Boundaries",
        "## Implementation Sequence",
        "## Forbidden Shortcuts",
        "## Dependency Graph",
        "## Supervisor, Operator, Native Runtime Integration Points",
    ):
        assert heading in text


def test_package_265_explicitly_says_no_runtime_wiring_or_implementation():
    text = _text(BLUEPRINT)
    assert "No runtime wiring in Package 265." in text
    assert "Package 265 does not create runtime modules" in text
    assert "Package 265 starts none of these steps." in text


def test_package_265_forbidden_runtime_behaviors_are_documented():
    text = _text(BLUEPRINT)
    for phrase in (
        "Package 265 must not create runtime modules.",
        "Package 265 must not modify runtime code.",
        "Package 265 must not modify gateway code.",
        "Package 265 must not implement executor behavior.",
        "Package 265 must not implement state transition behavior.",
        "Package 265 must not implement checkpoint behavior.",
        "Package 265 must not implement rollback behavior.",
        "Package 265 must not implement retry behavior.",
        "Package 265 must not wire recovery runtime modules.",
        "Package 265 must not call or import existing recovery bridge, executor, adapter, or integration modules.",
        "Package 265 must not add public runtime APIs.",
        "Package 265 must not mutate runtime state.",
    ):
        assert phrase in text


def test_package_265_sequence_entry_exists():
    section = _package_265_entry()
    assert "## Package 265" in section
    assert "Package 265: Runtime Recovery Implementation Blueprint" in section
    assert "Architecture/documentation only." in section
    assert "No runtime wiring in Package 265." in section
    assert "Final decision: GO. Next package: Package 266." in section
