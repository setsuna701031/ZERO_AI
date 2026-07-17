from pathlib import Path


BLUEPRINT = Path("docs/aer_runtime_resume_integration_blueprint.md")
RESUME_CONSUMER_CONTRACT = Path("docs/contracts/runtime/resume_consumer_v1.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _read(path: Path) -> str:
    assert path.exists(), f"missing required file: {path}"
    return path.read_text(encoding="utf-8")


def test_runtime_resume_integration_blueprint_exists_and_is_architecture_only():
    text = _read(BLUEPRINT)

    assert "# AER Runtime Resume Integration Blueprint" in text
    assert "Package 129 closes the Runtime Resume domain" in text
    assert "architecture + seal only" in text
    assert "does not add runtime code" in text
    assert "does not implement any downstream domain" in text
    assert "Final decision: GO" in text


def test_resume_domain_closes_at_consumer_boundary():
    text = _read(BLUEPRINT)

    assert "Runtime Resume is closed at Resume Consumer Boundary." in text
    assert "The public exit from Runtime Resume is the Resume Consumer Boundary." in text
    assert "Resume Plan public summary" in text
    assert "Resume Consumer Input contract" in text
    assert "Resume Consumer Output contract" in text
    assert "Resume Consumer Boundary descriptor" in text


def test_integration_sequence_is_ordered_and_does_not_skip_domains():
    text = _read(BLUEPRINT)

    expected = """Runtime Snapshot Consumer
↓
Resume Eligibility
↓
Resume Planning
↓
Resume Plan Summary
↓
Resume Consumer Boundary
↓
Future Runtime Resume Execution
↓
Future Recovery
↓
Future Scheduler / Dispatcher / Operator integration"""
    assert expected in text
    assert "No downstream domain may skip directly to Resume Eligibility" in text


def test_handoff_matrix_blocks_direct_scheduler_recovery_dispatcher_operator_consumption():
    text = _read(BLUEPRINT)

    required_rows = [
        "| Resume Plan Summary | Resume Consumer Boundary | Allowed as the only downstream-facing Resume input.",
        "| Resume Consumer Boundary | Future Runtime Resume Execution | Future-only after a dedicated execution-domain package authorizes it.",
        "| Resume Consumer Boundary | Future Recovery | Future-only after Recovery owns and defines its contract.",
        "| Resume Consumer Boundary | Future Scheduler | Not authorized in Package 129.",
        "| Resume Consumer Boundary | Future Dispatcher | Not authorized in Package 129.",
        "| Resume Consumer Boundary | Future Operator | Not authorized in Package 129.",
        "| Resume Consumer Boundary | Future Persistence | Not authorized in Package 129.",
        "| Resume Consumer Boundary | Future Audit | Not authorized in Package 129.",
        "| Resume Consumer Boundary | Future Journal | Not authorized in Package 129.",
        "| Resume Consumer Boundary | Future Replay | Not authorized in Package 129.",
    ]
    for row in required_rows:
        assert row in text


def test_forbidden_integration_shortcuts_are_explicit():
    text = _read(BLUEPRINT)

    forbidden = [
        "Scheduler consuming Resume Eligibility directly",
        "Scheduler consuming Resume Plan internals directly",
        "Dispatcher consuming Resume Plan as a dispatch command",
        "Recovery consuming Resume Plan internals directly",
        "Recovery bypassing Runtime Resume Execution",
        "Operator treating Resume Consumer Output as an operator decision",
        "Persistence storing Resume Consumer payloads without a persistence-domain contract",
        "Audit emitting audit records from Resume Consumer payloads without an audit-domain contract",
        "Journal emitting events from Resume Consumer payloads without a journal-domain contract",
        "Replay treating Resume Consumer Output as a replay token",
        "Runtime Resume Execution hidden inside eligibility, planning, summaries, metadata, consumer input, or consumer output",
        "Snapshot Builder output passed to any Resume downstream domain",
        "Snapshot validation duplicated inside Resume Integration",
    ]
    for rule in forbidden:
        assert rule in text


def test_integration_boundary_rules_forbid_execution_and_downstream_imports():
    text = _read(BLUEPRINT)

    for rule in [
        "execute runtime",
        "resume runtime",
        "recover runtime",
        "schedule work",
        "dispatch work",
        "call operator",
        "persist data",
        "audit data",
        "journal events",
        "replay events",
        "mutate runtime state",
        "allocate runtime identity",
        "import Scheduler, TaskRunner, Recovery, Dispatcher, Operator, Persistence, Audit, Journal, Replay, runtime loop, or operator loop modules",
    ]:
        assert rule in text


def test_failure_ownership_has_exact_downstream_owners():
    text = _read(BLUEPRINT)

    for owner in [
        "Future Runtime Resume Execution",
        "Future Recovery",
        "Future Scheduler",
        "Future Dispatcher",
        "Future Operator",
        "Future Persistence",
        "Future Audit",
        "Future Journal",
        "Future Replay",
    ]:
        assert owner in text

    assert "Ownership violation" in text


def test_dependency_graph_is_one_way_and_private_helpers_are_forbidden():
    text = _read(BLUEPRINT)

    assert "Allowed dependency direction is left to right only." in text
    assert "Resume must not import or call downstream domains." in text
    assert "Downstream domains must not import Resume private helpers." in text


def test_closure_criteria_require_all_resume_domain_layers():
    text = _read(BLUEPRINT)

    for criterion in [
        "Runtime Resume Contract exists and separates Eligibility, Planning, and Execution Boundary.",
        "Runtime Resume Planning exists and implements only Eligibility and Planning.",
        "Resume Consumer Contract exists and defines the downstream public boundary.",
        "Integration Blueprint defines the only authorized handoff path.",
        "Execution remains future-domain only.",
        "No hidden runtime execution surface exists in Resume Domain.",
        "No direct Snapshot Builder dependency exists in Resume Domain.",
        "No Snapshot validation duplication exists in Resume Domain.",
    ]:
        assert criterion in text


def test_resume_consumer_contract_readiness_points_to_package_129():
    text = _read(RESUME_CONSUMER_CONTRACT)

    assert "Ready for Package 129: Runtime Resume Integration Blueprint." in text
    assert "Package 129 should define the architecture" in text
    assert "does not authorize any downstream domain to execute, schedule, recover, dispatch, operate, persist, audit, journal, or replay" in text


def test_package_sequence_contains_package_128_and_129_entries():
    text = _read(PACKAGE_SEQUENCE)

    assert "## Package 128" in text
    assert "Package 128: Runtime Resume Consumer Contract" in text
    assert "## Package 129" in text
    assert "Package 129: Runtime Resume Integration Blueprint" in text
    assert "Runtime Resume Domain is closed at the integration-boundary level." in text
    assert "Ready for Package 130: Runtime Resume Execution Blueprint" in text


def test_package_sequence_keeps_runtime_resume_execution_future_domain_only():
    text = _read(PACKAGE_SEQUENCE)

    package_129 = text.split("## Package 129", 1)[1]
    assert "Runtime Resume Execution remains future-domain only" in package_129
    assert "Recovery, Scheduler, Dispatcher, Operator, Persistence, Audit, Journal, and Replay remain downstream domains" in package_129
    assert "Package 130: Runtime Resume Execution Blueprint" in package_129


def test_blueprint_does_not_define_execution_api_or_runtime_behavior():
    text = _read(BLUEPRINT)

    forbidden_public_apis = [
        "def resume(",
        "def execute_resume(",
        "def recover(",
        "def schedule(",
        "def dispatch(",
        "def operate(",
        "def persist(",
        "def audit(",
        "def journal(",
        "def replay(",
    ]
    for token in forbidden_public_apis:
        assert token not in text

    assert "Package 129 does not authorize execution." in text
