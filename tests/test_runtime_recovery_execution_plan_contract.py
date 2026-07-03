from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_execution_plan_v1.md")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

PUBLIC_CONTRACT_NAMES = (
    "RecoveryExecutionPlan",
    "RecoveryExecutionStage",
    "RecoveryExecutionUnit",
    "RecoveryExecutionCheckpoint",
    "RecoveryExecutionRollbackPolicy",
    "RecoveryExecutionRetryPolicy",
    "RecoveryExecutionPlanFailure",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_258_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 258")
    end = text.find("## Package 259", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_contract_document_exists():
    assert CONTRACT.exists()


def test_public_contract_names_exist():
    text = _text(CONTRACT)
    assert "## Public Contract Names Only" in text
    for name in PUBLIC_CONTRACT_NAMES:
        assert name in text
    assert "No public runtime API is introduced by this package" in text
    assert "No Python runtime module is introduced by this package" in text


def test_required_contract_sections_exist():
    text = _text(CONTRACT)
    for heading in (
        "## Purpose",
        "## Ownership",
        "## Lifecycle",
        "## Plan Input Boundaries",
        "## Plan Output Boundaries",
        "## Stage Ordering",
        "## Execution Unit Rules",
        "## Checkpoint Rules",
        "## Rollback Semantics",
        "## Retry Policy",
        "## Failure Taxonomy",
        "## Compatibility Policy",
        "## Dependency Graph",
        "## Future Executor Ownership",
        "## Forbidden Implementation Behaviors",
    ):
        assert heading in text


def test_forbidden_implementation_behaviors_are_explicit():
    text = _text(CONTRACT)
    for phrase in (
        "Package 258 must not execute recovery",
        "Package 258 must not create runtime modules",
        "Package 258 must not modify gateway code",
        "Package 258 must not modify executor code",
        "Package 258 must not call or import existing recovery bridge, executor, adapter, or integration modules",
        "Package 258 must not add public runtime APIs",
        "Package 258 must not mutate runtime state",
        "Package 258 must not add persistence, subprocess, filesystem mutation, endpoint invocation, hooks, or bridge calls",
    ):
        assert phrase in text


def test_stage_ordering_and_rules_are_reserved_only():
    text = _text(CONTRACT)
    for stage in (
        "validate_gateway_denial",
        "validate_policy_stub",
        "validate_authorization_stub",
        "validate_execution_stub",
        "prepare_future_execution_units",
        "prepare_future_checkpoints",
        "prepare_future_rollback_policy",
        "prepare_future_retry_policy",
    ):
        assert stage in text
    assert "Package 258 does not execute stages" in text
    assert "execution units must not execute recovery" in text
    assert "checkpoints must not write files" in text
    assert "Package 258 does not implement rollback" in text
    assert "Package 258 does not implement retry" in text


def test_failure_taxonomy_and_compatibility_policy_exist():
    text = _text(CONTRACT)
    for failure_code in (
        "recovery_execution_plan_not_implemented",
        "recovery_execution_plan_disabled",
        "stage_order_invalid",
        "execution_unit_forbidden",
        "checkpoint_forbidden",
        "rollback_forbidden",
        "retry_forbidden",
        "runtime_wiring_forbidden",
        "runtime_mutation_forbidden",
        "filesystem_mutation_forbidden",
        "subprocess_forbidden",
    ):
        assert failure_code in text
    assert "Runtime Recovery Execution Plan Contract v1 is append-only once sealed" in text
    assert "Breaking changes require a new contract version" in text


def test_dependency_graph_bans_runtime_wiring_and_recovery_runtime_imports():
    text = _text(CONTRACT)
    assert "Runtime Recovery Gateway" in text
    assert "Future Runtime Recovery Executor after GO review" in text
    for forbidden_dependency in (
        "recovery bridge",
        "recovery executor",
        "recovery adapter",
        "recovery integration",
        "planner",
        "scheduler",
        "TaskRunner",
        "operator",
        "dispatcher",
        "supervisor",
        "native runtime",
        "watchdog",
        "persistence",
        "audit",
        "journal",
        "subprocess",
        "filesystem mutation",
    ):
        assert forbidden_dependency in text
    assert "The contract must not call or import existing recovery bridge, executor, adapter, or integration modules." in text


def test_inventory_contains_recovery_execution_plan_contract():
    text = _text(INVENTORY)
    assert (
        "| Runtime Recovery Execution Plan | docs/contracts/runtime/recovery_execution_plan_v1.md | "
        "TBD | tests/test_runtime_recovery_execution_plan_contract.py | Missing Implementation | "
        "Package 258 contract/spec + seal only; implementation remains future work |"
    ) in text


def test_package_258_sequence_entry_exists():
    section = _package_258_entry()
    assert "Package 258: Runtime Recovery Execution Plan Contract" in section
    assert "Contract/documentation only" in section
    assert "No runtime implementation" in section
    assert "No gateway changes" in section
    assert "No executor changes" in section
    assert "Final decision: GO. Next package: Package 259." in section
