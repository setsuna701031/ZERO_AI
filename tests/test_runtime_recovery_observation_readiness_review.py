from pathlib import Path


DOC = Path("docs/runtime_recovery_observation_readiness_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 178")
    end = text.find("## Package 179", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_observation_readiness_review_doc_exists():
    assert DOC.exists()


def test_observation_readiness_review_required_sections_exist():
    text = _text(DOC)
    for section in (
        "## Purpose",
        "## Package 175 Observation Binding Review",
        "## Package 176 Surface Probe Helper Review",
        "## Package 177 Observation Report Review",
        "## Boundary Preservation",
        "## Readiness Decision",
        "## GO / NO-GO",
        "## Next Package",
    ):
        assert section in text


def test_observation_readiness_review_confirms_observe_only_defaults():
    text = _text(DOC)
    assert "`runtime_recovery_single_entry`" in text
    assert "Observation binding data is not permission to activate Recovery" in text
    for phrase in (
        "`observe_only` as `true`",
        "`dry_run` as `true`",
        "`surface_probe_allowed` as `true`",
        "`surface_probe_executed` as `false`",
        "`runtime_surface_touched` as `false`",
        "`event_emitted` as `false`",
        "`recovery_enabled` as `false`",
    ):
        assert phrase in text


def test_observation_readiness_review_preserves_boundaries():
    text = _text(DOC)
    for phrase in (
        "Packages 171 through 174 remain dry-run only",
        "Package 168 kill-switch OFF semantics remain intact",
        "Package 169 canonical event schema remains intact",
        "source surface information",
        "entry identifier",
        "route identifier",
        "gate state",
        "real runtime event emission blocked",
        "runtime surface untouched",
        "Runtime Recovery is not ready for runtime activation",
        "Activation remains OFF",
        "Recovery remains disabled by default",
    ):
        assert phrase in text


def test_observation_readiness_review_go_no_go_and_sequence_entry():
    text = _text(DOC)
    assert "Final decision: GO" in text
    assert "Next package: Package 179" in text

    entry = _package_entry()
    assert "## Package 178" in entry
    assert "Runtime Recovery Observation Readiness Review" in entry
    assert "docs/runtime_recovery_observation_readiness_review.md" in entry
    assert "tests/test_runtime_recovery_observation_readiness_review.py" in entry
    assert "python -m pytest tests/test_runtime_recovery_observation_readiness_review.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 179" in entry


def test_observation_readiness_review_has_no_implementation_tokens():
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
