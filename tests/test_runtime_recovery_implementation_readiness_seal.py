from pathlib import Path


SEAL = Path("docs/runtime_recovery_implementation_readiness_seal.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_267_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 267")
    end = text.find("## Package 268", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_package_267_readiness_seal_exists_with_go_decision():
    assert SEAL.exists()
    text = _text(SEAL)
    assert "Runtime Recovery Implementation Readiness Seal" in text
    assert "GO / NO-GO result: GO." in text
    assert "Readiness decision: GO for starting Package 268 runtime wiring." in text
    assert "Final decision: GO. Next package: Package 268." in text


def test_package_267_required_sections_exist():
    text = _text(SEAL)
    for heading in (
        "## Readiness Checklist",
        "## Required Contracts Completed",
        "## Required Reviews Completed",
        "## Boundary Matrix",
        "## Implementation Risk Table",
        "## Forbidden Runtime Behaviors",
        "## Final Decision",
    ):
        assert heading in text


def test_package_267_explicitly_says_no_runtime_wiring_or_implementation():
    text = _text(SEAL)
    assert "No runtime wiring or implementation in Package 267." in text
    assert "It does not authorize Package 267 to implement runtime wiring" in text
    assert "Package 267 does not create runtime modules" in text


def test_package_267_forbidden_runtime_behaviors_are_documented():
    text = _text(SEAL)
    for phrase in (
        "Package 267 must not create runtime modules.",
        "Package 267 must not modify runtime code.",
        "Package 267 must not modify gateway code.",
        "Package 267 must not implement executor behavior.",
        "Package 267 must not implement state transition behavior.",
        "Package 267 must not implement checkpoint behavior.",
        "Package 267 must not implement rollback behavior.",
        "Package 267 must not implement retry behavior.",
        "Package 267 must not wire recovery runtime modules.",
        "Package 267 must not call or import existing recovery bridge, executor, adapter, or integration modules.",
        "Package 267 must not add public runtime APIs.",
        "Package 267 must not mutate runtime state.",
        "Package 267 must not invoke endpoints.",
        "Package 267 must not register hooks.",
    ):
        assert phrase in text


def test_package_sequence_contains_265_266_267():
    text = _text(PACKAGE_SEQUENCE)
    assert "## Package 265" in text
    assert "## Package 266" in text
    assert "## Package 267" in text
    assert "Package 265: Runtime Recovery Implementation Blueprint" in text
    assert "Package 266: Runtime Recovery Wiring Phase Plan" in text
    assert "Package 267: Runtime Recovery Implementation Readiness Seal" in text


def test_package_267_sequence_entry_exists():
    section = _package_267_entry()
    assert "## Package 267" in section
    assert "Package 267: Runtime Recovery Implementation Readiness Seal" in section
    assert "Review/documentation only." in section
    assert "No runtime wiring or implementation in Package 267." in section
    assert "Final decision: GO. Next package: Package 268." in section
