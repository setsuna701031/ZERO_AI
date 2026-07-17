from pathlib import Path


DOC = Path("docs/runtime_recovery_dry_run_integration_readiness_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 174")
    end = text.find("## Package 175", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_dry_run_integration_readiness_review_doc_exists():
    assert DOC.exists()


def test_dry_run_integration_readiness_review_required_sections_exist():
    text = _text(DOC)
    for section in (
        "## Purpose",
        "## Package 171 Binding Contract Review",
        "## Package 172 Dry-Run Binding Helper Review",
        "## Package 173 Dry-Run Route Report Review",
        "## Boundary Preservation",
        "## Readiness Decision",
        "## GO / NO-GO",
        "## Next Package",
    ):
        assert section in text


def test_dry_run_integration_readiness_review_confirms_safe_defaults():
    text = _text(DOC)
    assert "`runtime_recovery_single_entry`" in text
    assert "Prepared binding data is not permission to activate Recovery" in text
    for phrase in (
        "`dry_run` as `true`",
        "`bound_to_runtime` as `false`",
        "`binding_enabled` as `false`",
        "`route_enabled` as `false`",
        "`event_emitted` as `false`",
        "`recovery_enabled` as `false`",
    ):
        assert phrase in text


def test_dry_run_integration_readiness_review_preserves_boundaries():
    text = _text(DOC)
    for phrase in (
        "Package 168 kill-switch OFF semantics remain intact",
        "Package 169 canonical event schema remains intact",
        "source surface information",
        "entry identifier",
        "route identifier",
        "gate state",
        "real runtime event emission blocked",
        "Runtime Recovery is not ready for runtime activation",
        "Activation remains OFF",
        "Recovery remains disabled by default",
    ):
        assert phrase in text


def test_dry_run_integration_readiness_review_go_no_go_and_sequence_entry():
    text = _text(DOC)
    assert "Final decision: GO" in text
    assert "Next package: Package 175" in text

    entry = _package_entry()
    assert "## Package 174" in entry
    assert "Runtime Recovery Dry-Run Integration Readiness Review" in entry
    assert "docs/runtime_recovery_dry_run_integration_readiness_review.md" in entry
    assert "tests/test_runtime_recovery_dry_run_integration_readiness_review.py" in entry
    assert "python -m pytest tests/test_runtime_recovery_dry_run_integration_readiness_review.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 175" in entry


def test_dry_run_integration_readiness_review_has_no_implementation_tokens():
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
