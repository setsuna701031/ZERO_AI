from pathlib import Path


READINESS_REVIEW = Path("docs/runtime_release_readiness_review.md")
BOUNDARY_SEAL = Path("docs/runtime_release_boundary_seal.md")
GAP_INVENTORY = Path("docs/runtime_release_gap_inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

COMPLETED_AREAS = (
    "Recovery Closure",
    "Mainline Re-entry",
    "Lifecycle",
    "Observability",
    "Operator Interface",
    "Deployment Readiness",
)

PRESERVED_AUTHORITY = (
    "Recovery remains disabled.",
    "Scheduler ownership unchanged.",
    "Executor ownership unchanged.",
    "Operator boundaries unchanged.",
    "No mutation authority.",
    "No autonomous execution.",
)

FORBIDDEN_RELEASE_WORDING = (
    "release enables activation",
    "release activates runtime",
    "release enables autonomous execution",
    "autonomous execution enabled",
    "recovery execution enabled",
    "release adds mutation authority",
    "release bypasses authority ownership",
)

GAP_FIELDS = (
    "Remaining Runtime Gap",
    "Owner Component",
    "Required Future Package Type",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _release_package_text() -> str:
    text = _text(PACKAGE_SEQUENCE)
    marker = "## Package 513"
    assert marker in text
    return text[text.index(marker) :]


def test_packages_513_to_520_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("513", "514", "515", "516", "517", "518", "519", "520"):
        assert f"## Package {package_number}" in text

    assert "Runtime Release Readiness Seal" in text
    assert "Documentation/test only." in text


def test_release_readiness_docs_exist():
    assert READINESS_REVIEW.exists()
    assert BOUNDARY_SEAL.exists()
    assert GAP_INVENTORY.exists()


def test_go_no_go_criteria_exist():
    text = _text(READINESS_REVIEW)
    assert "GO / NO-GO Criteria" in text
    assert "GO criteria:" in text
    assert "NO-GO criteria:" in text
    assert "Final decision: GO for Runtime Release Readiness Seal" in text


def test_completed_runtime_areas_are_documented():
    text = _text(READINESS_REVIEW)
    assert "Release Readiness Checklist" in text
    assert "Completed Runtime Areas" in text
    assert "Remaining Blocked Areas" in text
    for area in COMPLETED_AREAS:
        assert area in text


def test_recovery_remains_disabled():
    for path in (READINESS_REVIEW, BOUNDARY_SEAL, GAP_INVENTORY):
        text = _text(path)
        assert "Recovery remains disabled." in text
        assert "recovery execution remains blocked" in text.lower() or path == BOUNDARY_SEAL


def test_scheduler_executor_ownership_unchanged():
    for path in (READINESS_REVIEW, BOUNDARY_SEAL, GAP_INVENTORY):
        text = _text(path)
        assert "Scheduler ownership unchanged." in text
        assert "Executor ownership unchanged." in text


def test_release_does_not_add_activation_wording():
    for path in (READINESS_REVIEW, BOUNDARY_SEAL, GAP_INVENTORY):
        lowered = _text(path).lower()
        for phrase in FORBIDDEN_RELEASE_WORDING:
            assert phrase not in lowered

    package_text = _release_package_text().lower()
    for phrase in FORBIDDEN_RELEASE_WORDING:
        assert phrase not in package_text

    boundary_text = _text(BOUNDARY_SEAL)
    assert "Release readiness does not imply activation." in boundary_text
    assert "Release readiness does not enable autonomous execution." in boundary_text


def test_no_mutation_authority_is_added():
    for path in (READINESS_REVIEW, BOUNDARY_SEAL, GAP_INVENTORY):
        text = _text(path)
        assert "No mutation authority." in text
        assert "Mutation authority changes remain blocked." in text or path != READINESS_REVIEW


def test_gap_inventory_records_owner_and_future_package_type():
    text = _text(GAP_INVENTORY)
    for field in GAP_FIELDS:
        assert field in text
    assert "Runtime changes require future packages." in text
    assert "Deployment implementation package" in text
    assert "Recovery execution enablement package" in text


def test_boundary_seal_forbids_runtime_changes():
    text = _text(BOUNDARY_SEAL)
    assert "No runtime module changes." in text
    assert "No scheduler edits." in text
    assert "No executor edits." in text
    assert "No deployment scripts." in text
    assert "No activation edits." in text
    assert "No behavior changes." in text


def test_preserved_authority_is_documented():
    for path in (BOUNDARY_SEAL, GAP_INVENTORY):
        text = _text(path)
        for phrase in PRESERVED_AUTHORITY:
            assert phrase in text
