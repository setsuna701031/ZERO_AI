from pathlib import Path


PLAN = Path("docs/runtime_observability_completion_plan.md")
GAP_INVENTORY = Path("docs/runtime_observability_gap_inventory.md")
BOUNDARY_SEAL = Path("docs/runtime_observability_boundary_seal.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

SURFACES = (
    "runtime status",
    "execution evidence",
    "audit trail",
    "lifecycle events",
    "operator visibility",
    "failure reporting",
    "recovery disabled state reporting",
)

FIELDS = (
    "Current Owner",
    "Current State",
    "Existing Integration",
    "Missing Visibility Gap",
    "Allowed Future Action",
)

READ_ONLY_GUARANTEES = (
    "No execution control.",
    "No scheduler control.",
    "No executor control.",
    "No mutation authority.",
    "No recovery activation.",
)

MAY_ACTIONS = (
    "read state",
    "summarize state",
    "expose status",
    "report issues",
)

MUST_NOT_ACTIONS = (
    "change state",
    "retry execution",
    "dispatch tasks",
    "trigger recovery",
    "modify runtime flow",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_packages_489_to_496_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("489", "490", "491", "492", "493", "494", "495", "496"):
        assert f"## Package {package_number}" in text

    assert "Runtime Observability Completion Plan" in text
    assert "Documentation/test only." in text


def test_observability_docs_exist():
    assert PLAN.exists()
    assert GAP_INVENTORY.exists()
    assert BOUNDARY_SEAL.exists()


def test_required_surfaces_are_documented():
    for path in (PLAN, GAP_INVENTORY):
        text = _text(path)
        for surface in SURFACES:
            assert surface in text
        for field in FIELDS:
            assert field in text


def test_read_only_guarantees_exist():
    for path in (PLAN, GAP_INVENTORY, BOUNDARY_SEAL):
        text = _text(path)
        for guarantee in READ_ONLY_GUARANTEES:
            assert guarantee in text


def test_observability_may_and_must_not_rules_exist():
    plan = _text(PLAN)
    seal = _text(BOUNDARY_SEAL)

    for action in MAY_ACTIONS:
        assert action in plan
        assert action in seal
    for action in MUST_NOT_ACTIONS:
        assert action in plan
        assert action in seal


def test_boundary_seal_forbids_runtime_changes():
    text = _text(BOUNDARY_SEAL)
    assert "No new core/runtime files." in text
    assert "No scheduler edits." in text
    assert "No executor edits." in text
    assert "No activation edits." in text
    assert "No wiring changes." in text
    assert "No behavior changes." in text


def test_package_sequence_records_forbidden_scope():
    text = _text(PACKAGE_SEQUENCE)
    assert "no new core/runtime files" in text
    assert "no scheduler edits" in text
    assert "no executor edits" in text
    assert "no activation edits" in text
    assert "no wiring changes" in text
    assert "no behavior changes" in text
