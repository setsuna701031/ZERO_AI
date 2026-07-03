from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_retry_v1.md")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

PUBLIC_CONTRACT_NAMES = (
    "RecoveryRetry",
    "RecoveryRetryRequest",
    "RecoveryRetryResult",
    "RecoveryRetryFailure",
    "RecoveryRetryPolicy",
    "RecoveryRetryOwnership",
    "RecoveryRetryLifecycle",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_263_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 263")
    end = text.find("## Package 264", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_contract_document_exists():
    assert CONTRACT.exists()


def test_package_263_contract_names_exist():
    text = _text(CONTRACT)
    assert "## Public Contract Names Only" in text
    for name in PUBLIC_CONTRACT_NAMES:
        assert name in text
    assert "No public runtime API is introduced by this package" in text
    assert "No Python runtime module is introduced by this package" in text


def test_required_retry_sections_exist():
    text = _text(CONTRACT)
    for heading in (
        "## Retry Responsibility",
        "## Ownership Boundaries",
        "## Retry Eligibility",
        "## Retry Limits",
        "## Retry Ordering",
        "## Retry Backoff Semantics",
        "## Terminal Failure Rules",
        "## Interaction With RecoveryExecutionPlan",
        "## Interaction With RecoveryExecutor",
        "## Interaction With RecoveryStateTransition",
        "## Interaction With RecoveryCheckpoint",
        "## Interaction With RecoveryRollback",
        "## Failure Taxonomy",
        "## Compatibility Policy",
        "## Dependency Graph",
        "## Future Implementation Ownership",
        "## Forbidden Implementation Behaviors",
    ):
        assert heading in text


def test_retry_rules_are_documented():
    text = _text(CONTRACT)
    for phrase in (
        "retry eligibility is disabled in Package 263",
        "retry must not be eligible after terminal failure",
        "retry_attempt_index must not exceed max_retry_attempts",
        "retry attempts must be ordered deterministically in future data",
        'backoff_status: "reserved"',
        "timer_scheduled: false",
        "terminal failure must stop future retry eligibility",
        "Package 263 does not evaluate retry eligibility at runtime.",
        "Package 263 does not count retry attempts at runtime.",
    ):
        assert phrase in text


def test_retry_interactions_are_contract_only():
    text = _text(CONTRACT)
    assert "Package 263 does not call, import, execute, mutate, or wire RecoveryExecutionPlan implementation." in text
    assert "Package 263 does not call, import, execute, mutate, or wire RecoveryExecutor implementation." in text
    assert "Package 263 does not call, import, execute, mutate, or wire RecoveryStateTransition implementation." in text
    assert "Package 263 does not call, import, execute, mutate, restore, or wire RecoveryCheckpoint implementation." in text
    assert "Package 263 does not call, import, execute, mutate, apply, or wire RecoveryRollback implementation." in text
    assert "RecoveryRetry must not apply rollback." in text


def test_retry_failure_taxonomy_exists():
    text = _text(CONTRACT)
    for failure_code in (
        "recovery_retry_not_implemented",
        "recovery_retry_disabled",
        "retry_request_invalid",
        "retry_not_eligible",
        "retry_limit_exhausted",
        "retry_order_invalid",
        "retry_backoff_forbidden",
        "terminal_failure_reached",
        "rollback_apply_forbidden",
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
        "Package 263 is Contract/documentation only.",
        "Package 263 must not create runtime modules.",
        "Package 263 must not implement retry behavior.",
        "Package 263 must not modify runtime code.",
        "Package 263 must not modify gateway code.",
        "Package 263 must not modify executor code.",
        "Package 263 must not implement state transition behavior.",
        "Package 263 must not implement checkpoint behavior.",
        "Package 263 must not implement rollback behavior.",
        "Package 263 must not wire recovery runtime modules.",
        "Package 263 must not call or import existing recovery bridge, executor, adapter, or integration modules.",
        "Package 263 must not add public runtime APIs.",
        "Package 263 must not add persistence.",
        "Package 263 must not spawn subprocesses.",
        "Package 263 must not perform filesystem mutation.",
        "Package 263 must not invoke endpoints.",
        "Package 263 must not register hooks.",
        "Package 263 must not mutate runtime state.",
    ):
        assert phrase in text


def test_inventory_contains_recovery_retry_contract():
    text = _text(INVENTORY)
    assert "recovery_retry_v1" in text
    assert (
        "| Runtime Recovery Retry | docs/contracts/runtime/recovery_retry_v1.md | "
        "TBD | tests/test_runtime_recovery_retry_contract.py | Missing Implementation | "
        "Package 263 contract/spec + seal only; implementation remains future work |"
    ) in text


def test_package_263_sequence_entry_exists():
    section = _package_263_entry()
    assert "## Package 263" in section
    assert "Package 263: Runtime Recovery Retry Contract" in section
    assert "Contract/documentation only." in section
    assert "Final decision: GO. Next package: Package 264." in section
