from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_execution_v1.md")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_257_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 257")
    end = text.find("## Package 258", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_contract_document_exists():
    assert CONTRACT.exists()


def test_public_contract_names_only():
    text = _text(CONTRACT)
    assert "## Public Contract Names Only" in text
    for name in (
        "RecoveryExecutionRequest",
        "RecoveryExecutionResult",
        "RecoveryExecutionFailure",
    ):
        assert name in text
    assert "No public API function is introduced by this package" in text
    assert "No Python module is introduced by this package" in text


def test_required_contract_sections_exist():
    text = _text(CONTRACT)
    for heading in (
        "## RecoveryExecutionRequest",
        "## RecoveryExecutionResult",
        "## RecoveryExecutionFailure",
        "## Ownership",
        "## Lifecycle",
        "## Failure Taxonomy",
        "## Compatibility Policy",
        "## Boundary Rules",
        "## Dependency Graph",
        "## Future Implementation Ownership",
    ):
        assert heading in text


def test_contract_only_runtime_forbidden_rules_are_explicit():
    text = _text(CONTRACT)
    for phrase in (
        "There is no runtime execution yet",
        "Implementation is forbidden in this package",
        "no runtime execution yet",
        "contract only",
        "implementation forbidden in this package",
        "no planner wiring",
        "no scheduler wiring",
        "no operator wiring",
        "no supervisor wiring",
        "no persistence",
        "no subprocess",
        "no filesystem mutation",
        "no runtime mutation",
    ):
        assert phrase in text


def test_failure_taxonomy_and_compatibility_policy_are_sealed():
    text = _text(CONTRACT)
    for failure_code in (
        "recovery_execution_not_implemented",
        "recovery_execution_disabled",
        "admission_not_granted",
        "execution_not_allowed",
        "authorization_not_granted",
        "runtime_wiring_forbidden",
        "runtime_mutation_forbidden",
        "filesystem_mutation_forbidden",
        "subprocess_forbidden",
    ):
        assert failure_code in text
    assert "Runtime Recovery Execution Contract v1 is append-only once sealed" in text
    assert "Breaking changes require a new contract version" in text


def test_dependency_graph_does_not_authorize_runtime_wiring():
    text = _text(CONTRACT)
    assert "Runtime Recovery Gateway" in text
    assert "Future Runtime Recovery Execution Implementation" in text
    for forbidden_dependency in (
        "Scheduler",
        "TaskRunner",
        "Operator",
        "Dispatcher",
        "Supervisor",
        "Native Runtime",
        "Watchdog",
        "Persistence",
        "Audit",
        "Journal",
    ):
        assert forbidden_dependency in text
    assert "The contract must not import or wire runtime modules." in text


def test_inventory_contains_recovery_execution_contract():
    text = _text(INVENTORY)
    assert (
        "| Runtime Recovery Execution | docs/contracts/runtime/recovery_execution_v1.md | "
        "TBD | tests/test_runtime_recovery_execution_contract.py | Missing Implementation | "
        "Package 257 contract/spec + seal only; implementation remains future work |"
    ) in text


def test_package_257_sequence_entry_exists():
    section = _package_257_entry()
    assert "Package 257: Runtime Recovery Execution Contract v1" in section
    assert "Contract/documentation only" in section
    assert "No runtime behavior" in section
    assert "No gateway behavior changes" in section
    assert "No new public APIs" in section
    assert "No imports or runtime wiring" in section
    assert "Final decision: GO." in section
    assert "Next package: Package 258." in section
