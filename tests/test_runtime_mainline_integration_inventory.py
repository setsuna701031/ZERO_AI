from pathlib import Path


INVENTORY = Path("docs/runtime_mainline_integration_inventory.md")
SURFACE_MAP = Path("docs/runtime_mainline_surface_map.md")
NEXT_PHASE_PLAN = Path("docs/runtime_mainline_next_phase_plan.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

REQUIRED_SURFACES = (
    "dispatcher",
    "executor",
    "scheduler",
    "supervisor",
    "operator",
    "session",
    "recovery (closed/disabled)",
    "lifecycle",
    "observability",
)

REQUIRED_COLUMNS = (
    "Owner",
    "Current Status",
    "Integration State",
    "Allowed Next Actions",
    "Forbidden Ownership Violations",
)

FORBIDDEN_CHANGES = (
    "No runtime behavior changes.",
    "No new runtime modules.",
    "No scheduler edits.",
    "No executor edits.",
    "No activation changes.",
    "No wiring changes.",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_packages_473_to_480_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("473", "474", "475", "476", "477", "478", "479", "480"):
        assert f"## Package {package_number}" in text

    assert "Runtime Integration Inventory Refresh" in text
    assert "Analysis/report only." in text


def test_inventory_docs_exist():
    assert INVENTORY.exists()
    assert SURFACE_MAP.exists()
    assert NEXT_PHASE_PLAN.exists()


def test_inventory_lists_all_required_surfaces_and_columns():
    text = _text(INVENTORY)

    for surface in REQUIRED_SURFACES:
        assert surface in text
    for column in REQUIRED_COLUMNS:
        assert column in text


def test_recovery_is_marked_closed_disabled():
    inventory = _text(INVENTORY)
    surface_map = _text(SURFACE_MAP)
    plan = _text(NEXT_PHASE_PLAN)

    assert "recovery (closed/disabled)" in inventory
    assert "Closed/disabled" in inventory
    assert "Recovery is closed/disabled." in inventory
    assert "Recovery remains closed/disabled until a separate explicit GO package." in surface_map
    assert "Recovery remains closed/disabled." in plan


def test_ownership_boundaries_are_documented():
    inventory = _text(INVENTORY)
    surface_map = _text(SURFACE_MAP)

    assert "Forbidden Ownership Violations" in inventory
    assert "Ownership Boundary Rules" in surface_map
    assert "Dispatcher must not own scheduler behavior." in surface_map
    assert "Executor must not own activation authorization." in surface_map
    assert "Scheduler must not own executor execution." in surface_map


def test_next_phase_plan_exists_and_lists_allowed_areas():
    text = _text(NEXT_PHASE_PLAN)

    for area in (
        "runtime integration cleanup",
        "runtime lifecycle completion",
        "runtime observability",
        "runtime operator interface",
        "runtime deployment readiness",
    ):
        assert area in text


def test_forbidden_runtime_changes_are_documented():
    plan = _text(NEXT_PHASE_PLAN)
    for forbidden in FORBIDDEN_CHANGES:
        assert forbidden in plan
