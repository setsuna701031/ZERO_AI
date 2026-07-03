from pathlib import Path


PRODUCTION_REVIEW = Path("docs/runtime_production_entry_review.md")
PRODUCTION_BOUNDARY = Path("docs/runtime_production_boundary.md")
PRODUCTION_GAP_INVENTORY = Path("docs/runtime_production_gap_inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
THIS_TEST = Path("tests/test_runtime_production_entry.py")

PRODUCTION_GAPS = (
    "packaging",
    "local service wrapper",
    "configuration",
    "deployment artifact",
    "user-facing control surface",
)

BOUNDARIES = (
    "Scheduler remains owner of scheduling.",
    "Executor remains owner of execution.",
    "Operator remains approval boundary.",
    "Observability remains read-only.",
    "Recovery remains disabled until explicit future activation package.",
)

FORBIDDEN_ENABLED_PHRASES = (
    "recovery activation enabled.",
    "autonomous execution enabled.",
    "scheduler ownership transfer.",
    "executor ownership transfer.",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _production_package_text() -> str:
    text = _text(PACKAGE_SEQUENCE)
    marker = "## Package 529"
    assert marker in text
    return text[text.index(marker) :]


def test_packages_529_to_536_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("529", "530", "531", "532", "533", "534", "535", "536"):
        assert f"## Package {package_number}" in text

    assert "Runtime Production Entry Seal" in text
    assert "Documentation/test only." in text


def test_production_entry_docs_exist():
    assert PRODUCTION_REVIEW.exists()
    assert PRODUCTION_BOUNDARY.exists()
    assert PRODUCTION_GAP_INVENTORY.exists()


def test_rc_freeze_and_release_readiness_are_referenced():
    for path in (PRODUCTION_REVIEW, PRODUCTION_BOUNDARY, PRODUCTION_GAP_INVENTORY):
        text = _text(path)
        assert "RC freeze completed." in text

    review_text = _text(PRODUCTION_REVIEW)
    assert "Release readiness completed." in review_text
    assert "Production entry criteria" in review_text


def test_production_boundary_preserves_ownership():
    text = _text(PRODUCTION_BOUNDARY)
    for boundary in BOUNDARIES:
        assert boundary in text


def test_no_recovery_activation_or_autonomous_execution_enabled():
    for path in (PRODUCTION_REVIEW, PRODUCTION_BOUNDARY, PRODUCTION_GAP_INVENTORY):
        text = _text(path)
        assert "Recovery remains disabled until explicit future activation package." in text
        assert "No recovery activation enabled." in text or "no recovery activation enabled" in text.lower()
        assert "No autonomous execution enabled." in text or "no autonomous execution enabled" in text.lower()


def test_no_scheduler_or_executor_ownership_transfer():
    for path in (PRODUCTION_REVIEW, PRODUCTION_BOUNDARY, PRODUCTION_GAP_INVENTORY):
        text = _text(path)
        assert "No scheduler ownership transfer." in text or "no scheduler ownership transfer" in text.lower()
        assert "No executor ownership transfer." in text or "no executor ownership transfer" in text.lower()


def test_forbidden_enabled_phrases_only_appear_as_negative_guarantees():
    for path in (PRODUCTION_REVIEW, PRODUCTION_BOUNDARY, PRODUCTION_GAP_INVENTORY):
        text = _text(path).lower()
        for phrase in FORBIDDEN_ENABLED_PHRASES:
            assert f"no {phrase}" in text or f"forbidden direct activation path: no {phrase}" in text


def test_production_gap_inventory_lists_remaining_gaps_without_implementation():
    text = _text(PRODUCTION_GAP_INVENTORY)
    assert "These gaps are not implemented by this package." in text
    for gap in PRODUCTION_GAPS:
        assert gap in text
    assert text.count("Do not implement here") == len(PRODUCTION_GAPS)


def test_no_runtime_imports_in_focused_test():
    lines = _text(THIS_TEST).splitlines()
    import_lines = [
        line
        for line in lines
        if line.startswith("import ") or line.startswith("from ")
    ]
    assert import_lines == ["from pathlib import Path"]


def test_package_sequence_records_scope_and_validation():
    text = _production_package_text()
    assert "no core/runtime changes" in text
    assert "no scheduler changes" in text
    assert "no executor changes" in text
    assert "no deployment scripts" in text
    assert "no service files" in text
    assert "no behavior changes" in text
    assert "py -m pytest tests/test_runtime_production_entry.py -q" in text
    assert "do not run full suite, nightly, regression, or long validation" in text
