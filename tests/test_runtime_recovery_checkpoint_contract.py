from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_checkpoint_v1.md")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

PUBLIC_CONTRACT_NAMES = (
    "RecoveryCheckpoint",
    "RecoveryCheckpointRequest",
    "RecoveryCheckpointResult",
    "RecoveryCheckpointFailure",
    "RecoveryCheckpointPolicy",
    "RecoveryCheckpointOwnership",
    "RecoveryCheckpointLifecycle",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_261_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 261")
    end = text.find("## Package 262", start + 1)
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
        "## Checkpoint Responsibility",
        "## Ownership Boundaries",
        "## Checkpoint Creation Rules",
        "## Checkpoint Validation Rules",
        "## Checkpoint Identity Fields",
        "## Checkpoint Lineage Rules",
        "## Checkpoint Restore Boundaries",
        "## Interaction With RecoveryExecutionPlan",
        "## Interaction With RecoveryExecutor",
        "## Interaction With RecoveryStateTransition",
        "## Lifecycle",
        "## Failure Taxonomy",
        "## Compatibility Policy",
        "## Dependency Graph",
        "## Future Implementation Ownership",
        "## Forbidden Implementation Behaviors",
    ):
        assert heading in text


def test_checkpoint_identity_fields_are_documented():
    text = _text(CONTRACT)
    assert "RecoveryCheckpoint reserves these identity fields for future checkpoint data:" in text
    for field in (
        'contract_name: "RecoveryCheckpoint"',
        'contract_version: "v1"',
        "checkpoint_id",
        "checkpoint_request_id",
        "recovery_execution_plan_id",
        "executor_request_id",
        "state_transition_request_id",
        "checkpoint_policy_name",
        "checkpoint_sequence",
        "created_for_state",
    ):
        assert field in text
    assert "Package 261 does not allocate checkpoint identifiers and does not persist checkpoint identity." in text


def test_checkpoint_lineage_rules_are_documented():
    text = _text(CONTRACT)
    for phrase in (
        "checkpoint_id must identify one future checkpoint record.",
        "checkpoint_request_id must identify the future request that asked for checkpoint description.",
        "recovery_execution_plan_id must remain a reference to RecoveryExecutionPlan contract data.",
        "executor_request_id must remain a reference to RecoveryExecutor contract data when present.",
        "state_transition_request_id must remain a reference to RecoveryStateTransition contract data when present.",
        "parent_checkpoint_id may be absent only for an initial future checkpoint.",
        "parent_checkpoint_id must not imply restore authority.",
        "checkpoint_sequence must be deterministic within a future checkpoint lineage.",
        "checkpoint lineage must not cross recovery operation boundaries without a future explicit GO-reviewed lineage migration contract.",
    ):
        assert phrase in text
    assert "Package 261 does not construct, store, migrate, or verify checkpoint lineage at runtime." in text


def test_checkpoint_restore_boundaries_are_documented():
    text = _text(CONTRACT)
    for phrase in (
        "RecoveryCheckpoint does not authorize restore behavior in Package 261.",
        "RecoveryCheckpoint must not restore runtime state.",
        "RecoveryCheckpoint must not roll back runtime state.",
        "RecoveryCheckpoint must not replay runtime events.",
        "RecoveryCheckpoint must not write checkpoint data to persistence.",
        "RecoveryCheckpoint must not read checkpoint data from persistence.",
        "RecoveryCheckpoint must not invoke endpoints during restore.",
        "RecoveryCheckpoint must not register hooks during restore.",
        "RecoveryCheckpoint must not call bridges during restore.",
        "RecoveryCheckpoint must not spawn subprocesses during restore.",
        "RecoveryCheckpoint must not perform filesystem mutation during restore.",
        "Future restore behavior requires a separate explicit GO-reviewed implementation package.",
    ):
        assert phrase in text
    assert "Package 261 does not implement restore behavior." in text


def test_checkpoint_creation_and_validation_rules_are_contract_only():
    text = _text(CONTRACT)
    assert "checkpoint creation is disabled in Package 261" in text
    assert "checkpoint creation must not persist checkpoint data" in text
    assert "Package 261 does not create checkpoints at runtime." in text
    assert "checkpoint identity fields must be present in future checkpoint data" in text
    assert "checkpoint lineage fields must be present in future checkpoint data" in text
    assert "checkpoint restore boundaries must be explicit in future checkpoint data" in text
    assert "Package 261 does not validate checkpoints at runtime." in text


def test_plan_executor_and_state_transition_interactions_are_contract_only():
    text = _text(CONTRACT)
    assert "Future RecoveryCheckpoint implementations may reference RecoveryExecutionPlan data only after an explicit GO review." in text
    assert "Package 261 does not call, import, execute, mutate, or wire RecoveryExecutionPlan implementation." in text
    assert "Future RecoveryCheckpoint implementations may reference RecoveryExecutor data only after an explicit GO review." in text
    assert "Package 261 does not call, import, execute, mutate, or wire RecoveryExecutor implementation." in text
    assert "Future RecoveryCheckpoint implementations may reference RecoveryStateTransition data only after an explicit GO review." in text
    assert "Package 261 does not call, import, execute, mutate, or wire RecoveryStateTransition implementation." in text
    assert "RecoveryCheckpoint must not apply state transitions." in text
    assert "RecoveryCheckpoint must not override forbidden state transitions." in text


def test_failure_taxonomy_and_compatibility_policy_exist():
    text = _text(CONTRACT)
    for failure_code in (
        "recovery_checkpoint_not_implemented",
        "recovery_checkpoint_disabled",
        "checkpoint_request_invalid",
        "checkpoint_identity_invalid",
        "checkpoint_lineage_invalid",
        "checkpoint_policy_invalid",
        "checkpoint_creation_forbidden",
        "checkpoint_validation_forbidden",
        "checkpoint_restore_forbidden",
        "recovery_execution_plan_reference_invalid",
        "recovery_executor_reference_invalid",
        "recovery_state_transition_reference_invalid",
        "runtime_wiring_forbidden",
        "runtime_state_mutation_forbidden",
        "persistence_forbidden",
        "subprocess_forbidden",
        "filesystem_mutation_forbidden",
    ):
        assert failure_code in text
    assert "Runtime Recovery Checkpoint Contract v1 is append-only once sealed" in text
    assert "Breaking changes require a new contract version" in text


def test_forbidden_behaviors_are_explicit():
    text = _text(CONTRACT)
    for phrase in (
        "Package 261 is Contract/documentation only.",
        "Package 261 must not create runtime modules.",
        "Package 261 must not implement checkpoint behavior.",
        "Package 261 must not modify gateway code.",
        "Package 261 must not modify executor code.",
        "Package 261 must not implement state transition behavior.",
        "Package 261 must not wire recovery runtime modules.",
        "Package 261 must not call or import existing recovery bridge, executor, adapter, or integration modules.",
        "Package 261 must not add public runtime APIs.",
        "Package 261 must not add persistence.",
        "Package 261 must not spawn subprocesses.",
        "Package 261 must not perform filesystem mutation.",
        "Package 261 must not invoke endpoints.",
        "Package 261 must not register hooks.",
        "Package 261 must not mutate runtime state.",
    ):
        assert phrase in text


def test_dependency_graph_bans_runtime_wiring_and_recovery_runtime_imports():
    text = _text(CONTRACT)
    assert "Runtime Recovery Execution Plan Contract v1" in text
    assert "Runtime Recovery Executor Contract v1" in text
    assert "Runtime Recovery State Transition Contract v1" in text
    assert "Future Runtime Recovery Checkpoint Implementation after GO review" in text
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


def test_inventory_contains_recovery_checkpoint_contract():
    text = _text(INVENTORY)
    assert "recovery_checkpoint_v1" in text
    assert (
        "| Runtime Recovery Checkpoint | docs/contracts/runtime/recovery_checkpoint_v1.md | "
        "TBD | tests/test_runtime_recovery_checkpoint_contract.py | Missing Implementation | "
        "Package 261 contract/spec + seal only; implementation remains future work |"
    ) in text


def test_package_261_sequence_entry_exists():
    section = _package_261_entry()
    assert "## Package 261" in section
    assert "Package 261: Runtime Recovery Checkpoint Contract" in section
    assert "Contract/documentation only." in section
    assert "Final decision: GO. Next package: Package 262." in section
