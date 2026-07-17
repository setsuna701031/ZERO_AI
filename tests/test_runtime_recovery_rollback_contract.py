from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_rollback_v1.md")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

PUBLIC_CONTRACT_NAMES = (
    "RecoveryRollback",
    "RecoveryRollbackRequest",
    "RecoveryRollbackResult",
    "RecoveryRollbackFailure",
    "RecoveryRollbackPolicy",
    "RecoveryRollbackOwnership",
    "RecoveryRollbackLifecycle",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_262_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 262")
    end = text.find("## Package 263", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_contract_document_exists():
    assert CONTRACT.exists()


def test_package_262_contract_names_exist():
    text = _text(CONTRACT)
    assert "## Public Contract Names Only" in text
    for name in PUBLIC_CONTRACT_NAMES:
        assert name in text
    assert "No public runtime API is introduced by this package" in text
    assert "No Python runtime module is introduced by this package" in text


def test_required_rollback_sections_exist():
    text = _text(CONTRACT)
    for heading in (
        "## Rollback Responsibility",
        "## Ownership Boundaries",
        "## Rollback Eligibility",
        "## Rollback Target Rules",
        "## Rollback Safety Rules",
        "## Checkpoint Dependency",
        "## Interaction With RecoveryExecutionPlan",
        "## Interaction With RecoveryExecutor",
        "## Interaction With RecoveryStateTransition",
        "## Interaction With RecoveryCheckpoint",
        "## Failure Taxonomy",
        "## Compatibility Policy",
        "## Dependency Graph",
        "## Future Implementation Ownership",
        "## Forbidden Implementation Behaviors",
    ):
        assert heading in text


def test_rollback_rules_are_documented():
    text = _text(CONTRACT)
    for phrase in (
        "rollback eligibility is disabled in Package 262",
        "rollback requires an eligible RecoveryCheckpoint reference",
        "rollback_target_checkpoint_id must refer to RecoveryCheckpoint contract data.",
        "rollback targets must not imply checkpoint restore authority.",
        "RecoveryRollback must not restore runtime state.",
        "RecoveryRollback must not override RecoveryStateTransition forbidden transitions.",
        "Package 262 does not evaluate rollback eligibility at runtime.",
        "Package 262 does not select or apply rollback targets at runtime.",
    ):
        assert phrase in text


def test_rollback_interactions_are_contract_only():
    text = _text(CONTRACT)
    assert "Package 262 does not call, import, execute, mutate, or wire RecoveryExecutionPlan implementation." in text
    assert "Package 262 does not call, import, execute, mutate, or wire RecoveryExecutor implementation." in text
    assert "Package 262 does not call, import, execute, mutate, or wire RecoveryStateTransition implementation." in text
    assert "Package 262 does not call, import, execute, mutate, restore, or wire RecoveryCheckpoint implementation." in text
    assert "RecoveryRollback must not apply state transitions." in text
    assert "RecoveryRollback must not restore checkpoints at runtime in Package 262." in text


def test_rollback_failure_taxonomy_exists():
    text = _text(CONTRACT)
    for failure_code in (
        "recovery_rollback_not_implemented",
        "recovery_rollback_disabled",
        "rollback_request_invalid",
        "rollback_not_eligible",
        "rollback_target_invalid",
        "rollback_safety_violation",
        "checkpoint_dependency_invalid",
        "checkpoint_restore_forbidden",
        "runtime_wiring_forbidden",
        "runtime_state_mutation_forbidden",
        "persistence_forbidden",
        "subprocess_forbidden",
        "filesystem_mutation_forbidden",
    ):
        assert failure_code in text


def test_forbidden_runtime_behaviors_are_explicit():
    text = _text(CONTRACT)
    for phrase in (
        "Package 262 is Contract/documentation only.",
        "Package 262 must not create runtime modules.",
        "Package 262 must not implement rollback behavior.",
        "Package 262 must not modify runtime code.",
        "Package 262 must not modify gateway code.",
        "Package 262 must not modify executor code.",
        "Package 262 must not implement state transition behavior.",
        "Package 262 must not implement checkpoint behavior.",
        "Package 262 must not wire recovery runtime modules.",
        "Package 262 must not call or import existing recovery bridge, executor, adapter, or integration modules.",
        "Package 262 must not add public runtime APIs.",
        "Package 262 must not add persistence.",
        "Package 262 must not spawn subprocesses.",
        "Package 262 must not perform filesystem mutation.",
        "Package 262 must not invoke endpoints.",
        "Package 262 must not register hooks.",
        "Package 262 must not mutate runtime state.",
    ):
        assert phrase in text


def test_inventory_contains_recovery_rollback_contract():
    text = _text(INVENTORY)
    assert "recovery_rollback_v1" in text
    assert (
        "| Runtime Recovery Rollback | docs/contracts/runtime/recovery_rollback_v1.md | "
        "TBD | tests/test_runtime_recovery_rollback_contract.py | Missing Implementation | "
        "Package 262 contract/spec + seal only; implementation remains future work |"
    ) in text


def test_package_262_sequence_entry_exists():
    section = _package_262_entry()
    assert "## Package 262" in section
    assert "Package 262: Runtime Recovery Rollback Contract" in section
    assert "Contract/documentation only." in section
    assert "Final decision: GO. Next package: Package 263." in section
