from pathlib import Path


BLUEPRINT = Path("docs/aer_runtime_recovery_blueprint.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
RECOVERY_IMPLEMENTATION = Path("core/runtime/aer_runtime_recovery.py")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_138_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 138")
    end = text.find("## Package 139", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_blueprint_document_exists():
    assert BLUEPRINT.exists()


def test_blueprint_title_and_purpose_are_present():
    text = _text(BLUEPRINT)
    assert text.startswith("# AER Runtime Recovery Blueprint")
    assert "## Purpose" in text
    assert "Package 138 starts the Runtime Recovery Domain" in text
    assert "Blueprint only" in text


def test_blueprint_references_domain_lifecycle_standard():
    text = _text(BLUEPRINT)
    assert "AER Domain Lifecycle Standard" in text
    assert "Runtime Recovery Domain has started under the AER Domain Lifecycle Standard" in text


def test_recovery_ownership_and_non_ownership_sections_are_present():
    text = _text(BLUEPRINT)
    assert "## Recovery Domain Ownership" in text
    for owned in (
        "recovery eligibility",
        "recovery planning",
        "recovery failure classification",
        "recovery handoff preparation",
        "recovery boundary with Resume Execution",
    ):
        assert owned in text
    assert "## Recovery Non-Ownership" in text
    for not_owned in (
        "scheduler execution",
        "dispatcher calls",
        "operator decisions",
        "persistence writes",
        "audit emission",
        "journal/replay behavior",
        "direct runtime mutation",
    ):
        assert not_owned in text


def test_recovery_ownership_matrix_assigns_single_owner_per_capability():
    text = _text(BLUEPRINT)
    assert "## Recovery Ownership Matrix" in text
    assert "| Capability | Owner |" in text
    for row in (
        "| Recovery Eligibility | Runtime Recovery |",
        "| Recovery Planning | Runtime Recovery |",
        "| Recovery Failure Classification | Runtime Recovery |",
        "| Recovery Handoff Preparation | Runtime Recovery |",
        "| Recovery Boundary With Resume Execution | Runtime Recovery |",
        "| Recovery Execution | Future Runtime Recovery |",
        "| Scheduler Decision | Scheduler |",
        "| Dispatcher Decision | Dispatcher |",
        "| Operator Approval | Operator |",
        "| Persistence Commit | Persistence |",
        "| Audit Record | Audit |",
        "| Journal Record | Journal |",
        "| Replay Interpretation | Replay |",
    ):
        assert row in text
    assert "Every capability has exactly one owner" in text
    assert "both sides must not claim decision authority for the same capability" in text


def test_upstream_and_downstream_boundaries_are_present():
    text = _text(BLUEPRINT)
    assert "## Upstream Boundary" in text
    assert "Recovery may consume only public Runtime Resume Execution Consumer output or a public execution summary after authorized handoff" in text
    assert "Recovery must not consume Resume Planning internals" in text
    assert "Recovery must not consume Resume Execution Builder internals" in text
    assert "Recovery must not bypass Execution Consumer" in text
    assert "## Downstream Boundary" in text
    assert "Scheduler, Dispatcher, Operator, Persistence, Audit, and Journal remain future downstream domains" in text
    assert "Package 138 must not authorize downstream behavior" in text


def test_boundary_matrix_exists_and_contains_required_domains():
    text = _text(BLUEPRINT)
    assert "## Boundary Matrix" in text
    assert "| Domain | Direction | Allowed | Forbidden |" in text
    for domain in (
        "Runtime Resume Execution Consumer",
        "Runtime Resume Execution Builder",
        "Runtime Resume Planning",
        "Runtime Recovery",
        "Scheduler",
        "Dispatcher",
        "Operator",
        "Persistence",
        "Audit",
        "Journal",
        "Replay",
    ):
        assert f"| {domain} |" in text


def test_responsibility_matrix_defines_owner_future_owner_and_forbidden():
    text = _text(BLUEPRINT)
    assert "## Responsibility Matrix" in text
    assert "| Action | Owner | Future Owner | Forbidden |" in text
    for action in (
        "Classify recovery eligibility",
        "Draft recovery plan",
        "Prepare recovery handoff",
        "Execute recovery",
        "Decide scheduler admission",
        "Build dispatcher command",
        "Approve operator action",
        "Commit persistence record",
        "Emit audit record",
        "Emit journal record",
        "Interpret replay token",
    ):
        assert f"| {action} |" in text
    assert "The owner column defines who may do the action now" in text
    assert "The forbidden column defines who cannot do the action" in text


def test_recovery_lifecycle_phases_are_listed():
    text = _text(BLUEPRINT)
    assert "## Recovery Lifecycle Phases" in text
    phases = (
        "1. Blueprint",
        "2. Contract",
        "3. Validation",
        "4. Planner / Builder",
        "5. Consumer Boundary",
        "6. Closure Review",
        "7. Integration Blueprint",
    )
    positions = [text.index(phase) for phase in phases]
    assert positions == sorted(positions)


def test_failure_ownership_matrix_exists_with_required_failures():
    text = _text(BLUEPRINT)
    assert "## Failure Ownership Matrix" in text
    assert "| Failure | Single Owner | Rule |" in text
    for failure in (
        "recoverable_execution_failure",
        "nonrecoverable_execution_failure",
        "invalid_execution_handoff",
        "recovery_not_authorized",
        "scheduler_required",
        "operator_required",
        "persistence_required",
        "audit_required",
        "journal_required",
    ):
        assert f"| {failure} |" in text
    assert "Each failure has exactly one owner" in text


def test_dependency_graph_contains_required_arrows():
    text = _text(BLUEPRINT)
    assert "## Dependency Graph" in text
    for arrow in (
        "Runtime Resume Execution Consumer -> Runtime Recovery",
        "Runtime Recovery -> Future Scheduler",
        "Runtime Recovery -> Future Persistence",
        "Runtime Recovery -> Future Audit",
        "Runtime Recovery -> Future Journal",
    ):
        assert arrow in text
    assert "Runtime Recovery must not reverse-import upstream internals" in text


def test_api_roadmap_package_139_through_144_exists():
    text = _text(BLUEPRINT)
    assert "## Recovery API Roadmap" in text
    for package in (
        "Package 139: Runtime Recovery Contract",
        "Package 140: Runtime Recovery Validation",
        "Package 141: Runtime Recovery Planner / Builder",
        "Package 142: Runtime Recovery Consumer Boundary",
        "Package 143: Runtime Recovery Closure Review",
        "Package 144: Runtime Recovery Integration Blueprint",
    ):
        assert package in text


def test_forbidden_behavior_tokens_are_present_as_forbidden_text():
    text = _text(BLUEPRINT)
    assert "## Forbidden Behavior" in text
    for token in (
        "no `recover(...)`",
        "no `schedule(...)`",
        "no `dispatch(...)`",
        "no `operate(...)`",
        "no `persist(...)`",
        "no `audit(...)`",
        "no `journal(...)`",
        "no `replay(...)`",
        "no `subprocess`",
        "no file writes",
        "no runtime mutation",
    ):
        assert token in text


def test_no_recovery_implementation_file_is_added_or_required():
    text = _text(BLUEPRINT)
    entry = _package_138_entry()
    assert not RECOVERY_IMPLEMENTATION.exists()
    assert "core/runtime/aer_runtime_recovery.py" not in text
    assert "core/runtime/aer_runtime_recovery.py" not in entry
    assert "modified core runtime modules" not in text


def test_go_decision_and_next_package_are_present():
    text = _text(BLUEPRINT)
    assert "Final decision: GO" in text
    assert "Next package: Package 139: Runtime Recovery Contract" in text


def test_package_sequence_contains_package_138_and_package_139_next():
    entry = _package_138_entry()
    assert "## Package 138" in entry
    assert "Package 138: Runtime Recovery Blueprint" in entry
    assert "documentation and seal only" in entry
    assert "Blueprint only" in entry
    assert "must not modify runtime code" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 139: Runtime Recovery Contract" in entry
    assert "Recovery Ownership Matrix" in entry
    assert "Responsibility Matrix" in entry
