from pathlib import Path


DOC = Path("docs/runtime_recovery_runtime_wiring.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_153_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 153")
    end = text.find("## Package 154", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_runtime_wiring_doc_exists():
    assert DOC.exists()


def test_runtime_wiring_documents_required_future_points():
    text = _text(DOC)
    for phrase in (
        "## Purpose",
        "## Ownership Boundary",
        "## Scheduler Preparation",
        "## Operator Preparation",
        "## Runtime Supervisor Preparation",
        "## Native Runtime Preparation",
        "## Forbidden Implementation",
        "## GO / NO-GO",
        "## Next Package",
    ):
        assert phrase in text
    for point in (
        "Scheduler",
        "Operator",
        "Runtime Supervisor",
        "Native Runtime",
    ):
        assert point in text


def test_runtime_wiring_is_documentation_only_with_no_imports():
    text = _text(DOC)
    assert "Documented only" in text
    for token in (
        "import ",
        "from ",
        "scheduler.schedule(",
        "dispatcher.dispatch(",
        "operator.apply(",
        "subprocess.",
        "open(",
        ".write(",
        "Path(",
    ):
        assert token not in text


def test_runtime_wiring_forbidden_implementation_is_explicit():
    text = _text(DOC)
    for forbidden in (
        "execute Recovery",
        "schedule work",
        "dispatch commands",
        "persist Recovery state",
        "replay Recovery",
        "emit audit records",
        "emit journal records",
        "perform file IO",
        "call subprocess",
        "mutate runtime state",
        "modify runtime execution modules",
    ):
        assert forbidden in text


def test_package_sequence_includes_package_153_and_next_recommendation():
    entry = _package_153_entry()
    assert "## Package 153" in entry
    assert "Recovery Runtime Wiring Preparation" in entry
    assert "docs/runtime_recovery_runtime_wiring.md" in entry
    assert "python -m pytest tests/test_runtime_recovery_runtime_wiring.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 154" in entry
