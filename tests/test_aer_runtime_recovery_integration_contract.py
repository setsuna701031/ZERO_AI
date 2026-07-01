from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_integration_v1.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_145_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 145")
    end = text.find("## Package 146", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_integration_contract_file_exists():
    assert CONTRACT.exists()


def test_required_sections_exist():
    text = _text(CONTRACT)
    for section in (
        "## Purpose",
        "## Public Contract Surface",
        "## Integration Request Schema",
        "## Integration Response Schema",
        "## Allowed Consumer Roles",
        "## Forbidden Consumer Roles",
        "## Boundary Rules",
        "## Execution Authority Requirement",
        "## Prohibited Direct Integrations",
        "## Failure Taxonomy",
        "## Dependency Rules",
        "## Compatibility Policy",
        "## Contract Evolution Policy",
        "## GO / NO-GO Decision",
        "## Next Package Recommendation",
    ):
        assert section in text


def test_public_contract_surface_exists():
    text = _text(CONTRACT)
    assert "aer.runtime.recovery.integration_request.v1" in text
    assert "aer.runtime.recovery.integration_response.v1" in text
    assert "descriptive only" in text


def test_request_and_response_schemas_exist():
    text = _text(CONTRACT)
    for field in (
        "`request_id`",
        "`consumer_role`",
        "`recovery_plan_contract`",
        "`requested_boundary`",
        "`intent`",
        "`accepted`",
        "`status`",
        "`denied_capabilities`",
        "`execution_authority_required`",
        "`execution_authorized`",
    ):
        assert field in text


def test_execution_authority_requirement_exists():
    text = _text(CONTRACT)
    assert "## Execution Authority Requirement" in text
    assert "Execution authority is absent from this contract" in text
    assert "MUST NOT authorize execution" in text
    assert "future Runtime Recovery Execution Authority package" in text
    assert "`execution_authorized` to `false`" in text


def test_prohibited_direct_integrations_are_documented():
    text = _text(CONTRACT)
    for prohibited in (
        "Scheduler admission or scheduling paths",
        "Dispatcher command paths",
        "Operator action paths",
        "TaskRunner paths",
        "runtime execution loops",
        "persistence write paths",
        "audit emission paths",
        "journal emission paths",
        "replay action paths",
        "subprocess paths",
        "file IO paths",
        "runtime mutation paths",
        "runtime execution modules",
    ):
        assert prohibited in text


def test_compatibility_policy_exists():
    text = _text(CONTRACT)
    assert "## Compatibility Policy" in text
    assert "aer.runtime.recovery.plan.v1" in text
    assert "aer.runtime.recovery.execution_boundary.v1" in text
    assert "Must deny execution and downstream authorization" in text


def test_go_no_go_exists():
    text = _text(CONTRACT)
    assert "## GO / NO-GO Decision" in text
    assert "Final decision: GO" in text
    assert "contract-only package" in text
    assert "Next package: Package 146" in text


def test_package_145_sequence_entry_exists():
    entry = _package_145_entry()
    assert "## Package 145" in entry
    assert "Package 145: Runtime Recovery Integration Contract" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 146" in entry
    assert "MUST NOT authorize execution" in entry


def test_no_forbidden_runtime_behavior_tokens_are_introduced():
    text = _text(CONTRACT)
    for token in (
        "def execute_recovery",
        "class RecoveryExecutor",
        "scheduler.schedule(",
        "dispatcher.dispatch(",
        "operator.apply(",
        "task_runner.run(",
        "subprocess.",
        "open(",
        ".write(",
        "Path(",
    ):
        assert token not in text
