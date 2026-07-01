from pathlib import Path


REVIEW = Path("docs/aer_runtime_resume_execution_closure_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_closure_review_document_exists():
    assert REVIEW.exists()


def test_reviewed_package_set_is_complete():
    text = _text(REVIEW)
    for package in (
        "Package 130",
        "Package 131",
        "Package 132",
        "Package 133",
        "Package 134",
    ):
        assert package in text
    for surface in (
        "Runtime Resume Execution Blueprint",
        "Runtime Resume Execution Contract",
        "Runtime Resume Execution Validation",
        "Runtime Resume Execution Builder",
        "Runtime Resume Execution Consumer Boundary",
    ):
        assert surface in text


def test_go_decision_closes_domain_without_implementation():
    text = _text(REVIEW)
    assert "Final decision: GO" in text
    assert (
        "Runtime Resume Execution domain is closed for architecture + contract + validation + builder + consumer-boundary responsibilities"
        in text
    )
    assert "Runtime Resume Execution behavior remains future-domain implementation work" in text
    assert "does not add runtime behavior" in text
    assert "does not implement resume execution" in text


def test_closure_scope_forbids_runtime_and_downstream_behavior():
    text = _text(REVIEW)
    for forbidden in (
        "implement runtime resume execution",
        "add `core/runtime/aer_runtime_resume_execution.py`",
        "execute a Resume Plan",
        "execute an execution request",
        "authorize execution",
        "authorize downstream handoff",
        "recover",
        "schedule",
        "dispatch",
        "call operator",
        "persist",
        "audit",
        "journal",
        "replay",
        "mutate runtime state",
        "allocate runtime identity",
    ):
        assert forbidden in text


def test_public_surface_review_keeps_surfaces_separate():
    text = _text(REVIEW)
    assert "## Public Surface Review" in text
    assert "The surfaces must remain separate" in text
    assert "must never collapse into one public API" in text
    for row in (
        "| Execution Blueprint | Package 130 |",
        "| Execution Contract | Package 131 |",
        "| Execution Validation | Package 132 |",
        "| Execution Builder | Package 133 |",
        "| Execution Consumer Boundary | Package 134 |",
    ):
        assert row in text


def test_ownership_matrix_assigns_future_downstream_owners():
    text = _text(REVIEW)
    assert "## Ownership Matrix" in text
    for owner in (
        "Future Runtime Resume Execution implementation",
        "Future Recovery domain",
        "Future Scheduler domain",
        "Future Dispatcher domain",
        "Future Operator domain",
        "Future Persistence domain",
        "Future Audit domain",
        "Future Journal domain",
    ):
        assert owner in text


def test_boundary_matrix_blocks_direct_downstream_consumption():
    text = _text(REVIEW)
    assert "## Boundary Matrix" in text
    for boundary in (
        "Execution Consumer Boundary -> Future Runtime Resume Execution",
        "Execution Consumer Boundary -> Recovery",
        "Execution Consumer Boundary -> Scheduler",
        "Execution Consumer Boundary -> Dispatcher",
        "Execution Consumer Boundary -> Operator",
        "Execution Consumer Boundary -> Persistence / Audit / Journal",
    ):
        assert boundary in text
    for phrase in (
        "Package 135 must not authorize execution or downstream handoff",
        "Recovery must not consume execution consumer output without future Recovery contract",
        "Scheduler must not consume execution consumer output directly",
        "Dispatcher must not execute consumer output directly",
        "Operator must not treat consumer output as an operator decision",
    ):
        assert phrase in text


def test_closure_checklist_all_passes():
    text = _text(REVIEW)
    assert "## Closure Checklist" in text
    for check in (
        "Blueprint exists before contract.",
        "Contract exists before validation.",
        "Validation exists before builder.",
        "Builder exists before consumer boundary.",
        "Consumer boundary exists before closure.",
        "Execution behavior remains absent.",
        "Downstream domains remain future-owned.",
        "Runtime mutation is forbidden.",
    ):
        assert f"| {check} | PASS |" in text


def test_closure_invariants_are_sealed():
    text = _text(REVIEW)
    assert "## Closure Invariants" in text
    for invariant in (
        "not allowed to hide execution behavior inside validation, builders, consumers, summaries, metadata, or closure review",
        "payloads are not runtime permission tokens",
        "Execution Consumer Boundary output is not a Recovery trigger",
        "Runtime Resume Execution behavior remains future-domain behavior",
        "Missing runtime execution is intentional",
    ):
        assert invariant in text


def test_failure_ownership_review_keeps_single_owners():
    text = _text(REVIEW)
    assert "## Failure Ownership Review" in text
    for row in (
        "| Invalid execution request | Runtime Resume Execution Validation |",
        "| Invalid execution result | Runtime Resume Execution Validation |",
        "| Invalid execution failure | Runtime Resume Execution Validation |",
        "| Invalid execution summary | Runtime Resume Execution Consumer Boundary |",
        "| Recovery required | Future Recovery domain |",
        "| Scheduler admission | Future Scheduler domain |",
        "| Dispatcher execution | Future Dispatcher domain |",
        "| Operator decision | Future Operator domain |",
    ):
        assert row in text


def test_dependency_graph_allows_only_forward_blueprint_handoff():
    text = _text(REVIEW)
    assert "## Dependency Graph" in text
    assert "Runtime Resume Execution Integration Blueprint" in text
    assert "Future Recovery Blueprint" in text
    for forbidden in (
        "-/-> Scheduler",
        "-/-> TaskRunner",
        "-/-> Recovery",
        "-/-> Dispatcher",
        "-/-> Operator",
        "-/-> Persistence",
        "-/-> Audit",
        "-/-> Journal",
        "-/-> Replay",
        "-/-> Runtime loop",
        "-/-> Snapshot Builder",
        "-/-> Snapshot Validator internals",
    ):
        assert forbidden in text


def test_go_and_no_go_criteria_are_explicit():
    text = _text(REVIEW)
    assert "## GO Criteria" in text
    assert "## NO-GO Criteria" in text
    for phrase in (
        "execution behavior is implemented or hidden in this closure package",
        "downstream handoff is authorized without a future downstream contract",
        "closure decision lacks explicit GO / NO-GO language",
    ):
        assert phrase in text


def test_next_package_is_integration_blueprint():
    text = _text(REVIEW)
    assert "Ready for Package 136: Runtime Resume Execution Integration Blueprint" in text
    assert "Package 136 must remain blueprint-only" in text
    assert "must not implement runtime execution or recovery behavior" in text


def test_package_sequence_contains_package_135_entry():
    text = _text(PACKAGE_SEQUENCE)
    assert "## Package 135" in text
    assert "Package 135: Runtime Resume Execution Closure Review" in text
    assert "Final decision: GO" in text
    assert "Ready for Package 136: Runtime Resume Execution Integration Blueprint" in text
