from pathlib import Path


BLUEPRINT = Path("docs/aer_runtime_recovery_integration_blueprint.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_144_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 144")
    end = text.find("## Package 145", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_integration_blueprint_file_exists():
    assert BLUEPRINT.exists()


def test_required_sections_exist():
    text = _text(BLUEPRINT)
    for section in (
        "## Purpose",
        "## Integration Objective",
        "## Existing Recovery Governance Chain",
        "## Integration Boundary",
        "## Non-Goals",
        "## Runtime Touchpoint Inventory",
        "## Allowed Future Consumers",
        "## Forbidden Direct Integrations",
        "## Responsibility Matrix",
        "## Dependency Graph",
        "## Data Flow Overview",
        "## Execution Authority Placeholder",
        "## Implementation Package Roadmap",
        "## GO / NO-GO Decision",
        "## Next Package Recommendation",
    ):
        assert section in text


def test_go_no_go_exists():
    text = _text(BLUEPRINT)
    assert "Final decision: GO" in text
    assert "GO / NO-GO" in text
    assert "Runtime Recovery remains descriptive only" in text


def test_execution_authority_placeholder_exists():
    text = _text(BLUEPRINT)
    assert "## Execution Authority Placeholder" in text
    assert "Execution authority is intentionally absent" in text
    assert "separate Execution Authority package must exist" in text
    assert "MUST NOT allow direct scheduler/dispatcher/operator execution" in text


def test_forbidden_direct_integrations_are_documented():
    text = _text(BLUEPRINT)
    for forbidden in (
        "Scheduler execution or admission",
        "Dispatcher execution or command paths",
        "Operator action paths",
        "TaskRunner execution",
        "runtime execution loops",
        "persistence write paths",
        "audit emitters",
        "journal emitters",
        "replay execution paths",
        "subprocess execution",
        "file IO paths",
        "runtime mutation modules",
    ):
        assert forbidden in text


def test_dependency_graph_exists():
    text = _text(BLUEPRINT)
    assert "## Dependency Graph" in text
    assert "Package 137 Domain Lifecycle Standard" in text
    assert "Package 144 Runtime Recovery Integration Blueprint" in text
    assert "Package 145 Execution Authority placeholder package" in text
    assert "core.runtime.aer_runtime_recovery_validation" in text
    assert "core.runtime.aer_runtime_recovery_planner" in text
    assert "core.runtime.aer_runtime_recovery_consumer_boundary" in text


def test_package_roadmap_exists():
    text = _text(BLUEPRINT)
    assert "## Implementation Package Roadmap" in text
    assert "Package 145" in text
    assert "Execution Authority package for Recovery integration" in text
    assert "Package 146" in text
    assert "Package 150" in text


def test_package_144_sequence_entry_exists():
    entry = _package_144_entry()
    assert "## Package 144" in entry
    assert "Package 144: Runtime Recovery Integration Blueprint" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 145" in entry
    assert "MUST NOT allow direct scheduler/dispatcher/operator execution" in entry
