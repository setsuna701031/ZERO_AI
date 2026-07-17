from pathlib import Path


DOC = Path("docs/runtime_recovery_activation_readiness_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_155_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 155")
    end = text.find("## Package 156", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_activation_readiness_review_doc_exists():
    assert DOC.exists()


def test_readiness_review_has_required_sections():
    text = _text(DOC)
    for section in (
        "## Purpose",
        "## Package 151 Executor Review",
        "## Package 152 Runtime Integration Review",
        "## Package 153 Wiring Review",
        "## Package 154 End-to-End Review",
        "## Runtime Hook Absence",
        "## Activation Readiness Decision",
        "## GO / NO-GO",
        "## Next Package",
    ):
        assert section in text


def test_readiness_review_verifies_packages_151_through_154():
    text = _text(DOC)
    assert "Package 151 executor output is side-effect free" in text
    assert "`side_effects_performed` is `false`" in text
    assert "`executes_recovery` is `false`" in text
    assert "Package 152 runtime integration is passive" in text
    assert "`external_runtime_invoked` is `false`" in text
    assert "Package 153 wiring is documentation-only" in text
    assert "Package 154 end-to-end contract preserves references" in text


def test_readiness_review_requires_reference_preservation():
    text = _text(DOC)
    for reference in (
        "authority reference is preserved",
        "intent reference is preserved",
        "bridge reference is preserved",
        "executor boundary reference is preserved",
        "executor report reference is preserved",
    ):
        assert reference in text


def test_readiness_review_confirms_no_runtime_hooks_exist_yet():
    text = _text(DOC)
    for hook in (
        "No scheduler, operator, dispatcher, runtime supervisor, or native runtime hook exists yet",
        "Scheduler admission hook",
        "Dispatcher command hook",
        "Operator runtime hook",
        "Runtime Supervisor hook",
        "Native Runtime execution hook",
    ):
        assert hook in text


def test_readiness_review_go_no_go_and_sequence_entry():
    text = _text(DOC)
    assert "Final decision: GO" in text
    assert "Next package: Package 156" in text

    entry = _package_155_entry()
    assert "## Package 155" in entry
    assert "Recovery Runtime Activation Readiness Review" in entry
    assert "docs/runtime_recovery_activation_readiness_review.md" in entry
    assert "tests/test_runtime_recovery_activation_readiness_review.py" in entry
    assert "python -m pytest tests/test_runtime_recovery_activation_readiness_review.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 156" in entry


def test_readiness_review_has_no_implementation_tokens():
    text = _text(DOC)
    for token in (
        "def ",
        "class ",
        "import ",
        "scheduler.schedule(",
        "dispatcher.dispatch(",
        "operator.apply(",
        "subprocess.",
        "open(",
        ".write(",
        "Path(",
    ):
        assert token not in text
