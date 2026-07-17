from pathlib import Path


PLAN = Path("docs/runtime_deployment_readiness_plan.md")
GAP_INVENTORY = Path("docs/runtime_deployment_gap_inventory.md")
BOUNDARY_SEAL = Path("docs/runtime_deployment_boundary_seal.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

SURFACES = (
    "runtime startup",
    "configuration",
    "environment requirements",
    "dependency validation",
    "health reporting",
    "operator access",
    "observability access",
    "failure visibility",
    "safe shutdown",
)

FIELDS = (
    "Current State",
    "Owner",
    "Readiness Gap",
    "Allowed Future Action",
    "Forbidden Ownership Violation",
)

MAY_DEFINE = (
    "checks",
    "requirements",
    "documentation",
    "future validation points",
)

MUST_NOT = (
    "start runtime",
    "execute tasks",
    "mutate state",
    "bypass scheduler",
    "bypass executor",
    "enable recovery activation",
)

PRESERVED_AUTHORITY = (
    "Recovery activation disabled.",
    "Scheduler authority unchanged.",
    "Executor authority unchanged.",
    "Operator boundaries unchanged.",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_packages_505_to_512_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("505", "506", "507", "508", "509", "510", "511", "512"):
        assert f"## Package {package_number}" in text

    assert "Runtime Deployment Readiness Plan" in text
    assert "Documentation/test only." in text


def test_deployment_docs_exist():
    assert PLAN.exists()
    assert GAP_INVENTORY.exists()
    assert BOUNDARY_SEAL.exists()


def test_required_deployment_surfaces_are_documented():
    for path in (PLAN, GAP_INVENTORY):
        text = _text(path)
        for surface in SURFACES:
            assert surface in text
        for field in FIELDS:
            assert field in text


def test_no_execution_authority_is_added():
    for path in (PLAN, BOUNDARY_SEAL):
        text = _text(path)
        for phrase in MAY_DEFINE:
            assert phrase in text
        for phrase in MUST_NOT:
            assert phrase in text


def test_preserved_authority_is_documented():
    for path in (PLAN, GAP_INVENTORY, BOUNDARY_SEAL):
        text = _text(path)
        for phrase in PRESERVED_AUTHORITY:
            assert phrase in text


def test_boundary_seal_forbids_runtime_changes():
    text = _text(BOUNDARY_SEAL)
    assert "No new runtime modules." in text
    assert "No deployment scripts." in text
    assert "No service files." in text
    assert "No scheduler edits." in text
    assert "No executor edits." in text
    assert "No activation edits." in text
    assert "No behavior changes." in text


def test_package_sequence_records_forbidden_scope():
    text = _text(PACKAGE_SEQUENCE)
    assert "no new runtime modules" in text
    assert "no deployment scripts" in text
    assert "no service files" in text
    assert "no scheduler edits" in text
    assert "no executor edits" in text
    assert "no activation edits" in text
    assert "no behavior changes" in text
