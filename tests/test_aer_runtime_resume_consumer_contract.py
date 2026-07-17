from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/resume_consumer_v1.md")
RESUME_PLAN_MODULE = Path("core/runtime/aer_runtime_resume_plan.py")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence_package128.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_resume_consumer_contract_document_exists_and_is_contract_only():
    assert CONTRACT.exists()
    text = _text(CONTRACT)

    assert "# AER Runtime Resume Consumer Contract v1" in text
    assert "Package 128 is contract/spec + seal only" in text
    assert "Package 128 does not add a runtime implementation module" in text
    assert "Package 128 does not modify `core/runtime/aer_runtime_resume_plan.py`" in text
    assert "Final decision: GO" in text


def test_resume_consumer_contract_declares_expected_schemas():
    text = _text(CONTRACT)

    for schema in (
        "aer.runtime.resume.consumer_input.v1",
        "aer.runtime.resume.consumer_output.v1",
        "aer.runtime.resume.consumer_boundary.v1",
    ):
        assert schema in text

    assert "aer.runtime.resume.plan.v1" in text
    assert "aer.runtime.resume.execution_boundary.v1" in text


def test_resume_consumer_contract_uses_only_public_resume_plan_surface():
    text = _text(CONTRACT)

    assert "consumes only the public Resume Plan summary produced by `resume_plan_to_summary(...)`" in text
    assert "Resume Plan public summary from `resume_plan_to_summary(...)`" in text
    assert "Validated Resume Plan public contract using schema `aer.runtime.resume.plan.v1`" in text
    assert "must not consume Resume Plan internals" in text
    assert "must not consume private planning helpers or internal planning state" in text


def test_resume_consumer_contract_preserves_snapshot_boundary_rules():
    text = _text(CONTRACT)

    assert "Package 128 must not call Snapshot Consumer, Snapshot Builder, or Snapshot Validator" in text
    assert "Package 128 must never consume Snapshot Builder output directly" in text
    assert "Package 128 must never duplicate Snapshot validation" in text
    assert "Resume Eligibility" in text
    assert "Package 128 must not recompute eligibility" in text


def test_resume_consumer_contract_has_boundary_matrix_for_downstream_domains():
    text = _text(CONTRACT)

    assert "## Boundary Matrix" in text
    assert "| Domain | Direction | Allowed | Forbidden |" in text
    for domain in (
        "Runtime Resume Execution",
        "Recovery",
        "Scheduler",
        "Dispatcher",
        "Operator",
        "Persistence",
        "Audit",
        "Journal",
    ):
        assert f"| {domain} | Downstream |" in text


def test_resume_consumer_contract_forbids_downstream_runtime_behavior():
    text = _text(CONTRACT)

    for phrase in (
        "Package 128 does not authorize any downstream domain to execute, schedule, recover, dispatch, operate, persist, audit, journal, or replay",
        "Execution is outside Package 128 and must not be hidden inside consumer input, output, validation, or summary",
        "Package 128 must not schedule, enqueue, select workers, or choose execution order",
        "Package 128 must not dispatch or construct dispatcher calls",
        "Package 128 must not call Operator or create operator decisions",
        "Package 128 must not persist or create persistence handles",
        "Package 128 must not audit or create audit handles",
        "Package 128 must not journal, replay, emit events, or read event streams",
    ):
        assert phrase in text


def test_consumer_input_contract_required_fields_are_explicit():
    text = _text(CONTRACT)

    assert "## Consumer Input Contract" in text
    for field in (
        "`contract`",
        "`resume_token`",
        "`eligible`",
        "`status`",
        "`reason`",
        "`snapshot_id`",
        "`lineage`",
        "`consumer_status`",
        "`execution_boundary`",
        "`source_valid`",
        "`source_outcome`",
        "`descriptive_only`",
    ):
        assert field in text

    for outcome in (
        "`ready_for_future_consumer`",
        "`blocked`",
        "`invalid_plan`",
        "`invalid_summary`",
        "`execution_not_authorized`",
    ):
        assert outcome in text


def test_consumer_output_and_boundary_contracts_are_explicit():
    text = _text(CONTRACT)

    assert "## Consumer Output Contract" in text
    assert "## Consumer Boundary Contract" in text
    assert "`accepted_for_future_domain` means only that the descriptor is structurally safe" in text
    assert "`accepted_for_future_domain` does not mean runtime execution is allowed" in text
    assert "`future_domain_only` must be true" in text
    assert "`execution_allowed` must be false" in text
    assert "`downstream_authorized` must be false" in text
    assert "not a scheduler admission token" in text


def test_consumer_safe_summary_rule_is_fixed_and_does_not_leak_internals():
    text = _text(CONTRACT)

    assert "## Consumer-Safe Summary Rule" in text
    for allowed in (
        "`contract`",
        "`resume_token`",
        "`eligible`",
        "`status`",
        "`reason`",
        "`snapshot_id`",
        "`lineage`",
        "`consumer_status`",
        "`execution_boundary`",
        "`source_valid`",
        "`source_outcome`",
    ):
        assert allowed in text

    for forbidden in (
        "raw Resume Plan payloads",
        "private Resume Planning helper state",
        "raw Snapshot payloads",
        "Snapshot Builder output",
        "Snapshot Validator internals",
        "scheduler queues",
        "dispatcher calls",
        "operator decisions",
        "persistence handles",
        "audit handles",
        "journal handles",
        "replay streams",
        "recovery objects",
        "runtime execution state",
    ):
        assert forbidden in text


def test_unknown_required_type_identity_lineage_and_status_policies_are_sealed():
    text = _text(CONTRACT)

    for section in (
        "## Unknown Field Policy",
        "## Required Field Policy",
        "## Type Policy",
        "## Identity Policy",
        "## Lineage Policy",
        "## Status Policy",
    ):
        assert section in text

    assert "Unknown fields must not be ignored, renamed, embedded in metadata, persisted, audited, journaled, replayed, passed through, or executed" in text
    assert "Package 128 must not use metadata as an escape hatch" in text
    assert "Package 128 must not allocate runtime session identity" in text
    assert "Package 128 must not repair lineage, infer lineage, merge lineage" in text
    assert "must not be interpreted as scheduler statuses" in text


def test_error_taxonomy_assigns_downstream_violations_to_future_domains():
    text = _text(CONTRACT)

    assert "## Error Taxonomy" in text
    for row in (
        "| downstream domain tries to execute | Ownership Violation | Future Runtime Resume Execution |",
        "| recovery consumes without future contract | Ownership Violation | Future Recovery |",
        "| scheduler consumes without future contract | Ownership Violation | Future Scheduler |",
        "| dispatcher consumes without future contract | Ownership Violation | Future Dispatcher |",
        "| operator consumes without future contract | Ownership Violation | Future Operator |",
        "| persistence consumes without future contract | Ownership Violation | Future Persistence |",
        "| audit consumes without future contract | Ownership Violation | Future Audit |",
        "| journal consumes without future contract | Ownership Violation | Future Journal |",
    ):
        assert row in text


def test_responsibility_matrix_keeps_exact_owner_boundaries():
    text = _text(CONTRACT)

    assert "## Responsibility Matrix" in text
    assert "| Capability | Owner | Package 128 Allowed | Package 128 Forbidden |" in text
    for owner in (
        "Runtime Resume Planning",
        "Runtime Resume Consumer Boundary",
        "Future Runtime Resume Execution",
        "Future Recovery",
        "Future Scheduler",
        "Future Dispatcher",
        "Future Operator",
        "Future Persistence",
        "Future Audit",
        "Future Journal",
    ):
        assert owner in text


def test_public_api_contract_is_future_only_and_forbids_execution_names():
    text = _text(CONTRACT)

    assert "## Public API Contract" in text
    assert "Package 128 is contract/spec + seal only. It does not implement public runtime functions" in text
    for future_name in (
        "`build_resume_consumer_input(...)`",
        "`validate_resume_consumer_input(...)`",
        "`build_resume_consumer_output(...)`",
        "`validate_resume_consumer_output(...)`",
        "`resume_consumer_input_to_summary(...)`",
        "`resume_consumer_output_to_summary(...)`",
    ):
        assert future_name in text

    for forbidden_name in (
        "`resume(...)`",
        "`execute_resume(...)`",
        "`recover(...)`",
        "`schedule(...)`",
        "`dispatch(...)`",
        "`operate(...)`",
        "`persist(...)`",
        "`audit(...)`",
        "`journal(...)`",
        "`replay(...)`",
    ):
        assert forbidden_name in text


def test_forbidden_import_and_call_section_rejects_downstream_surfaces():
    text = _text(CONTRACT)

    assert "## Forbidden Imports and Calls" in text
    for forbidden in (
        "Scheduler",
        "TaskRunner",
        "Recovery",
        "Dispatcher",
        "Operator",
        "Persistence",
        "Audit",
        "Journal",
        "Replay",
        "Runtime execution modules",
        "Runtime loop modules",
        "Operator loop modules",
        "Snapshot Builder",
        "Snapshot Validator private helpers",
    ):
        assert forbidden in text


def test_existing_resume_plan_module_does_not_grow_consumer_or_execution_surface():
    text = _text(RESUME_PLAN_MODULE)

    for forbidden_public_surface in (
        "build_resume_consumer_input",
        "validate_resume_consumer_input",
        "build_resume_consumer_output",
        "validate_resume_consumer_output",
        "resume_consumer_input_to_summary",
        "resume_consumer_output_to_summary",
        "def resume(",
        "def execute_resume(",
        "def recover(",
        "def schedule(",
        "def dispatch(",
        "def operate(",
    ):
        assert forbidden_public_surface not in text


def test_existing_resume_plan_module_still_has_package_127_public_surface_only():
    text = _text(RESUME_PLAN_MODULE)

    expected_all = '''__all__ = [\n    "ELIGIBILITY_CONTRACT",\n    "PLAN_CONTRACT",\n    "EXECUTION_BOUNDARY_CONTRACT",\n    "check_resume_eligibility",\n    "validate_resume_eligibility",\n    "build_resume_plan",\n    "validate_resume_plan",\n    "resume_eligibility_to_summary",\n    "resume_plan_to_summary",\n]'''
    assert expected_all in text


def test_package_sequence_contains_package_128_consumer_contract_entry():
    text = _text(PACKAGE_SEQUENCE)

    assert "## Package 128" in text
    assert "Package 128: Runtime Resume Consumer Contract" in text
    assert "contract/spec + seal only" in text
    assert "`docs/contracts/runtime/resume_consumer_v1.md`" in text
    assert "`tests/test_aer_runtime_resume_consumer_contract.py`" in text
    assert "Final decision: GO" in text


def test_package_sequence_updates_resume_roadmap_to_integration_blueprint_next():
    text = _text(PACKAGE_SEQUENCE)

    assert "Package 128: Runtime Resume Consumer Contract, if the Package 127 decision is GO" in text
    assert "Package 129: Runtime Resume Integration Blueprint, if the Package 128 decision is GO" in text
    assert "Package 130: Runtime Recovery Blueprint after Resume Integration Blueprint is sealed" in text
    assert "Runtime Resume Execution only after a future execution-domain package authorizes it" in text


def test_package_sequence_package_128_must_not_list_is_complete():
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 128")
    end = text.index("## Future Foundation Work", start)
    package_128 = text[start:end]

    for phrase in (
        "modify `core/runtime/aer_runtime_resume_plan.py`",
        "create Runtime Resume Execution",
        "execute a Resume Plan",
        "schedule",
        "dispatch",
        "recover",
        "call operator",
        "persist",
        "audit",
        "journal",
        "replay",
        "mutate runtime state",
        "allocate runtime sessions",
        "allocate runtime identity",
        "consume Snapshot Builder output directly",
        "duplicate Snapshot validation",
        "collapse Eligibility, Planning, Consumer Boundary, and Execution into one public API",
    ):
        assert phrase in package_128


def test_no_runtime_mutation_section_is_explicit():
    text = _text(CONTRACT)

    assert "## No Runtime Mutation" in text
    assert "Consumer boundary contracts are descriptive only" in text
    assert "Package 128 must not read or write files" in text
    assert "mutate scheduler queues" in text
    assert "mutate operator state" in text
    assert "mutate dispatcher state" in text
    assert "mutate persistence records" in text
    assert "mutate recovery state" in text
    assert "mutate runtime execution state" in text


def test_implementation_readiness_points_to_package_129_not_execution():
    text = _text(CONTRACT)

    assert "## Implementation Readiness" in text
    assert "Ready for Package 129: Runtime Resume Integration Blueprint" in text
    assert "without implementing execution, recovery, scheduling, dispatch, operator behavior, persistence, audit, journal, or replay" in text
    assert "Package 130 should begin Runtime Recovery Blueprint only after Package 129 is sealed" in text
