from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_runtime_bridge_v1.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_148_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 148")
    end = text.find("## Package 149", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_runtime_bridge_contract_exists():
    assert CONTRACT.exists()


def test_required_sections_exist():
    text = _text(CONTRACT)
    for section in (
        "## Purpose",
        "## Public Bridge Surface",
        "## Bridge Request Schema",
        "## Bridge Response Schema",
        "## Required Authority Reference",
        "## Required Intent Reference",
        "## Allowed Bridge Consumers",
        "## Forbidden Bridge Consumers",
        "## Boundary Rules",
        "## Dependency Rules",
        "## Prohibited Runtime Calls",
        "## Compatibility Policy",
        "## Evolution Policy",
        "## GO / NO-GO",
        "## Next Package",
    ):
        assert section in text


def test_bridge_request_schema_exists():
    text = _text(CONTRACT)
    assert "aer.runtime.recovery.runtime_bridge_request.v1" in text
    for field in (
        "`bridge_request_id`",
        "`bridge_consumer`",
        "`authority_reference`",
        "`intent_reference`",
        "`recovery_token`",
        "`requested_bridge_scope`",
        "`metadata`",
        "`bridge_only`",
    ):
        assert field in text


def test_bridge_response_schema_exists():
    text = _text(CONTRACT)
    assert "aer.runtime.recovery.runtime_bridge_response.v1" in text
    for field in (
        "`accepted`",
        "`status`",
        "`authority_reference`",
        "`intent_reference`",
        "`bridge_scope`",
        "`denied_capabilities`",
        "`executes_recovery`",
        "`bridge_only`",
    ):
        assert field in text
    assert "Bridge response acceptance does not authorize execution" in text


def test_required_references_exist():
    text = _text(CONTRACT)
    assert "aer.runtime.recovery.execution_authority_response.v1" in text
    assert "aer.runtime.recovery.execution_intent_response.v1" in text
    assert "authorized_for_future_handoff" in text
    assert "`intent_only: true`" in text
    assert "`executes_recovery: false`" in text


def test_allowed_and_forbidden_consumers_documented():
    text = _text(CONTRACT)
    for allowed in (
        "`runtime_recovery_runtime_bridge`",
        "`runtime_recovery_executor_boundary`",
        "`runtime_recovery_bridge_review`",
    ):
        assert allowed in text
    for forbidden in (
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
    ):
        assert forbidden in text


def test_prohibited_runtime_calls_and_compatibility_exist():
    text = _text(CONTRACT)
    assert "## Prohibited Runtime Calls" in text
    assert "Scheduler admission or scheduling paths" in text
    assert "Dispatcher command paths" in text
    assert "Operator runtime action paths" in text
    assert "runtime execution modules" in text
    assert "## Compatibility Policy" in text
    assert "preserve execution denial" in text


def test_go_no_go_and_sequence_entry_exist():
    text = _text(CONTRACT)
    assert "## GO / NO-GO" in text
    assert "Final decision: GO" in text
    assert "Next package: Package 149" in text

    entry = _package_148_entry()
    assert "## Package 148" in entry
    assert "Package 148: Runtime Recovery Runtime Bridge Contract" in entry
    assert "python -m pytest tests/test_aer_runtime_recovery_runtime_bridge_contract.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 149" in entry


def test_no_forbidden_runtime_behavior_tokens():
    text = _text(CONTRACT)
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
