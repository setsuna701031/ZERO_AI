from pathlib import Path


DOC = Path("docs/runtime_recovery_wiring_readiness_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 166")
    end = text.find("## Package 167", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_wiring_readiness_review_doc_exists():
    assert DOC.exists()


def test_wiring_readiness_review_required_sections_exist():
    text = _text(DOC)
    for section in (
        "## Purpose",
        "## Package 159-162 Adapter Boundary Review",
        "## Package 163 Contract Review",
        "## Package 164 Gate Review",
        "## Package 165 Controlled Activation Review",
        "## Readiness Decision",
        "## GO / NO-GO",
        "## Next Package",
    ):
        assert section in text


def test_wiring_readiness_review_preserves_passive_adapter_boundaries():
    text = _text(DOC)
    for phrase in (
        "Package 159 Scheduler Passive Adapter remains adapter-only",
        "Package 160 Operator Passive Adapter remains adapter-only",
        "Package 161 Runtime Supervisor Passive Adapter remains adapter-only",
        "Package 162 Native Runtime Passive Adapter remains adapter-only",
        "Each adapter preserves activation, authority, intent, bridge, and executor references",
        "Each adapter denies runtime calls",
    ):
        assert phrase in text


def test_wiring_readiness_review_confirms_gate_off_and_no_activation():
    text = _text(DOC)
    for phrase in (
        "activation gate to remain OFF by default",
        "keeps activation gate OFF by default",
        "`activation_gate_enabled` as `false`",
        "`activation_allowed` as `false`",
        "`runtime_mainline_wiring_allowed` as `false`",
        "Runtime hook wiring is ready for a future review package, but it is not ready for runtime activation",
        "Activation remains OFF",
        "Runtime mainline wiring remains forbidden",
    ):
        assert phrase in text


def test_wiring_readiness_review_go_no_go_and_sequence_entry():
    text = _text(DOC)
    assert "Final decision: GO" in text
    assert "Next package: Package 167" in text

    entry = _package_entry()
    assert "## Package 166" in entry
    assert "Runtime Wiring Readiness Review" in entry
    assert "docs/runtime_recovery_wiring_readiness_review.md" in entry
    assert "tests/test_runtime_recovery_wiring_readiness_review.py" in entry
    assert "python -m pytest tests/test_runtime_recovery_wiring_readiness_review.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 167" in entry


def test_wiring_readiness_review_has_no_implementation_tokens():
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
