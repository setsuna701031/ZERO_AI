from pathlib import Path


INTENT = Path("docs/contracts/runtime/recovery_execution_intent_v1.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_147_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 147")
    end = text.find("## Package 148", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_intent_contract_exists():
    assert INTENT.exists()


def test_required_sections_exist():
    text = _text(INTENT)
    for section in (
        "## Purpose",
        "## Intent Ownership",
        "## Public Intent Surface",
        "## Intent Request Schema",
        "## Intent Response Schema",
        "## Required Authority Reference",
        "## Intent State Model",
        "## Intent Action Vocabulary",
        "## Allowed Intent Actions",
        "## Forbidden Intent Actions",
        "## Boundary Rules",
        "## Dependency Rules",
        "## Failure Taxonomy",
        "## Compatibility Policy",
        "## Intent Evolution Policy",
        "## GO / NO-GO",
        "## Next Package",
    ):
        assert section in text


def test_request_schema_exists():
    text = _text(INTENT)
    assert "aer.runtime.recovery.execution_intent_request.v1" in text
    for field in (
        "`intent_request_id`",
        "`requesting_owner`",
        "`intent_owner`",
        "`authority_response_contract`",
        "`authority_request_id`",
        "`authority_decision`",
        "`recovery_token`",
        "`integration_response_contract`",
        "`requested_actions`",
        "`intent_only`",
    ):
        assert field in text


def test_response_schema_exists():
    text = _text(INTENT)
    assert "aer.runtime.recovery.execution_intent_response.v1" in text
    for field in (
        "`authority_reference`",
        "`accepted`",
        "`status`",
        "`state`",
        "`intended_actions`",
        "`denied_actions`",
        "`denied_capabilities`",
        "`executes_recovery`",
        "`intent_only`",
    ):
        assert field in text
    assert "`executes_recovery` must remain `false`" in text


def test_authority_reference_exists():
    text = _text(INTENT)
    assert "## Required Authority Reference" in text
    assert "aer.runtime.recovery.execution_authority_request.v1" in text
    assert "aer.runtime.recovery.execution_authority_response.v1" in text
    assert "authorized_for_future_handoff" in text
    assert "Authority reference is data-only" in text


def test_intent_state_model_exists():
    text = _text(INTENT)
    assert "## Intent State Model" in text
    for state in (
        "`requested`",
        "`described`",
        "`denied`",
        "`blocked`",
        "`invalid`",
    ):
        assert state in text
    assert "does not persist Recovery state" in text
    assert "does not mutate runtime state" in text


def test_allowed_and_forbidden_intent_actions_documented():
    text = _text(INTENT)
    for allowed in (
        "`describe_recovery_execution_intent`",
        "`describe_recovery_plan_handoff_intent`",
        "`describe_scheduler_admission_intent`",
        "`describe_dispatcher_command_intent`",
        "`describe_operator_decision_intent`",
        "`describe_persistence_alignment_intent`",
        "`describe_audit_alignment_intent`",
        "`describe_journal_alignment_intent`",
        "`describe_replay_alignment_intent`",
    ):
        assert allowed in text
    for forbidden in (
        "execute Recovery",
        "invoke Scheduler behavior",
        "invoke Dispatcher behavior",
        "invoke Operator runtime behavior",
        "persist Recovery state",
        "replay Recovery",
        "emit audit records",
        "emit journal records",
        "mutate runtime state",
        "perform file IO",
        "call subprocess",
        "call runtime execution modules",
    ):
        assert forbidden in text


def test_compatibility_policy_exists():
    text = _text(INTENT)
    assert "## Compatibility Policy" in text
    assert "aer.runtime.recovery.integration_response.v1" in text
    assert "aer.runtime.recovery.execution_authority_response.v1" in text
    assert "separation between intent and execution" in text


def test_go_no_go_exists():
    text = _text(INTENT)
    assert "## GO / NO-GO" in text
    assert "Final decision: GO" in text
    assert "intent-only package" in text
    assert "Execution Intent MAY describe intended Recovery actions" in text
    assert "Execution Intent MUST NOT execute" in text
    assert "Next package: Package 148" in text


def test_package_147_sequence_entry_exists():
    entry = _package_147_entry()
    assert "## Package 147" in entry
    assert "Package 147: Runtime Recovery Execution Intent" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 148" in entry
    assert "Execution Intent MAY describe intended Recovery actions" in entry
    assert "Execution Intent MUST NOT execute" in entry


def test_no_forbidden_runtime_behavior_tokens():
    text = _text(INTENT)
    for token in (
        "def execute_recovery",
        "class RecoveryExecutor",
        "scheduler.schedule(",
        "dispatcher.dispatch(",
        "operator.apply(",
        "runtime_supervisor.",
        "recovery_executor.",
        "task_runner.run(",
        "subprocess.",
        "open(",
        ".write(",
        "Path(",
    ):
        assert token not in text
