from pathlib import Path

CONTRACT = Path("docs/contracts/runtime/resume_execution_v1.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_resume_execution_contract_document_exists():
    assert CONTRACT.exists()
    text = _text(CONTRACT)
    assert text.startswith("# AER Runtime Resume Execution Contract v1")
    assert "Package 131" in text
    assert "contract/spec + seal only" in text


def test_contract_defines_required_schema_names():
    text = _text(CONTRACT)
    for schema in (
        "aer.runtime.resume.execution_request.v1",
        "aer.runtime.resume.execution_result.v1",
        "aer.runtime.resume.execution_failure.v1",
    ):
        assert schema in text
    assert "Execution Request, Execution Result, and Execution Failure must never collapse into one public API" in text


def test_contract_consumes_only_resume_consumer_output():
    text = _text(CONTRACT)
    assert "Runtime Resume Consumer Output" in text
    assert "aer.runtime.resume.consumer_output.v1" in text
    assert "Resume Consumer Output is the only authorized upstream public surface" in text
    assert "raw Resume Plan payloads" in text
    assert "Snapshot Builder output" in text


def test_downstream_domains_remain_future_owned():
    text = _text(CONTRACT)
    for domain in (
        "Recovery owns recovery decisions",
        "Scheduler owns scheduling",
        "Dispatcher owns dispatch commands",
        "Operator owns operator-facing decisions",
        "Persistence owns durable records",
        "Audit owns audit records",
        "Journal owns journal events",
        "Replay owns replay behavior",
    ):
        assert domain in text


def test_boundary_matrix_lists_core_domains_and_forbidden_actions():
    text = _text(CONTRACT)
    for row in (
        "| Resume Consumer Output | Upstream |",
        "| Runtime Resume Execution Request | Internal output |",
        "| Runtime Resume Execution Result | Internal output |",
        "| Runtime Resume Execution Failure | Internal output |",
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
    for forbidden in ("must not schedule", "must not dispatch", "must not audit", "must not journal"):
        assert forbidden in text.lower()


def test_execution_request_required_fields_are_sealed():
    text = _text(CONTRACT)
    for field in (
        "`execution_request_id`",
        "`resume_token`",
        "`snapshot_id`",
        "`lineage`",
        "`source_contract`",
        "`source_status`",
        "`source_reason`",
        "`execution_allowed`",
        "`requested_action`",
        "`preconditions`",
        "`failure_policy`",
        "`metadata`",
        "`descriptive_only`",
    ):
        assert field in text
    assert "`execution_allowed` must be false in Package 131" in text


def test_execution_result_required_fields_and_statuses_are_sealed():
    text = _text(CONTRACT)
    for field in (
        "`completed`",
        "`failed`",
        "`failure`",
        "`downstream_handoff_required`",
        "`downstream_handoff_type`",
    ):
        assert field in text
    for status in (
        "`not_started`",
        "`blocked`",
        "`validated`",
        "`completed`",
        "`failed`",
        "`handoff_required`",
    ):
        assert status in text


def test_execution_failure_vocabulary_is_sealed():
    text = _text(CONTRACT)
    for code in (
        "`invalid_execution_request`",
        "`invalid_consumer_output`",
        "`consumer_boundary_violation`",
        "`execution_not_authorized`",
        "`precondition_failed`",
        "`lineage_mismatch`",
        "`identity_mismatch`",
        "`unsupported_requested_action`",
        "`future_domain_required`",
        "`downstream_contract_missing`",
        "`runtime_execution_failed`",
        "`ownership_violation`",
    ):
        assert code in text
    for category in (
        "`Compatibility Error`",
        "`Consumer Boundary Error`",
        "`Execution Boundary Error`",
        "`Precondition Error`",
        "`Future Domain Required`",
        "`Ownership Violation`",
    ):
        assert category in text


def test_public_api_is_future_only_and_behavior_is_forbidden():
    text = _text(CONTRACT)
    for future_api in (
        "`create_execution_request(...)`",
        "`validate_execution_request(...)`",
        "`create_execution_result(...)`",
        "`validate_execution_result(...)`",
        "`create_execution_failure(...)`",
        "`validate_execution_failure(...)`",
        "`execution_result_to_summary(...)`",
    ):
        assert future_api in text
    for forbidden_api in (
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
        assert forbidden_api in text


def test_validation_contract_is_descriptive_only_and_no_auto_repair():
    text = _text(CONTRACT)
    assert "Validation reports are descriptive only. No auto-repair is allowed." in text
    assert "Execution Request Validation" in text
    assert "Execution Result Validation" in text
    assert "Execution Failure Validation" in text
    assert "unknown fields are prohibited" in text
    assert "runtime objects and executable callables are prohibited" in text


def test_identity_lineage_status_and_unknown_field_policies_are_present():
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
    assert "must not allocate runtime session identity" in text
    assert "must not repair lineage" in text


def test_failure_ownership_matrix_has_single_owner_rows():
    text = _text(CONTRACT)
    assert "## Failure Ownership Matrix" in text
    for row in (
        "| invalid execution request | `invalid_execution_request` | Compatibility Error | Runtime Resume Execution |",
        "| invalid consumer output | `invalid_consumer_output` | Consumer Boundary Error | Runtime Resume Consumer Boundary |",
        "| execution not authorized | `execution_not_authorized` | Execution Boundary Error | Runtime Resume Execution |",
        "| ownership violation | `ownership_violation` | Ownership Violation | Runtime Resume Execution |",
    ):
        assert row in text


def test_dependency_graph_forbids_downstream_internals():
    text = _text(CONTRACT)
    assert "Runtime Resume Consumer Output" in text
    assert "-> Runtime Resume Execution Request" in text
    assert "-> Runtime Resume Execution Result" in text
    assert "-> Runtime Resume Execution Failure" in text
    for forbidden in (
        "-> Scheduler internals",
        "-> Recovery internals",
        "-> Dispatcher internals",
        "-> Operator internals",
        "-> Persistence internals",
        "-> Audit internals",
        "-> Journal internals",
        "-> Replay internals",
        "-> Snapshot Builder",
        "-> Resume Plan internals",
    ):
        assert forbidden in text


def test_forbidden_imports_calls_and_runtime_mutation_are_sealed():
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
        "Runtime loop modules",
        "Snapshot Builder",
        "Resume Planning private helpers",
    ):
        assert forbidden in text
    assert "## No Runtime Mutation" in text
    assert "must not read or write files" in text


def test_contract_go_decision_and_next_package_are_present():
    text = _text(CONTRACT)
    assert "Final decision: GO." in text
    assert "Ready for Package 132: Runtime Resume Execution Validation." in text
    assert "Package 132 may implement validation helpers" in text
    assert "must not implement execution behavior" in text


def test_package_sequence_contains_package_131_entry():
    assert PACKAGE_SEQUENCE.exists()
    text = _text(PACKAGE_SEQUENCE)
    assert "## Package 131" in text
    assert "Package 131: Runtime Resume Execution Contract" in text
    assert "docs/contracts/runtime/resume_execution_v1.md" in text
    assert "tests/test_aer_runtime_resume_execution_contract.py" in text
    assert "Final decision: GO" in text
    assert "Ready for Package 132: Runtime Resume Execution Validation" in text


def test_package_sequence_forbids_implementation_in_package_131():
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 131")
    entry = text[start:]
    for phrase in (
        "must not implement Runtime Resume Execution",
        "must not implement Recovery",
        "must not implement Scheduler integration",
        "must not implement Dispatcher integration",
        "must not implement Operator integration",
        "must not execute runtime",
        "must not schedule work",
        "must not dispatch work",
        "must not persist data",
        "must not audit data",
        "must not journal events",
        "must not replay events",
    ):
        assert phrase in entry
