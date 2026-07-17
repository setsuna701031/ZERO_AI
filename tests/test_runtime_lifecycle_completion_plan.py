from pathlib import Path


PLAN = Path("docs/runtime_lifecycle_completion_plan.md")
GAP_INVENTORY = Path("docs/runtime_lifecycle_gap_inventory.md")
BOUNDARY_SEAL = Path("docs/runtime_lifecycle_completion_boundary_seal.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

LIFECYCLE_AREAS = (
    "intake",
    "planning",
    "dispatch",
    "execution",
    "observation",
    "recovery disabled boundary",
    "completion",
    "audit",
    "operator handoff",
)

REQUIRED_FIELDS = (
    "Current Status",
    "Owner",
    "Gap If Any",
    "Allowed Next Action",
    "Forbidden Ownership Violation",
)

DISABLED_GUARANTEES = (
    "Recovery activation remains disabled.",
    "No scheduler behavior change.",
    "No executor behavior change.",
    "No runtime mutation added.",
    "No autonomous execution change.",
)

FORBIDDEN_CHANGES = (
    "does not add core runtime files",
    "does not edit scheduler behavior",
    "does not edit executor behavior",
    "does not edit activation behavior",
    "does not change wiring",
    "does not change behavior",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_packages_481_to_488_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("481", "482", "483", "484", "485", "486", "487", "488"):
        assert f"## Package {package_number}" in text

    assert "Runtime Lifecycle Completion Plan" in text
    assert "Documentation/test only." in text


def test_lifecycle_docs_exist():
    assert PLAN.exists()
    assert GAP_INVENTORY.exists()
    assert BOUNDARY_SEAL.exists()


def test_all_required_lifecycle_areas_are_listed():
    for path in (PLAN, GAP_INVENTORY, BOUNDARY_SEAL):
        text = _text(path)
        for area in LIFECYCLE_AREAS:
            assert area in text


def test_lifecycle_plan_and_gap_inventory_include_required_fields():
    for path in (PLAN, GAP_INVENTORY):
        text = _text(path)
        for field in REQUIRED_FIELDS:
            assert field in text


def test_disabled_guarantees_remain_documented():
    for path in (PLAN, GAP_INVENTORY, BOUNDARY_SEAL):
        text = _text(path)
        for guarantee in DISABLED_GUARANTEES:
            assert guarantee in text


def test_boundary_seal_forbids_runtime_changes():
    text = _text(BOUNDARY_SEAL)
    for forbidden in FORBIDDEN_CHANGES:
        assert forbidden in text


def test_package_sequence_records_forbidden_scope():
    text = _text(PACKAGE_SEQUENCE)
    assert "no new core/runtime files" in text
    assert "no scheduler edits" in text
    assert "no executor edits" in text
    assert "no activation edits" in text
    assert "no wiring changes" in text
    assert "no behavior changes" in text
