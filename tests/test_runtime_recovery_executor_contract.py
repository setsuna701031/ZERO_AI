from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_executor_v1.md")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

PUBLIC_CONTRACT_NAMES = (
    "RecoveryExecutor",
    "RecoveryExecutorRequest",
    "RecoveryExecutorResult",
    "RecoveryExecutorFailure",
    "RecoveryExecutorOwnership",
    "RecoveryExecutorLifecycle",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_259_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 259")
    end = text.find("## Package 260", start + 1)
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
        "## Executor Responsibility",
        "## Ownership Boundaries",
        "## Execution Input",
        "## Execution Output",
        "## Interaction With RecoveryExecutionPlan",
        "## Execution Lifecycle",
        "## State Ownership",
        "## Failure Taxonomy",
        "## Compatibility Policy",
        "## Dependency Graph",
        "## Future Implementation Ownership",
        "## Forbidden Implementation Behaviors",
    ):
        assert heading in text


def test_forbidden_behaviors_are_explicit():
    text = _text(CONTRACT)
    for phrase in (
        "Package 259 is Contract/documentation only.",
        "Package 259 must not create runtime modules.",
        "Package 259 must not implement an executor.",
        "Package 259 must not modify gateway code.",
        "Package 259 must not wire recovery runtime modules.",
        "Package 259 must not call or import existing recovery bridge, executor, adapter, or integration modules.",
        "Package 259 must not add public runtime APIs.",
        "Package 259 must not add persistence.",
        "Package 259 must not spawn subprocesses.",
        "Package 259 must not perform filesystem mutation.",
        "Package 259 must not invoke endpoints.",
        "Package 259 must not register hooks.",
        "Package 259 must not mutate runtime state.",
    ):
        assert phrase in text


def test_recovery_execution_plan_interaction_is_contract_only():
    text = _text(CONTRACT)
    assert "Interaction With RecoveryExecutionPlan" in text
    assert "Future RecoveryExecutor implementations may consume RecoveryExecutionPlan only after an explicit GO review." in text
    assert "Package 259 does not call, import, execute, or wire RecoveryExecutionPlan implementation." in text
    assert "RecoveryExecutor must not bypass Runtime Recovery Gateway admission." in text
    assert "RecoveryExecutor must not bypass Runtime Authorization." in text


def test_failure_taxonomy_and_compatibility_policy_exist():
    text = _text(CONTRACT)
    for failure_code in (
        "recovery_executor_not_implemented",
        "recovery_executor_disabled",
        "executor_request_invalid",
        "executor_plan_invalid",
        "admission_not_granted",
        "execution_not_allowed",
        "recovery_not_enabled",
        "runtime_wiring_forbidden",
        "runtime_state_mutation_forbidden",
        "persistence_forbidden",
        "subprocess_forbidden",
        "filesystem_mutation_forbidden",
    ):
        assert failure_code in text
    assert "Runtime Recovery Executor Contract v1 is append-only once sealed" in text
    assert "Breaking changes require a new contract version" in text


def test_dependency_graph_bans_runtime_wiring_and_recovery_runtime_imports():
    text = _text(CONTRACT)
    assert "Runtime Recovery Execution Plan Contract v1" in text
    assert "Future Runtime Recovery Executor Implementation after GO review" in text
    for forbidden_dependency in (
        "recovery bridge",
        "recovery executor implementation",
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
        "endpoint invocation",
        "hook registration",
        "bridge calls",
        "subprocess",
        "filesystem mutation",
    ):
        assert forbidden_dependency in text
    assert "The contract must not call or import existing recovery bridge, executor, adapter, or integration modules." in text


def test_inventory_contains_recovery_executor_contract():
    text = _text(INVENTORY)
    assert (
        "| Runtime Recovery Executor | docs/contracts/runtime/recovery_executor_v1.md | "
        "TBD | tests/test_runtime_recovery_executor_contract.py | Missing Implementation | "
        "Package 259 contract/spec + seal only; implementation remains future work |"
    ) in text


def test_package_259_sequence_entry_exists():
    section = _package_259_entry()
    assert "## Package 259" in section
    assert "Package 259: Runtime Recovery Executor Contract" in section
    assert "Contract/documentation only." in section
    assert "Final decision: GO. Next package: Package 260." in section
