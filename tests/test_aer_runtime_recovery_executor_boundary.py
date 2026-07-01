from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_executor_boundary_v1.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_150_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 150")
    end = text.find("## Package 151", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_executor_boundary_contract_exists():
    assert CONTRACT.exists()


def test_required_sections_exist():
    text = _text(CONTRACT)
    for section in (
        "## Executor Boundary Purpose",
        "## Executor Input Schema",
        "## Executor Output Schema",
        "## Required Bridge Reference",
        "## Required Authority Reference",
        "## Required Intent Reference",
        "## Allowed Executor Responsibilities",
        "## Forbidden Executor Responsibilities",
        "## Side-Effect Boundary",
        "## Runtime Mutation Boundary",
        "## Failure Taxonomy",
        "## Dependency Rules",
        "## Compatibility Policy",
        "## GO / NO-GO",
        "## Next Package",
    ):
        assert section in text


def test_executor_input_schema_exists():
    text = _text(CONTRACT)
    assert "aer.runtime.recovery.executor_boundary_input.v1" in text
    for field in (
        "`executor_boundary_id`",
        "`bridge_reference`",
        "`authority_reference`",
        "`intent_reference`",
        "`requested_executor_scope`",
        "`metadata`",
        "`boundary_only`",
    ):
        assert field in text


def test_executor_output_schema_exists():
    text = _text(CONTRACT)
    assert "aer.runtime.recovery.executor_boundary_output.v1" in text
    for field in (
        "`accepted`",
        "`status`",
        "`bridge_reference`",
        "`authority_reference`",
        "`intent_reference`",
        "`allowed_responsibilities`",
        "`denied_responsibilities`",
        "`side_effects_allowed`",
        "`runtime_mutation_allowed`",
        "`executes_recovery`",
        "`boundary_only`",
    ):
        assert field in text
    assert "Boundary acceptance does not implement an executor" in text


def test_required_references_exist():
    text = _text(CONTRACT)
    assert "aer.runtime.recovery.runtime_bridge_response.v1" in text
    assert "aer.runtime.recovery.execution_authority_response.v1" in text
    assert "aer.runtime.recovery.execution_intent_response.v1" in text
    assert "`bridge_only: true`" in text
    assert "`executes_recovery: false`" in text


def test_allowed_and_forbidden_responsibilities_documented():
    text = _text(CONTRACT)
    for allowed in (
        "define future executor input shape",
        "define future executor output shape",
        "describe required bridge reference",
        "describe side-effect denial",
        "prepare future executor package review",
    ):
        assert allowed in text
    for forbidden in (
        "execute Recovery",
        "schedule runtime work",
        "dispatch runtime commands",
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


def test_boundaries_failure_taxonomy_and_compatibility_exist():
    text = _text(CONTRACT)
    assert "## Side-Effect Boundary" in text
    assert "`side_effects_allowed` to `false`" in text
    assert "## Runtime Mutation Boundary" in text
    assert "`runtime_mutation_allowed` to `false`" in text
    assert "## Failure Taxonomy" in text
    assert "`accepted_boundary_only`" in text
    assert "`incompatible_bridge_reference`" in text
    assert "## Compatibility Policy" in text
    assert "real executor remains incompatible" in text


def test_go_no_go_and_sequence_entry_exist():
    text = _text(CONTRACT)
    assert "## GO / NO-GO" in text
    assert "Final decision: GO" in text
    assert "It does not implement executor behavior" in text
    assert "Next package: Package 151" in text

    entry = _package_150_entry()
    assert "## Package 150" in entry
    assert "Package 150: Runtime Recovery Executor Boundary" in entry
    assert "python -m pytest tests/test_aer_runtime_recovery_executor_boundary.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 151" in entry


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
