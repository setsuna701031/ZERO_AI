from pathlib import Path


PACKAGE_BOUNDARY = Path("docs/runtime_production_package_boundary.md")
DISTRIBUTION_GAP_INVENTORY = Path("docs/runtime_distribution_gap_inventory.md")
PACKAGING_READINESS_REVIEW = Path("docs/runtime_packaging_readiness_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
THIS_TEST = Path("tests/test_runtime_production_package_boundary.py")

FROZEN_GUARANTEES = (
    "Scheduler remains frozen.",
    "Executor remains frozen.",
    "Recovery activation disabled.",
    "Runtime ownership migration forbidden.",
    "No autonomous execution enablement.",
)

DISTRIBUTION_GAPS = (
    "configuration loading",
    "environment validation",
    "dependency check",
    "operator entry",
    "deployment wrapper",
)

FORBIDDEN_SCOPE = (
    "No core/runtime changes.",
    "No scheduler changes.",
    "No executor changes.",
    "No service files.",
    "No startup scripts.",
    "No deployment scripts.",
    "No behavior changes.",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _production_package_boundary_text() -> str:
    text = _text(PACKAGE_SEQUENCE)
    marker = "## Package 537"
    assert marker in text
    return text[text.index(marker) :]


def test_packages_537_to_544_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("537", "538", "539", "540", "541", "542", "543", "544"):
        assert f"## Package {package_number}" in text

    assert "Runtime Production Package Boundary" in text
    assert "Documentation/test only." in text


def test_production_package_boundary_docs_exist():
    assert PACKAGE_BOUNDARY.exists()
    assert DISTRIBUTION_GAP_INVENTORY.exists()
    assert PACKAGING_READINESS_REVIEW.exists()


def test_scheduler_and_executor_remain_frozen():
    for path in (PACKAGE_BOUNDARY, DISTRIBUTION_GAP_INVENTORY, PACKAGING_READINESS_REVIEW):
        text = _text(path)
        assert "Scheduler remains frozen." in text
        assert "Executor remains frozen." in text


def test_recovery_activation_disabled():
    for path in (PACKAGE_BOUNDARY, DISTRIBUTION_GAP_INVENTORY, PACKAGING_READINESS_REVIEW):
        text = _text(path)
        assert "Recovery activation disabled." in text
        assert "Recovery activation enabled." not in text


def test_no_runtime_ownership_migration():
    for path in (PACKAGE_BOUNDARY, DISTRIBUTION_GAP_INVENTORY, PACKAGING_READINESS_REVIEW):
        text = _text(path)
        assert "Runtime ownership migration forbidden." in text
        assert "runtime ownership migration occurs" in text or path != PACKAGING_READINESS_REVIEW


def test_no_autonomous_execution_enablement():
    for path in (PACKAGE_BOUNDARY, DISTRIBUTION_GAP_INVENTORY, PACKAGING_READINESS_REVIEW):
        text = _text(path)
        assert "No autonomous execution enablement." in text
        assert "Autonomous execution enabled." not in text


def test_frozen_rc_inheritance_from_521_to_536():
    text = _text(PACKAGE_BOUNDARY)
    assert "Frozen RC Inheritance From Packages 521-536" in text
    assert "Frozen RC inheritance from Packages 521-536 remains in force." in text
    assert "RC freeze completed." in text
    assert "Production entry completed." in text
    for guarantee in FROZEN_GUARANTEES:
        assert guarantee in text


def test_distribution_gap_inventory_records_remaining_gaps_without_implementation():
    text = _text(DISTRIBUTION_GAP_INVENTORY)
    assert "These gaps are not implemented by this package." in text
    for gap in DISTRIBUTION_GAPS:
        assert gap in text
    assert text.count("Do not implement here") == len(DISTRIBUTION_GAPS)


def test_packaging_readiness_has_go_no_go_and_required_guarantees():
    text = _text(PACKAGING_READINESS_REVIEW)
    assert "GO / NO-GO Decision" in text
    assert "GO criteria:" in text
    assert "NO-GO criteria:" in text
    assert "Required Guarantees" in text
    assert "Production Entry Status" in text
    for guarantee in FROZEN_GUARANTEES:
        assert guarantee in text
    for forbidden in FORBIDDEN_SCOPE:
        assert forbidden in text


def test_no_runtime_imports_in_focused_test():
    lines = _text(THIS_TEST).splitlines()
    import_lines = [
        line
        for line in lines
        if line.startswith("import ") or line.startswith("from ")
    ]
    assert import_lines == ["from pathlib import Path"]


def test_package_sequence_records_scope_and_validation():
    text = _production_package_boundary_text()
    assert "no core/runtime changes" in text
    assert "no scheduler changes" in text
    assert "no executor changes" in text
    assert "no service files" in text
    assert "no startup scripts" in text
    assert "do not enable runtime activation" in text
    assert "py -m pytest tests/test_runtime_production_package_boundary.py -q" in text
    assert "do not run full suite, nightly, regression, or long validation" in text
