from pathlib import Path


BLUEPRINT = Path("docs/aer_runtime_resume_execution_blueprint.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _read(path: Path) -> str:
    assert path.exists(), f"missing required file: {path}"
    return path.read_text(encoding="utf-8")


def test_execution_blueprint_file_exists_and_declares_package_130():
    text = _read(BLUEPRINT)

    assert "# AER Runtime Resume Execution Blueprint" in text
    assert "Package 130" in text
    assert "architecture + seal only" in text
    assert "does not implement runtime resume execution" in text
    assert "Final decision: GO" in text
    assert "Ready for Package 131: Runtime Resume Execution Contract" in text


def test_domain_position_requires_consumer_boundary_before_execution():
    text = _read(BLUEPRINT)

    required_order = [
        "Runtime Snapshot Consumer",
        "Resume Eligibility",
        "Resume Planning",
        "Resume Plan Summary",
        "Resume Consumer Boundary",
        "Runtime Resume Execution",
        "Recovery",
        "Scheduler",
    ]
    cursor = -1
    for token in required_order:
        next_cursor = text.find(token, cursor + 1)
        assert next_cursor > cursor, token
        cursor = next_cursor

    assert "No domain may skip over Resume Consumer Boundary" in text
    assert "No domain may skip over Runtime Resume Execution" in text


def test_upstream_boundary_forbids_resume_and_snapshot_internals():
    text = _read(BLUEPRINT)

    for token in (
        "raw Resume Plan payloads",
        "Resume Plan private helper state",
        "Resume Eligibility internals",
        "Snapshot Builder output",
        "Snapshot Validator internals",
        "Runtime Snapshot Consumer private helpers",
        "runtime execution state",
        "callables",
    ):
        assert token in text

    assert "Package 130 does not authorize any input as executable" in text


def test_downstream_domains_remain_future_owned():
    text = _read(BLUEPRINT)

    for token in (
        "Recovery owns recovery decisions and recovery classification.",
        "Scheduler owns scheduling, queueing, worker selection, retry timing, and execution admission.",
        "Dispatcher owns dispatch commands and execution routing.",
        "Operator owns operator-facing decisions, approvals, and issue handling.",
        "Persistence owns durable records and stores.",
        "Audit owns audit records.",
        "Journal owns journal events and replay streams.",
        "Replay owns replay behavior.",
    ):
        assert token in text


def test_execution_ownership_is_separate_from_recovery_scheduler_and_planning():
    text = _read(BLUEPRINT)

    for token in (
        "execution admission check against a future execution contract",
        "execution precondition validation",
        "execution lifecycle state within the execution domain",
        "execution failure classification",
        "execution result projection",
    ):
        assert token in text

    for token in (
        "Resume Plan construction",
        "Resume Plan validation",
        "Resume Consumer Boundary validation",
        "Recovery policy",
        "Scheduler policy",
        "Dispatcher policy",
        "Operator policy",
        "persistence storage",
        "audit record emission",
        "journal event emission",
        "replay behavior",
    ):
        assert token in text


def test_execution_lifecycle_is_blueprint_only():
    text = _read(BLUEPRINT)

    for token in (
        "candidate_received",
        "precondition_checked",
        "execution_admitted",
        "execution_started",
        "execution_completed",
        "execution_failed",
        "handoff_required",
    ):
        assert token in text

    assert "These phases are blueprint vocabulary only" in text
    assert "must not be used as executable state machine behavior in Package 130" in text


def test_boundary_matrix_names_all_downstream_domains_and_forbidden_behaviors():
    text = _read(BLUEPRINT)

    for row in (
        "| Resume Consumer Boundary | Upstream |",
        "| Runtime Resume Execution | Owner |",
        "| Recovery | Downstream |",
        "| Scheduler | Downstream |",
        "| Dispatcher | Downstream |",
        "| Operator | Downstream |",
        "| Persistence | Downstream |",
        "| Audit | Downstream |",
        "| Journal | Downstream |",
        "| Replay | Downstream |",
    ):
        assert row in text

    for token in (
        "must not schedule, enqueue, choose workers, or retry",
        "must not dispatch or construct dispatcher calls",
        "must not call Operator or create operator decisions",
        "must not persist or create persistence handles",
        "must not audit or create audit handles",
        "must not journal, emit events, replay, or read event streams",
    ):
        assert token in text


def test_failure_ownership_is_single_owner_and_reports_ownership_violations():
    text = _read(BLUEPRINT)

    for token in (
        "Missing Resume Consumer Output | Runtime Resume Execution",
        "Invalid Resume Consumer Output | Runtime Resume Execution",
        "Resume Plan internals consumed directly | Runtime Resume Execution | Ownership Violation",
        "Snapshot Builder output consumed directly | Runtime Resume Execution | Ownership Violation",
        "Recovery called from Resume Execution without contract | Future Recovery | Ownership Violation",
        "Scheduler called from Resume Execution without contract | Future Scheduler | Ownership Violation",
        "Runtime mutation before execution admission | Runtime Resume Execution | Ownership Violation",
    ):
        assert token in text

    assert "Each failure belongs to exactly one owner" in text
    assert "must not introduce shared ownership or implicit recovery" in text


def test_execution_to_recovery_scheduler_dispatcher_operator_boundaries_are_explicit():
    text = _read(BLUEPRINT)

    for heading in (
        "## Execution to Recovery Boundary",
        "## Execution to Scheduler Boundary",
        "## Execution to Dispatcher Boundary",
        "## Execution to Operator Boundary",
    ):
        assert heading in text

    for token in (
        "call Recovery directly",
        "call Scheduler",
        "call Dispatcher",
        "call Operator",
        "bypass Runtime Resume Execution",
        "own execution lifecycle state",
    ):
        assert token in text


def test_state_machine_is_future_contract_requirement_not_implementation():
    text = _read(BLUEPRINT)

    assert "## Execution State Machine Blueprint" in text
    assert "A future Runtime Resume Execution state machine must be explicit" in text
    assert "The state machine is a future contract requirement, not an implementation in Package 130." in text

    for token in (
        "implementing these states as code",
        "adding transition functions",
        "mutating runtime state",
        "changing scheduler status",
        "changing recovery status",
        "writing persistence records",
        "emitting audit records",
        "emitting journal events",
        "replaying execution",
        "retrying execution",
        "repairing execution",
    ):
        assert token in text


def test_public_api_roadmap_does_not_authorize_execution_apis_now():
    text = _read(BLUEPRINT)

    for token in (
        "Package 130 does not define public runtime functions.",
        "build_resume_execution_candidate(...)",
        "validate_resume_execution_candidate(...)",
        "admit_resume_execution(...)",
        "build_resume_execution_result(...)",
        "validate_resume_execution_result(...)",
        "resume_execution_to_summary(...)",
    ):
        assert token in text

    for token in (
        "resume(...)",
        "execute_resume(...)",
        "recover(...)",
        "schedule(...)",
        "dispatch(...)",
        "operate(...)",
        "persist(...)",
        "audit(...)",
        "journal(...)",
        "replay(...)",
    ):
        assert token in text


def test_forbidden_imports_calls_and_no_runtime_mutation_are_sealed():
    text = _read(BLUEPRINT)

    for token in (
        "Scheduler",
        "TaskRunner",
        "Recovery",
        "Dispatcher",
        "Operator",
        "Persistence",
        "Audit",
        "Journal",
        "Replay",
        "Runtime loop modules",
        "Operator loop modules",
        "Snapshot Builder",
        "Snapshot Validator private helpers",
        "Resume Planning private helpers",
    ):
        assert token in text

    for token in (
        "must not read or write files",
        "mutate scheduler queues",
        "mutate operator state",
        "mutate dispatcher state",
        "mutate persistence records",
        "mutate recovery state",
        "allocate runtime identity",
        "bind workspaces",
        "introduce locks",
        "introduce leases",
        "introduce reservations",
        "introduce execution permissions",
    ):
        assert token in text


def test_dependency_graph_allows_only_forward_contract_direction():
    text = _read(BLUEPRINT)

    assert "Resume Consumer Boundary\n  -> Runtime Resume Execution\n  -> Future Recovery Handoff\n  -> Future Scheduler Handoff" in text

    for token in (
        "Runtime Resume Execution -> Resume Planning private helpers",
        "Runtime Resume Execution -> Snapshot Builder",
        "Runtime Resume Execution -> Snapshot Validator",
        "Runtime Resume Execution -> Recovery implementation",
        "Runtime Resume Execution -> Scheduler implementation",
        "Runtime Resume Execution -> Dispatcher implementation",
        "Runtime Resume Execution -> Operator implementation",
        "Runtime Resume Execution -> Persistence implementation",
        "Runtime Resume Execution -> Audit implementation",
        "Runtime Resume Execution -> Journal implementation",
        "Runtime Resume Execution -> Replay implementation",
    ):
        assert token in text

    assert "Runtime Resume Execution may never become a cross-domain orchestrator" in text


def test_closure_criteria_and_next_package_are_explicit():
    text = _read(BLUEPRINT)

    for token in (
        "Runtime Resume Execution is clearly downstream of Resume Consumer Boundary.",
        "Runtime Resume Execution is not hidden inside Resume Planning or Resume Consumer Boundary.",
        "Recovery, Scheduler, Dispatcher, Operator, Persistence, Audit, Journal, and Replay remain downstream future domains.",
        "Execution lifecycle phases are blueprint vocabulary only.",
        "Failure ownership is single-owner",
        "No implementation module is added.",
        "No runtime behavior is added.",
        "No downstream module imports are authorized.",
        "Future packages are ordered as Execution Contract before Execution Implementation.",
    ):
        assert token in text


def test_package_sequence_contains_package_130_entry_and_future_package_131():
    text = _read(PACKAGE_SEQUENCE)

    assert "## Package 130" in text
    assert "Package 130: Runtime Resume Execution Blueprint" in text
    assert "`docs/aer_runtime_resume_execution_blueprint.md`" in text
    assert "`tests/test_aer_runtime_resume_execution_blueprint.py`" in text
    assert "Final decision: GO" in text
    assert "Ready for Package 131: Runtime Resume Execution Contract" in text


def test_package_sequence_seals_no_implementation_for_package_130():
    text = _read(PACKAGE_SEQUENCE)
    package_130 = text.split("## Package 130", 1)[1].split("## Future Foundation Work", 1)[0]

    for token in (
        "must not modify runtime code",
        "must not implement Runtime Resume Execution",
        "must not implement Recovery",
        "must not implement Scheduler integration",
        "must not implement Dispatcher integration",
        "must not implement Operator integration",
        "must not implement Persistence",
        "must not implement Audit",
        "must not implement Journal",
        "must not implement Replay",
        "must not execute runtime",
        "must not recover runtime",
        "must not schedule work",
        "must not dispatch work",
        "must not mutate runtime state",
    ):
        assert token in package_130
