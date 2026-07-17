from pathlib import Path


AUTHORITY = Path("docs/contracts/runtime/recovery_execution_authority_v1.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_146_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 146")
    end = text.find("## Package 147", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_authority_contract_exists():
    assert AUTHORITY.exists()


def test_required_sections_exist():
    text = _text(AUTHORITY)
    for section in (
        "## Purpose",
        "## Authority Ownership",
        "## Public Authority Surface",
        "## Authority Request Schema",
        "## Authority Response Schema",
        "## Authority Decision Model",
        "## Allowed Authority Owners",
        "## Forbidden Authority Owners",
        "## Authority State Model",
        "## Decision Outcomes",
        "## Failure Taxonomy",
        "## Boundary Rules",
        "## Dependency Rules",
        "## Compatibility Policy",
        "## Authority Evolution Policy",
        "## GO / NO-GO",
        "## Next Package",
    ):
        assert section in text


def test_request_schema_exists():
    text = _text(AUTHORITY)
    assert "aer.runtime.recovery.execution_authority_request.v1" in text
    for field in (
        "`authority_request_id`",
        "`requesting_owner`",
        "`authority_owner`",
        "`recovery_token`",
        "`integration_response_contract`",
        "`requested_decision`",
        "`authority_only`",
    ):
        assert field in text


def test_response_schema_exists():
    text = _text(AUTHORITY)
    assert "aer.runtime.recovery.execution_authority_response.v1" in text
    for field in (
        "`authorized`",
        "`decision`",
        "`state`",
        "`authorized_scope`",
        "`downstream_requirements`",
        "`denied_capabilities`",
        "`executes_recovery`",
    ):
        assert field in text
    assert "`executes_recovery` must remain `false`" in text


def test_decision_model_exists():
    text = _text(AUTHORITY)
    assert "## Authority Decision Model" in text
    assert "separates authorization from execution" in text
    assert "authorized_for_future_handoff" in text
    assert "denied_by_authority" in text
    assert "blocked_missing_downstream_contract" in text


def test_authority_ownership_exists():
    text = _text(AUTHORITY)
    assert "## Authority Ownership" in text
    assert "Runtime Recovery Execution Authority is owned" in text
    assert "runtime_recovery_execution_authority" in text
    assert "Only `runtime_recovery_execution_authority` may produce `authorized_for_future_handoff`" in text


def test_forbidden_owners_documented():
    text = _text(AUTHORITY)
    for owner in (
        "`scheduler`",
        "`dispatcher`",
        "`operator_runtime`",
        "`runtime_supervisor`",
        "`recovery_executor`",
        "`task_runner`",
        "`persistence`",
        "`audit`",
        "`journal`",
        "`replay`",
        "`runtime_execution_loop`",
        "`file_io_owner`",
        "`subprocess_owner`",
    ):
        assert owner in text


def test_compatibility_policy_exists():
    text = _text(AUTHORITY)
    assert "## Compatibility Policy" in text
    assert "aer.runtime.recovery.integration_response.v1" in text
    assert "aer.runtime.recovery.plan.v1" in text
    assert "separation between authorization and execution" in text


def test_go_no_go_exists():
    text = _text(AUTHORITY)
    assert "## GO / NO-GO" in text
    assert "Final decision: GO" in text
    assert "authority-only package" in text
    assert "Execution Authority MAY authorize" in text
    assert "Execution Authority MUST NOT execute" in text


def test_package_146_sequence_entry_exists():
    entry = _package_146_entry()
    assert "## Package 146" in entry
    assert "Package 146: Runtime Recovery Execution Authority" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 147" in entry
    assert "Execution Authority MAY authorize" in entry
    assert "Execution Authority MUST NOT execute" in entry


def test_no_forbidden_runtime_behavior_tokens():
    text = _text(AUTHORITY)
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
