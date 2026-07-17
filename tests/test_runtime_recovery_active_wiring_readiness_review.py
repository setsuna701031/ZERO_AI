from pathlib import Path


DOC = Path("docs/runtime_recovery_active_wiring_readiness_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 170")
    end = text.find("## Package 171", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_active_wiring_readiness_review_doc_exists():
    assert DOC.exists()


def test_active_wiring_readiness_review_required_sections_exist():
    text = _text(DOC)
    for section in (
        "## Purpose",
        "## Package 167 Single Entry Review",
        "## Package 168 Kill Switch Review",
        "## Package 169 Event Route Review",
        "## Boundary Preservation",
        "## Readiness Decision",
        "## GO / NO-GO",
        "## Next Package",
    ):
        assert section in text


def test_active_wiring_readiness_review_confirms_single_entry_and_kill_switch_safe():
    text = _text(DOC)
    assert "`runtime_recovery_single_entry`" in text
    assert "Multiple runtime surfaces remain forbidden" in text
    assert "defaults to disabled, off, and safe" in text
    for phrase in (
        "`kill_switch_enabled` as `false`",
        "`kill_switch_state` as `off`",
        "`safe_mode` as `true`",
        "`recovery_enabled` as `false`",
    ):
        assert phrase in text


def test_active_wiring_readiness_review_confirms_canonical_event_and_gate_off():
    text = _text(DOC)
    for phrase in (
        "canonical event schema",
        "source surface information",
        "entry identifier",
        "route identifier",
        "gate state",
        "Package 163 through Package 166 gate OFF semantics remain intact",
        "Runtime Recovery active wiring is not ready for runtime activation",
        "Activation remains OFF",
        "Recovery remains disabled by default",
    ):
        assert phrase in text


def test_active_wiring_readiness_review_go_no_go_and_sequence_entry():
    text = _text(DOC)
    assert "Final decision: GO" in text
    assert "Next package: Package 171" in text

    entry = _package_entry()
    assert "## Package 170" in entry
    assert "Runtime Recovery Active Wiring Readiness Review" in entry
    assert "docs/runtime_recovery_active_wiring_readiness_review.md" in entry
    assert "tests/test_runtime_recovery_active_wiring_readiness_review.py" in entry
    assert "python -m pytest tests/test_runtime_recovery_active_wiring_readiness_review.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 171" in entry


def test_active_wiring_readiness_review_has_no_implementation_tokens():
    text = _text(DOC)
    for token in (
        "def ",
        "class ",
        "import ",
        "scheduler.",
        "operator.",
        "dispatcher.",
        "supervisor.",
        "native_runtime.",
        "subprocess.",
        "open(",
        ".write(",
        "Path(",
    ):
        assert token not in text
