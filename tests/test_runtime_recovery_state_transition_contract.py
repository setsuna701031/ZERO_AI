from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_state_transition_v1.md")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

PUBLIC_CONTRACT_NAMES = (
    "RecoveryStateTransition",
    "RecoveryStateTransitionRequest",
    "RecoveryStateTransitionResult",
    "RecoveryStateTransitionFailure",
    "RecoveryStateTransitionPolicy",
    "RecoveryStateTransitionOwnership",
    "RecoveryStateTransitionLifecycle",
)

ALLOWED_STATES = (
    "recovery_unrequested",
    "recovery_requested",
    "recovery_denied",
    "recovery_admitted",
    "recovery_plan_reserved",
    "recovery_plan_ready",
    "recovery_execution_reserved",
    "recovery_executor_ready",
    "recovery_running_future_only",
    "recovery_succeeded_future_only",
    "recovery_failed_future_only",
    "recovery_cancelled",
    "recovery_blocked",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_260_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 260")
    end = text.find("## Package 261", start + 1)
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
        "## Transition Responsibility",
        "## Ownership Boundaries",
        "## Allowed Recovery States",
        "## Forbidden State Transitions",
        "## Transition Input",
        "## Transition Output",
        "## Interaction With RecoveryExecutionPlan",
        "## Interaction With RecoveryExecutor",
        "## Transition Lifecycle",
        "## Failure Taxonomy",
        "## Compatibility Policy",
        "## Dependency Graph",
        "## Future Implementation Ownership",
        "## Forbidden Implementation Behaviors",
    ):
        assert heading in text


def test_allowed_recovery_states_are_documented():
    text = _text(CONTRACT)
    assert "RecoveryStateTransitionPolicy reserves these allowed recovery states:" in text
    for state in ALLOWED_STATES:
        assert state in text
    assert "Package 260 does not create, persist, read, write, or mutate any runtime state." in text


def test_forbidden_state_transitions_are_documented():
    text = _text(CONTRACT)
    for phrase in (
        "recovery_unrequested must not transition directly to recovery_running_future_only.",
        "recovery_requested must not transition directly to recovery_execution_reserved.",
        "recovery_denied must not transition to recovery_admitted.",
        "recovery_plan_reserved must not transition directly to recovery_running_future_only.",
        "recovery_succeeded_future_only must not transition to recovery_failed_future_only.",
        "recovery_failed_future_only must not transition to recovery_running_future_only.",
        "recovery_cancelled must not transition to recovery_running_future_only.",
        "recovery_blocked must not transition to recovery_running_future_only without a future explicit GO-reviewed unblock contract.",
    ):
        assert phrase in text
    assert "Package 260 does not enforce transitions at runtime." in text


def test_transition_input_and_output_are_contract_only():
    text = _text(CONTRACT)
    for field in (
        'contract_name: "RecoveryStateTransitionRequest"',
        'contract_version: "v1"',
        "transition_request_id",
        "source_state",
        "target_state",
        'contract_name: "RecoveryStateTransitionResult"',
        "transition_allowed",
        "transition_applied",
        "runtime_state_mutated",
    ):
        assert field in text
    assert "Package 260 does not construct or consume RecoveryStateTransitionRequest at runtime." in text
    assert "Package 260 does not produce RecoveryStateTransitionResult at runtime." in text


def test_plan_and_executor_interactions_are_contract_only():
    text = _text(CONTRACT)
    assert "Future RecoveryStateTransition implementations may reference RecoveryExecutionPlan data only after an explicit GO review." in text
    assert "Package 260 does not call, import, execute, mutate, or wire RecoveryExecutionPlan implementation." in text
    assert "RecoveryStateTransition must not create a RecoveryExecutionPlan." in text
    assert "Future RecoveryStateTransition implementations may reference RecoveryExecutor data only after an explicit GO review." in text
    assert "Package 260 does not call, import, execute, mutate, or wire RecoveryExecutor implementation." in text
    assert "RecoveryStateTransition must not start RecoveryExecutor." in text
    assert "RecoveryStateTransition must not mutate executor state." in text


def test_failure_taxonomy_and_compatibility_policy_exist():
    text = _text(CONTRACT)
    for failure_code in (
        "recovery_state_transition_not_implemented",
        "recovery_state_transition_disabled",
        "transition_request_invalid",
        "source_state_invalid",
        "target_state_invalid",
        "transition_forbidden",
        "transition_policy_invalid",
        "recovery_execution_plan_reference_invalid",
        "recovery_executor_reference_invalid",
        "runtime_wiring_forbidden",
        "runtime_state_mutation_forbidden",
        "persistence_forbidden",
        "subprocess_forbidden",
        "filesystem_mutation_forbidden",
    ):
        assert failure_code in text
    assert "Runtime Recovery State Transition Contract v1 is append-only once sealed" in text
    assert "Breaking changes require a new contract version" in text


def test_forbidden_behaviors_are_explicit():
    text = _text(CONTRACT)
    for phrase in (
        "Package 260 is Contract/documentation only.",
        "Package 260 must not create runtime modules.",
        "Package 260 must not implement state transition behavior.",
        "Package 260 must not modify gateway code.",
        "Package 260 must not modify executor code.",
        "Package 260 must not wire recovery runtime modules.",
        "Package 260 must not call or import existing recovery bridge, executor, adapter, or integration modules.",
        "Package 260 must not add public runtime APIs.",
        "Package 260 must not add persistence.",
        "Package 260 must not spawn subprocesses.",
        "Package 260 must not perform filesystem mutation.",
        "Package 260 must not invoke endpoints.",
        "Package 260 must not register hooks.",
        "Package 260 must not mutate runtime state.",
    ):
        assert phrase in text


def test_dependency_graph_bans_runtime_wiring_and_recovery_runtime_imports():
    text = _text(CONTRACT)
    assert "Runtime Recovery Execution Plan Contract v1" in text
    assert "Runtime Recovery Executor Contract v1" in text
    assert "Future Runtime Recovery State Transition Implementation after GO review" in text
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
        "runtime state mutation",
    ):
        assert forbidden_dependency in text
    assert "The contract must not call or import existing recovery bridge, executor, adapter, or integration modules." in text


def test_inventory_contains_recovery_state_transition_contract():
    text = _text(INVENTORY)
    assert "recovery_state_transition_v1" in text
    assert (
        "| Runtime Recovery State Transition | docs/contracts/runtime/recovery_state_transition_v1.md | "
        "TBD | tests/test_runtime_recovery_state_transition_contract.py | Missing Implementation | "
        "Package 260 contract/spec + seal only; implementation remains future work |"
    ) in text


def test_package_260_sequence_entry_exists():
    section = _package_260_entry()
    assert "## Package 260" in section
    assert "Package 260: Runtime Recovery State Transition Contract" in section
    assert "Contract/documentation only." in section
    assert "Final decision: GO. Next package: Package 261." in section
