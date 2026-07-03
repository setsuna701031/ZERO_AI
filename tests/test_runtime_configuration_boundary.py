from pathlib import Path


CONFIG_BOUNDARY = Path("docs/runtime_configuration_boundary.md")
CONFIG_GAP_INVENTORY = Path("docs/runtime_configuration_gap_inventory.md")
CONFIG_READINESS_REVIEW = Path("docs/runtime_configuration_readiness_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
THIS_TEST = Path("tests/test_runtime_configuration_boundary.py")

CONFIG_GAPS = (
    "config file format",
    "environment discovery",
    "validation layer",
    "secrets handling boundary",
    "local machine profile",
)

INHERITED_SEALS = (
    "RC freeze inherited.",
    "Production entry inherited.",
    "Package boundary inherited.",
    "Assembly boundary inherited.",
)

CONFIG_GUARANTEES = (
    "No runtime activation authority.",
    "No scheduler ownership transfer.",
    "No executor ownership transfer.",
    "No recovery enable switch.",
    "No autonomous execution through config.",
)

FORBIDDEN_CONFIG_AUTHORITY = (
    "Config cannot trigger execution.",
    "Config cannot enable recovery.",
    "Config cannot bypass scheduler.",
    "Config cannot mutate runtime state.",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _configuration_package_text() -> str:
    text = _text(PACKAGE_SEQUENCE)
    marker = "## Package 553"
    assert marker in text
    return text[text.index(marker) :]


def test_packages_553_to_560_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("553", "554", "555", "556", "557", "558", "559", "560"):
        assert f"## Package {package_number}" in text

    assert "Runtime Production Configuration Boundary" in text
    assert "Documentation/test only." in text


def test_configuration_boundary_docs_exist():
    assert CONFIG_BOUNDARY.exists()
    assert CONFIG_GAP_INVENTORY.exists()
    assert CONFIG_READINESS_REVIEW.exists()


def test_inherited_seals_are_documented():
    for path in (CONFIG_BOUNDARY, CONFIG_READINESS_REVIEW):
        text = _text(path)
        for seal in INHERITED_SEALS:
            assert seal in text


def test_no_runtime_activation_authority():
    for path in (CONFIG_BOUNDARY, CONFIG_GAP_INVENTORY, CONFIG_READINESS_REVIEW):
        text = _text(path)
        assert "No runtime activation authority." in text or "Config cannot provide runtime activation authority." in text
        assert "Runtime activation authority enabled." not in text


def test_no_scheduler_or_executor_ownership_transfer():
    for path in (CONFIG_BOUNDARY, CONFIG_GAP_INVENTORY, CONFIG_READINESS_REVIEW):
        text = _text(path)
        assert "No scheduler ownership transfer." in text or "Config cannot transfer scheduler ownership." in text
        assert "No executor ownership transfer." in text or "Config cannot transfer executor ownership." in text


def test_no_recovery_enable_switch():
    for path in (CONFIG_BOUNDARY, CONFIG_GAP_INVENTORY, CONFIG_READINESS_REVIEW):
        text = _text(path)
        assert "Config cannot enable recovery." in text or "No recovery enable switch." in text
        assert "Recovery enable switch added." not in text


def test_no_autonomous_execution_through_config():
    for path in (CONFIG_BOUNDARY, CONFIG_GAP_INVENTORY, CONFIG_READINESS_REVIEW):
        text = _text(path)
        assert "No autonomous execution through config." in text or "Config cannot provide autonomous execution authority." in text
        assert "Autonomous execution through config is enabled." not in text


def test_forbidden_configuration_authority_is_documented():
    text = _text(CONFIG_BOUNDARY)
    for phrase in FORBIDDEN_CONFIG_AUTHORITY:
        assert phrase in text


def test_configuration_gap_inventory_records_remaining_gaps_without_implementation():
    text = _text(CONFIG_GAP_INVENTORY)
    assert "These gaps are not implemented by this package." in text
    for gap in CONFIG_GAPS:
        assert gap in text
    assert text.count("Do not implement here") == len(CONFIG_GAPS)


def test_readiness_review_has_go_no_go_and_requirements():
    text = _text(CONFIG_READINESS_REVIEW)
    assert "GO / NO-GO Review" in text
    assert "GO criteria:" in text
    assert "NO-GO criteria:" in text
    assert "Requirements Before Implementation" in text
    for guarantee in CONFIG_GUARANTEES:
        assert guarantee in text


def test_no_runtime_imports_in_focused_test():
    lines = _text(THIS_TEST).splitlines()
    import_lines = [
        line
        for line in lines
        if line.startswith("import ") or line.startswith("from ")
    ]
    assert import_lines == ["from pathlib import Path"]


def test_package_sequence_records_scope_and_validation():
    text = _configuration_package_text()
    assert "do not modify core/runtime" in text
    assert "do not modify scheduler" in text
    assert "do not modify executor" in text
    assert "do not create startup scripts" in text
    assert "do not create services" in text
    assert "do not create config loader implementation" in text
    assert "do not enable runtime execution" in text
    assert "do not enable recovery activation" in text
    assert "py -m pytest tests/test_runtime_configuration_boundary.py -q" in text
    assert "do not run full suite, nightly, regression, or long validation" in text
