from pathlib import Path


ENV_BOUNDARY = Path("docs/runtime_environment_resolver_boundary.md")
ENV_GAP_INVENTORY = Path("docs/runtime_environment_gap_inventory.md")
ENV_READINESS_REVIEW = Path("docs/runtime_environment_readiness_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
THIS_TEST = Path("tests/test_runtime_environment_resolver_boundary.py")

ENVIRONMENT_GAPS = (
    "Python executable resolution",
    "dependency availability",
    "workspace discovery",
    "filesystem permission checks",
    "runtime directory verification",
    "deployment preparation",
)

INHERITED_SEALS = (
    "Release seal inherited.",
    "RC freeze inherited.",
    "Production entry boundary inherited.",
    "Package boundary inherited.",
    "Assembly boundary inherited.",
    "Configuration boundary inherited.",
)

BOUNDARY_GUARANTEES = (
    "Environment resolver may inspect only.",
    "No execution authority.",
    "No scheduler ownership.",
    "No executor ownership.",
    "No recovery enablement.",
    "No runtime mutation.",
)

FORBIDDEN_AUTHORITY = (
    "Starting runtime forbidden.",
    "Dispatching tasks forbidden.",
    "Scheduler control forbidden.",
    "Executor control forbidden.",
    "Recovery activation forbidden.",
    "Configuration mutation forbidden.",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _environment_package_text() -> str:
    text = _text(PACKAGE_SEQUENCE)
    marker = "## Package 561"
    assert marker in text
    return text[text.index(marker) :]


def test_packages_561_to_568_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("561", "562", "563", "564", "565", "566", "567", "568"):
        assert f"## Package {package_number}" in text

    assert "Runtime Environment Resolver Boundary" in text
    assert "Documentation/test only." in text


def test_environment_resolver_docs_exist():
    assert ENV_BOUNDARY.exists()
    assert ENV_GAP_INVENTORY.exists()
    assert ENV_READINESS_REVIEW.exists()


def test_inherited_seals_are_documented():
    for path in (ENV_BOUNDARY, ENV_READINESS_REVIEW):
        text = _text(path)
        for seal in INHERITED_SEALS:
            assert seal in text


def test_inspection_only_and_no_execution_authority():
    for path in (ENV_BOUNDARY, ENV_GAP_INVENTORY, ENV_READINESS_REVIEW):
        text = _text(path)
        assert "Environment resolver may inspect only." in text
        assert "No execution authority." in text or "Runtime prerequisite checking has no execution authority." in text
        assert "Runtime execution forbidden." in text or "runtime execution is introduced" in text


def test_no_scheduler_or_executor_ownership():
    for path in (ENV_BOUNDARY, ENV_GAP_INVENTORY, ENV_READINESS_REVIEW):
        text = _text(path)
        assert "No scheduler ownership." in text or "Runtime prerequisite checking has no scheduler ownership." in text
        assert "No executor ownership." in text or "Runtime prerequisite checking has no executor ownership." in text
        assert "Scheduler remains owner of scheduling." in text or path == ENV_GAP_INVENTORY
        assert "Executor remains owner of execution." in text or path == ENV_GAP_INVENTORY


def test_no_recovery_enablement():
    for path in (ENV_BOUNDARY, ENV_GAP_INVENTORY, ENV_READINESS_REVIEW):
        text = _text(path)
        assert "No recovery enablement." in text or "Runtime prerequisite checking has no recovery enablement." in text
        assert "Recovery remains disabled." in text or path == ENV_GAP_INVENTORY


def test_no_runtime_mutation_or_configuration_mutation():
    for path in (ENV_BOUNDARY, ENV_GAP_INVENTORY, ENV_READINESS_REVIEW):
        text = _text(path)
        assert "No runtime mutation." in text or "Runtime prerequisite checking has no runtime mutation." in text
        assert "Configuration mutation forbidden." in text


def test_forbidden_environment_resolver_authority_is_documented():
    text = _text(ENV_BOUNDARY)
    for phrase in FORBIDDEN_AUTHORITY:
        assert phrase in text


def test_environment_gap_inventory_records_remaining_gaps_without_implementation():
    text = _text(ENV_GAP_INVENTORY)
    assert "These gaps are not implemented by this package." in text
    for gap in ENVIRONMENT_GAPS:
        assert gap in text
    assert text.count("Do not implement here") == len(ENVIRONMENT_GAPS)


def test_readiness_review_has_go_no_go_and_required_guarantees():
    text = _text(ENV_READINESS_REVIEW)
    assert "GO / NO-GO" in text
    assert "GO criteria:" in text
    assert "NO-GO criteria:" in text
    assert "Required Guarantees" in text
    for guarantee in BOUNDARY_GUARANTEES:
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
    text = _environment_package_text()
    assert "do not modify core/runtime" in text
    assert "do not modify scheduler" in text
    assert "do not modify executor" in text
    assert "do not add startup scripts" in text
    assert "do not add deployment scripts" in text
    assert "do not create runtime services" in text
    assert "do not execute runtime" in text
    assert "do not activate recovery" in text
    assert "do not mutate runtime state" in text
    assert "py -m pytest tests/test_runtime_environment_resolver_boundary.py -q" in text
    assert "do not run full suite, nightly, regression, or long validation" in text
