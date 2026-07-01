from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_v1.md")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
RECOVERY_IMPLEMENTATION = Path("core/runtime/aer_runtime_recovery.py")

FORBIDDEN_IMPLEMENTATION_TOKENS = (
    "recover(",
    "schedule(",
    "dispatch(",
    "operate(",
    "persist(",
    "audit(",
    "journal(",
    "subprocess",
    "open(",
    "write(",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _package_139_entry() -> str:
    text = _text(PACKAGE_SEQUENCE)
    start = text.index("## Package 139")
    end = text.find("## Package 140", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_contract_document_exists():
    assert CONTRACT.exists()


def test_public_schemas_exist():
    text = _text(CONTRACT)
    for schema in (
        "aer.runtime.recovery.eligibility.v1",
        "aer.runtime.recovery.plan.v1",
        "aer.runtime.recovery.execution_boundary.v1",
    ):
        assert schema in text
    assert "These three public contracts must never collapse into a single API" in text


def test_contract_evolution_policy_exists():
    text = _text(CONTRACT)
    assert "## Contract Evolution Policy" in text
    assert "Recovery v1 schemas are immutable once sealed" in text
    assert "Breaking changes must create a new contract version" in text
    assert "Old versions must not be silently overwritten" in text
    assert "recovery_v1" in text
    assert "recovery_v2" in text
    for forbidden_change in (
        "changing v1 field meaning",
        "removing v1 fields",
        "renaming v1 fields",
        "changing v1 schemas",
        "changing v1 summary semantics in place",
    ):
        assert forbidden_change in text


def test_public_api_names_are_contract_only():
    text = _text(CONTRACT)
    for api in (
        "check_recovery_eligibility(...)",
        "validate_recovery_eligibility(...)",
        "build_recovery_plan(...)",
        "validate_recovery_plan(...)",
        "recovery_eligibility_to_summary(...)",
        "recovery_plan_to_summary(...)",
    ):
        assert api in text
    assert "No implementation is provided by Package 139" in text


def test_ownership_exists():
    text = _text(CONTRACT)
    assert "## Ownership" in text
    for owned in (
        "recovery eligibility",
        "recovery planning",
        "recovery failure taxonomy",
        "recovery public summaries",
    ):
        assert owned in text
    for not_owned in (
        "execution",
        "scheduling",
        "dispatch",
        "operator approval",
        "persistence",
        "audit",
        "journal",
        "replay",
    ):
        assert not_owned in text


def test_boundary_exists():
    text = _text(CONTRACT)
    assert "## Boundary" in text
    assert "Runtime Resume Execution Consumer public output" in text
    assert "Resume Builder internals" in text
    assert "Resume Planning internals" in text
    assert "Resume Validation internals" in text
    assert "Recovery must not bypass the Runtime Resume Execution Consumer boundary" in text


def test_boundary_matrix_exists():
    text = _text(CONTRACT)
    assert "## Boundary Matrix" in text
    assert "| Domain | Direction | Allowed | Forbidden |" in text
    for domain in (
        "Runtime Resume Execution Consumer",
        "Resume Builder",
        "Resume Planning",
        "Resume Validation",
        "Runtime Recovery",
        "Scheduler",
        "Dispatcher",
        "Operator",
        "Persistence",
        "Audit",
        "Journal",
        "Replay",
    ):
        assert f"| {domain} |" in text


def test_contract_compatibility_matrix_exists():
    text = _text(CONTRACT)
    assert "## Contract Compatibility Matrix" in text
    assert "| Producer | Consumer | Compatible |" in text
    for row in (
        "| Resume Execution Consumer v1 | Recovery v1 | Yes |",
        "| Resume Execution Consumer v2 | Recovery v1 | TBD |",
        "| Recovery v1 | Scheduler v1 | Future |",
        "| Recovery v1 | Persistence v1 | Future |",
        "| Recovery v1 | Audit v1 | Future |",
        "| Recovery v1 | Journal v1 | Future |",
    ):
        assert row in text
    assert "Compatibility entries marked TBD or Future do not authorize consumption" in text


def test_failure_taxonomy_exists():
    text = _text(CONTRACT)
    assert "## Failure Taxonomy" in text
    for failure in (
        "invalid_execution_summary",
        "invalid_recovery_request",
        "recovery_not_authorized",
        "scheduler_required",
        "operator_required",
        "persistence_required",
        "audit_required",
        "journal_required",
    ):
        assert failure in text


def test_dependency_graph_exists():
    text = _text(CONTRACT)
    assert "## Dependency Graph" in text
    for node in (
        "Resume Execution Consumer",
        "Recovery",
        "Future Scheduler",
        "Future Persistence",
        "Future Audit",
        "Future Journal",
    ):
        assert node in text
    assert "Recovery may not reverse-import upstream internals" in text


def test_lifecycle_reference_exists():
    text = _text(CONTRACT)
    assert "AER Domain Lifecycle Standard" in text
    assert "Package 139 is the Contract phase" in text


def test_go_decision_and_package_140_exist():
    text = _text(CONTRACT)
    assert "Final decision: GO" in text
    assert "Next package: Package 140: Runtime Recovery Validation" in text


def test_inventory_contains_recovery_contract():
    text = _text(INVENTORY)
    assert "| Recovery | docs/contracts/runtime/recovery_v1.md | TBD | tests/test_aer_runtime_recovery_contract.py | Missing Implementation | Package 139 contract/spec + seal only; implementation remains future work |" in text


def test_package_sequence_contains_package_139_and_package_140_next():
    entry = _package_139_entry()
    assert "## Package 139" in entry
    assert "Package 139: Runtime Recovery Contract" in entry
    assert "contract-only" in entry
    assert "AER Domain Lifecycle Standard" in entry
    assert "Contract Evolution Policy" in entry
    assert "Contract Compatibility Matrix" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 140: Runtime Recovery Validation" in entry


def test_no_recovery_implementation_file_is_added_or_referenced_as_modified():
    text = _text(CONTRACT)
    entry = _package_139_entry()
    inventory = _text(INVENTORY)
    assert not RECOVERY_IMPLEMENTATION.exists()
    assert "core/runtime/aer_runtime_recovery.py" not in text
    assert "core/runtime/aer_runtime_recovery.py" not in entry
    assert "core/runtime/aer_runtime_recovery.py" not in inventory
    assert "modify core runtime modules" in text


def test_forbidden_implementation_tokens_remain_absent():
    combined = "\n".join((_text(CONTRACT), _package_139_entry()))
    for token in FORBIDDEN_IMPLEMENTATION_TOKENS:
        assert token not in combined
