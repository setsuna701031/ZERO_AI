from pathlib import Path


PLAN = Path("docs/runtime_recovery_wiring_phase_plan.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_266_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 266")
    end = text.find("## Package 267", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_package_266_phase_plan_exists_and_includes_phases_1_to_5():
    assert PLAN.exists()
    text = _text(PLAN)
    for heading in (
        "## Phase 1: Inert Wiring Only",
        "## Phase 2: Executor Skeleton",
        "## Phase 3: Checkpoint/Rollback/Retry Skeletons",
        "## Phase 4: Supervised Execution",
        "## Phase 5: Activation Readiness",
    ):
        assert heading in text


def test_package_266_required_plan_sections_exist():
    text = _text(PLAN)
    for phrase in (
        "Allowed future files:",
        "Forbidden future files:",
        "## Rollback Plan",
        "## Validation Plan",
        "Long validation must remain local, not Codex.",
    ):
        assert phrase in text


def test_package_266_explicitly_says_no_runtime_wiring_or_implementation():
    text = _text(PLAN)
    assert "No runtime wiring or implementation in Package 266." in text
    assert "Package 266 does not create runtime modules" in text
    assert "Package 266 does not implement rollback behavior." in text


def test_package_266_forbidden_runtime_behaviors_are_documented():
    text = _text(PLAN)
    for phrase in (
        "Package 266 must not create runtime modules.",
        "Package 266 must not modify runtime code.",
        "Package 266 must not modify gateway code.",
        "Package 266 must not implement executor behavior.",
        "Package 266 must not implement state transition behavior.",
        "Package 266 must not implement checkpoint behavior.",
        "Package 266 must not implement rollback behavior.",
        "Package 266 must not implement retry behavior.",
        "Package 266 must not wire recovery runtime modules.",
        "Package 266 must not call or import existing recovery bridge, executor, adapter, or integration modules.",
        "Package 266 must not add public runtime APIs.",
        "Package 266 must not mutate runtime state.",
    ):
        assert phrase in text


def test_package_266_sequence_entry_exists():
    section = _package_266_entry()
    assert "## Package 266" in section
    assert "Package 266: Runtime Recovery Wiring Phase Plan" in section
    assert "Architecture/documentation only." in section
    assert "No runtime wiring or implementation in Package 266." in section
    assert "Final decision: GO. Next package: Package 267." in section
