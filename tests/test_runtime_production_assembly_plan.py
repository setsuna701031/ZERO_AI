from pathlib import Path


ASSEMBLY_PLAN = Path("docs/runtime_production_assembly_plan.md")
ASSEMBLY_GAP_INVENTORY = Path("docs/runtime_assembly_gap_inventory.md")
ASSEMBLY_BOUNDARY_SEAL = Path("docs/runtime_assembly_boundary_seal.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
THIS_TEST = Path("tests/test_runtime_production_assembly_plan.py")

ASSEMBLY_GAPS = (
    "environment resolver",
    "config loader",
    "local runtime wrapper",
    "operator console entry",
    "health validation",
    "package verification",
)

INHERITED_SEALS = (
    "RC freeze guarantees inherited.",
    "Production entry seal inherited.",
    "Package boundary seal inherited.",
)

OWNERSHIP_GUARANTEES = (
    "Scheduler remains owner of scheduling.",
    "Executor remains owner of execution.",
    "Operator remains approval boundary.",
    "Recovery remains disabled.",
)

BOUNDARY_GUARANTEES = (
    "Assembly planning only.",
    "No execution authority.",
    "No scheduler ownership change.",
    "No executor ownership change.",
    "No recovery enablement.",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assembly_package_text() -> str:
    text = _text(PACKAGE_SEQUENCE)
    marker = "## Package 545"
    assert marker in text
    return text[text.index(marker) :]


def test_packages_545_to_552_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("545", "546", "547", "548", "549", "550", "551", "552"):
        assert f"## Package {package_number}" in text

    assert "Runtime Production Assembly Plan" in text
    assert "Documentation/test only." in text


def test_production_assembly_docs_exist():
    assert ASSEMBLY_PLAN.exists()
    assert ASSEMBLY_GAP_INVENTORY.exists()
    assert ASSEMBLY_BOUNDARY_SEAL.exists()


def test_inherited_seals_are_documented():
    text = _text(ASSEMBLY_PLAN)
    for seal in INHERITED_SEALS:
        assert seal in text

    boundary_text = _text(ASSEMBLY_BOUNDARY_SEAL)
    for seal in INHERITED_SEALS:
        assert seal in boundary_text


def test_no_autonomous_activation():
    for path in (ASSEMBLY_PLAN, ASSEMBLY_GAP_INVENTORY, ASSEMBLY_BOUNDARY_SEAL):
        text = _text(path)
        assert "No autonomous activation." in text
        assert "Autonomous activation enabled." not in text


def test_no_runtime_mutation():
    for path in (ASSEMBLY_PLAN, ASSEMBLY_GAP_INVENTORY, ASSEMBLY_BOUNDARY_SEAL):
        text = _text(path)
        assert "No runtime mutation." in text
        assert "Runtime mutation enabled." not in text


def test_scheduler_executor_and_operator_boundaries_remain():
    for path in (ASSEMBLY_PLAN, ASSEMBLY_GAP_INVENTORY, ASSEMBLY_BOUNDARY_SEAL):
        text = _text(path)
        for guarantee in OWNERSHIP_GUARANTEES:
            assert guarantee in text


def test_recovery_remains_disabled_without_enablement():
    for path in (ASSEMBLY_PLAN, ASSEMBLY_GAP_INVENTORY, ASSEMBLY_BOUNDARY_SEAL):
        text = _text(path)
        assert "Recovery remains disabled." in text
        assert "No recovery enablement." in text or path != ASSEMBLY_BOUNDARY_SEAL


def test_assembly_gap_inventory_records_remaining_gaps_without_implementation():
    text = _text(ASSEMBLY_GAP_INVENTORY)
    assert "These gaps are not implemented by this package." in text
    for gap in ASSEMBLY_GAPS:
        assert gap in text
    assert text.count("Do not implement here") == len(ASSEMBLY_GAPS)


def test_assembly_boundary_seal_guarantees_planning_only():
    text = _text(ASSEMBLY_BOUNDARY_SEAL)
    for guarantee in BOUNDARY_GUARANTEES:
        assert guarantee in text
    assert "No startup scripts." in text
    assert "No services." in text
    assert "No behavior path changes." in text


def test_no_runtime_imports_in_focused_test():
    lines = _text(THIS_TEST).splitlines()
    import_lines = [
        line
        for line in lines
        if line.startswith("import ") or line.startswith("from ")
    ]
    assert import_lines == ["from pathlib import Path"]


def test_package_sequence_records_scope_and_validation():
    text = _assembly_package_text()
    assert "do not modify core/runtime" in text
    assert "do not modify scheduler" in text
    assert "do not modify executor" in text
    assert "do not create startup scripts" in text
    assert "do not create services" in text
    assert "do not enable runtime execution" in text
    assert "do not enable recovery activation" in text
    assert "do not change behavior paths" in text
    assert "py -m pytest tests/test_runtime_production_assembly_plan.py -q" in text
    assert "do not run full suite, nightly, regression, or long validation" in text
