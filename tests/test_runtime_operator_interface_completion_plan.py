from pathlib import Path


PLAN = Path("docs/runtime_operator_interface_completion_plan.md")
GAP_INVENTORY = Path("docs/runtime_operator_interface_gap_inventory.md")
BOUNDARY_SEAL = Path("docs/runtime_operator_interface_boundary_seal.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

SURFACES = (
    "runtime status visibility",
    "execution result visibility",
    "lifecycle state visibility",
    "audit/evidence visibility",
    "operator handoff",
    "operator decision boundary",
    "user confirmation boundary",
    "failure reporting",
)

FIELDS = (
    "Current Owner",
    "Current Status",
    "Integration State",
    "Missing Gap",
    "Allowed Next Action",
    "Forbidden Ownership Violation",
)

MAY_RULES = (
    "observe runtime state",
    "receive summaries",
    "review evidence",
    "make explicit decisions through approved boundaries",
)

MUST_NOT_RULES = (
    "directly mutate runtime state",
    "bypass scheduler ownership",
    "bypass executor ownership",
    "trigger recovery activation",
    "silently approve actions",
)

DISABLED_GUARANTEES = (
    "Recovery activation disabled.",
    "Executor authority unchanged.",
    "Scheduler authority unchanged.",
    "Mutation authority unchanged.",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_packages_497_to_504_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("497", "498", "499", "500", "501", "502", "503", "504"):
        assert f"## Package {package_number}" in text

    assert "Runtime Operator Interface Completion Plan" in text
    assert "Documentation/test only." in text


def test_operator_interface_docs_exist():
    assert PLAN.exists()
    assert GAP_INVENTORY.exists()
    assert BOUNDARY_SEAL.exists()


def test_required_operator_surfaces_are_documented():
    for path in (PLAN, GAP_INVENTORY):
        text = _text(path)
        for surface in SURFACES:
            assert surface in text
        for field in FIELDS:
            assert field in text


def test_authority_separation_is_documented():
    for path in (PLAN, BOUNDARY_SEAL):
        text = _text(path)
        for rule in MAY_RULES:
            assert rule in text
        for rule in MUST_NOT_RULES:
            assert rule in text


def test_disabled_guarantees_remain_documented():
    for path in (PLAN, GAP_INVENTORY, BOUNDARY_SEAL):
        text = _text(path)
        for guarantee in DISABLED_GUARANTEES:
            assert guarantee in text


def test_boundary_seal_forbids_runtime_changes():
    text = _text(BOUNDARY_SEAL)
    assert "No new core/runtime files." in text
    assert "No operator code edits." in text
    assert "No scheduler edits." in text
    assert "No executor edits." in text
    assert "No activation edits." in text
    assert "No wiring changes." in text
    assert "No behavior changes." in text


def test_package_sequence_records_forbidden_scope():
    text = _text(PACKAGE_SEQUENCE)
    assert "no new core/runtime files" in text
    assert "no operator code edits" in text
    assert "no scheduler edits" in text
    assert "no executor edits" in text
    assert "no activation edits" in text
    assert "no wiring changes" in text
    assert "no behavior changes" in text
