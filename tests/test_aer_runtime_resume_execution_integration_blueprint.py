from pathlib import Path


BLUEPRINT = Path("docs/aer_runtime_resume_execution_integration_blueprint.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_integration_blueprint_document_exists():
    assert BLUEPRINT.exists()


def test_blueprint_is_package_136_and_blueprint_only():
    text = _text(BLUEPRINT)
    assert "Package 136" in text
    assert "Runtime Resume Execution Integration Blueprint" in text
    assert "blueprint-only" in text
    assert "does not add runtime behavior" in text
    assert "does not implement resume execution" in text
    assert "does not implement Recovery" in text


def test_reviewed_upstream_packages_are_complete():
    text = _text(BLUEPRINT)
    for package in (
        "Package 130",
        "Package 131",
        "Package 132",
        "Package 133",
        "Package 134",
        "Package 135",
    ):
        assert package in text
    for surface in (
        "Runtime Resume Execution Blueprint",
        "Runtime Resume Execution Contract",
        "Runtime Resume Execution Validation",
        "Runtime Resume Execution Builder",
        "Runtime Resume Execution Consumer Boundary",
        "Runtime Resume Execution Closure Review",
    ):
        assert surface in text


def test_domain_closure_position_points_to_recovery_blueprint():
    text = _text(BLUEPRINT)
    assert "## Domain Closure Position" in text
    assert "Runtime Resume Execution is closed for architecture, contract, validation, builder, consumer-boundary, and closure review responsibilities" in text
    assert "Runtime Resume Execution behavior is not implemented" in text
    assert "Future Runtime Recovery Blueprint" in text
    assert "No package may skip this boundary" in text


def test_integration_sequence_is_fixed_and_no_skips_allowed():
    text = _text(BLUEPRINT)
    assert "## Integration Sequence" in text
    for step in (
        "Snapshot Consumer",
        "Resume Eligibility",
        "Resume Planning",
        "Resume Consumer Boundary",
        "Runtime Resume Execution Blueprint",
        "Runtime Resume Execution Contract",
        "Runtime Resume Execution Validation",
        "Runtime Resume Execution Builder",
        "Runtime Resume Execution Consumer Boundary",
        "Runtime Resume Execution Closure Review",
        "Runtime Resume Execution Integration Blueprint",
        "Runtime Recovery Blueprint",
    ):
        assert step in text
    for forbidden_skip in (
        "must not skip directly from Runtime Resume Execution Builder to Recovery",
        "must not skip directly from Runtime Resume Execution Consumer Boundary to Scheduler",
        "must not skip directly from Runtime Resume Execution Consumer Boundary to Dispatcher",
        "must not skip directly from Runtime Resume Execution Consumer Boundary to Operator",
    ):
        assert forbidden_skip in text


def test_handoff_matrix_blocks_direct_downstream_consumption():
    text = _text(BLUEPRINT)
    assert "## Handoff Matrix" in text
    for row in (
        "| Execution Consumer Boundary | Runtime Resume Execution Integration Blueprint | Yes |",
        "| Execution Consumer Boundary | Future Runtime Recovery Blueprint | Future only |",
        "| Execution Consumer Boundary | Scheduler | No |",
        "| Execution Consumer Boundary | Dispatcher | No |",
        "| Execution Consumer Boundary | Operator | No |",
        "| Execution Consumer Boundary | Persistence | No |",
        "| Execution Consumer Boundary | Audit | No |",
        "| Execution Consumer Boundary | Journal | No |",
        "| Execution Consumer Boundary | Replay | No |",
        "| Execution Consumer Boundary | TaskRunner | No |",
        "| Execution Consumer Boundary | Runtime loop | No |",
    ):
        assert row in text


def test_recovery_handoff_boundary_keeps_recovery_future_owned():
    text = _text(BLUEPRINT)
    assert "## Recovery Handoff Boundary" in text
    for phrase in (
        "Recovery is the next domain owner",
        "Package 136 does not implement Recovery",
        "Recovery must consume only a future public handoff explicitly authorized by its own contract",
        "Recovery must not treat Execution Consumer Boundary output as a recovery trigger",
        "Recovery must own recovery classification, recovery planning, recovery failure handling, and recovery lifecycle rules",
    ):
        assert phrase in text


def test_scheduler_dispatcher_operator_boundaries_are_future_owned():
    text = _text(BLUEPRINT)
    for heading in (
        "## Scheduler Boundary",
        "## Dispatcher Boundary",
        "## Operator Boundary",
    ):
        assert heading in text
    for phrase in (
        "Scheduler remains future-owned",
        "Scheduler must not consume execution consumer output directly",
        "Dispatcher remains future-owned",
        "Dispatcher must not dispatch execution consumer output directly",
        "Operator remains future-owned",
        "Operator must not treat execution consumer output as an operator decision",
    ):
        assert phrase in text


def test_persistence_audit_journal_replay_remain_future_owned():
    text = _text(BLUEPRINT)
    assert "## Persistence / Audit / Journal / Replay Boundary" in text
    for phrase in (
        "Persistence, Audit, Journal, and Replay remain future-owned",
        "Package 136 must not persist, audit, journal, replay, emit events, read event streams, write records, or create storage handles",
        "Future Persistence, Audit, Journal, and Replay domains must each define their own contracts",
    ):
        assert phrase in text


def test_failure_ownership_handoff_assigns_future_owners():
    text = _text(BLUEPRINT)
    assert "## Failure Ownership Handoff" in text
    for row in (
        "| Invalid execution request | None | Runtime Resume Execution Validation |",
        "| Invalid execution result | None | Runtime Resume Execution Validation |",
        "| Invalid execution failure | None | Runtime Resume Execution Validation |",
        "| Invalid execution summary | None | Runtime Resume Execution Consumer Boundary |",
        "| Recovery required | None | Future Runtime Recovery domain |",
        "| Scheduler admission needed | None | Future Scheduler domain |",
        "| Dispatcher command needed | None | Future Dispatcher domain |",
        "| Operator approval needed | None | Future Operator / Approval domains |",
        "| Persistence record needed | None | Future Persistence domain |",
        "| Audit record needed | None | Future Audit domain |",
        "| Journal event needed | None | Future Journal domain |",
        "| Replay token needed | None | Future Replay domain |",
    ):
        assert row in text
    assert "Package 136 owns no runtime failure handling" in text


def test_dependency_graph_forbids_downstream_runtime_dependencies():
    text = _text(BLUEPRINT)
    assert "## Dependency Graph" in text
    assert "Package 135 Closure Review" in text
    assert "Package 137 Runtime Recovery Blueprint" in text
    for forbidden in (
        "Package 136 -/-> Scheduler",
        "Package 136 -/-> TaskRunner",
        "Package 136 -/-> Recovery implementation",
        "Package 136 -/-> Dispatcher",
        "Package 136 -/-> Operator",
        "Package 136 -/-> Persistence",
        "Package 136 -/-> Audit",
        "Package 136 -/-> Journal",
        "Package 136 -/-> Replay",
        "Package 136 -/-> Runtime loop",
        "Package 136 -/-> Snapshot Builder",
        "Package 136 -/-> Snapshot Validator internals",
        "Package 136 -/-> Execution Builder internals",
        "Package 136 -/-> Execution Consumer helper internals",
    ):
        assert forbidden in text


def test_forbidden_actions_are_sealed():
    text = _text(BLUEPRINT)
    assert "## Forbidden Actions" in text
    for forbidden in (
        "implement runtime resume execution",
        "implement recovery",
        "implement scheduler admission",
        "implement dispatcher commands",
        "implement operator decisions",
        "add `core/runtime/aer_runtime_resume_execution.py`",
        "add `core/runtime/aer_runtime_recovery.py`",
        "execute a Resume Plan",
        "authorize downstream handoff",
        "mutate runtime state",
        "allocate runtime identity",
        "modify PATH, venv, pip, or bundled runtime",
    ):
        assert forbidden in text


def test_future_package_roadmap_starts_recovery_blueprint_only():
    text = _text(BLUEPRINT)
    assert "## Future Package Roadmap" in text
    assert "Package 137 must be Runtime Recovery Blueprint" in text
    assert "Package 137 must remain blueprint-only" in text
    assert "Package 137 must not implement recovery behavior" in text
    assert "Package 137 must not call Scheduler, Dispatcher, Operator, Persistence, Audit, Journal, Replay, TaskRunner, or runtime loops" in text


def test_go_no_go_criteria_and_decision_are_explicit():
    text = _text(BLUEPRINT)
    assert "## GO Criteria" in text
    assert "## NO-GO Criteria" in text
    assert "Final decision: GO" in text
    for phrase in (
        "Runtime Resume Execution domain remains closed",
        "Recovery is identified as the next domain owner",
        "Package 136 authorizes no execution and no downstream handoff",
        "it skips Recovery Blueprint and proceeds directly to Recovery implementation",
    ):
        assert phrase in text


def test_next_package_is_recovery_blueprint():
    text = _text(BLUEPRINT)
    assert "Ready for Package 137: Runtime Recovery Blueprint" in text
    assert "Package 137 must remain blueprint-only and must not implement recovery behavior" in text


def test_package_sequence_contains_package_136_entry():
    text = _text(PACKAGE_SEQUENCE)
    assert "## Package 136" in text
    assert "Package 136: Runtime Resume Execution Integration Blueprint" in text
    assert "Final decision: GO" in text
    assert "Ready for Package 137: Runtime Recovery Blueprint" in text
    assert "Package 137 must remain blueprint-only" in text
