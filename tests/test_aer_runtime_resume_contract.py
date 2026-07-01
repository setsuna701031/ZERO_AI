from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/resume_v1.md")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def test_runtime_resume_contract_exists_and_defines_schema_names():
    assert CONTRACT.exists()

    text = CONTRACT.read_text(encoding="utf-8")

    for token in (
        "AER Runtime Resume Contract v1",
        "aer.runtime.resume.eligibility.v1",
        "aer.runtime.resume.plan.v1",
        "aer.runtime.resume.execution_boundary.v1",
        "Schema Names",
        "contract/spec + seal only",
    ):
        assert token in text


def test_resume_responsibilities_are_separate_and_never_collapsed():
    text = CONTRACT.read_text(encoding="utf-8")

    for token in (
        "Resume Eligibility",
        "Resume Planning",
        "Resume Execution Boundary",
        "must never collapse into one public API",
        "Eligibility decides only",
        "Planning plans only",
        "Execution is future-domain only",
        "execution must not be hidden inside eligibility or planning",
    ):
        assert token in text


def test_upstream_downstream_boundaries_and_boundary_matrix_are_explicit():
    text = CONTRACT.read_text(encoding="utf-8")

    for token in (
        "Upstream Boundary",
        "Downstream Boundary",
        "Boundary Matrix",
        "| Domain | Direction | Allowed | Forbidden |",
        "consumes only Runtime Snapshot Consumer public result",
        "must never consume Snapshot Builder output directly",
        "must never duplicate Snapshot validation",
        "produces only Resume Eligibility and Resume Plan public contracts",
        "Runtime Resume Execution is outside Package 126",
        "Recovery, Scheduler, Dispatcher, Operator, Persistence, Audit, and Journal remain downstream domains",
        "Runtime Snapshot Consumer",
        "Snapshot Builder",
        "Snapshot Validation",
        "Runtime Resume Execution",
    ):
        assert token in text


def test_eligibility_contract_is_complete_and_descriptive_only():
    text = CONTRACT.read_text(encoding="utf-8")

    for token in (
        "Input: Runtime Snapshot Consumer public result",
        "Output: eligibility decision",
        "Allowed statuses",
        "Blocked statuses",
        "Missing identity behavior",
        "Lineage mismatch behavior",
        "Invalid snapshot behavior",
        "No runtime mutation",
        "No execution",
        "produces only a descriptive eligibility decision",
    ):
        assert token in text


def test_planning_contract_has_mapping_token_and_forbidden_domains():
    text = CONTRACT.read_text(encoding="utf-8")

    for token in (
        "Input: eligibility decision + Runtime Snapshot Consumer public result",
        "Output: deterministic Resume Plan",
        "Required fields",
        "Optional fields",
        "Field-level mapping table",
        "Deterministic resume_token rule",
        "no scheduler",
        "no recovery",
        "no operator",
        "no dispatcher",
        "no persistence",
        "no audit",
        "no journal",
        "no runtime execution",
    ):
        assert token in text


def test_execution_boundary_contract_keeps_execution_future_domain_only():
    text = CONTRACT.read_text(encoding="utf-8")

    for token in (
        "Execution is future-domain only",
        "Package 126 does not implement execution",
        "A Resume Plan may be consumed later by Runtime Resume Execution",
        "Execution must not be hidden inside eligibility or planning",
        "execution_allowed",
        "future_domain_only",
    ):
        assert token in text


def test_validation_contract_and_error_taxonomy_are_sealed():
    text = CONTRACT.read_text(encoding="utf-8")

    for token in (
        "Validation Contract",
        "Eligibility Validation",
        "Plan Validation",
        "Execution-Boundary Validation",
        "Unknown Field Policy",
        "Required Field Policy",
        "Type Policy",
        "Identity Policy",
        "Lineage Policy",
        "Status Policy",
        "Error Taxonomy",
        "Every failure must belong to exactly one category",
        "Validation reports are descriptive only",
        "No auto-repair",
    ):
        assert token in text

    for category in (
        "Snapshot Error",
        "Consumer Result Error",
        "Eligibility Error",
        "Planning Error",
        "Execution Boundary Error",
        "Identity Error",
        "Lineage Error",
        "Status Error",
        "Safety Error",
        "Compatibility Error",
    ):
        assert category in text


def test_responsibility_matrix_has_exactly_one_owner_per_capability():
    text = CONTRACT.read_text(encoding="utf-8")

    for token in (
        "Responsibility Matrix",
        "Exactly one owner per capability",
        "Snapshot validation",
        "Snapshot consumer result",
        "Resume eligibility",
        "Resume planning",
        "Resume execution",
        "Recovery",
        "Scheduler",
        "Operator",
        "Dispatcher",
        "Persistence",
        "Audit",
        "Journal",
        "No shared ownership is allowed",
    ):
        assert token in text


def test_public_api_contract_allows_only_future_planning_apis_and_rejects_execution_apis():
    text = CONTRACT.read_text(encoding="utf-8")

    for token in (
        "Public API Contract",
        "Future implementation may expose only",
        "check_resume_eligibility(...)",
        "build_resume_plan(...)",
        "validate_resume_plan(...)",
        "resume_plan_to_summary(...)",
        "Do not expose",
        "resume(...)",
        "execute_resume(...)",
        "recover(...)",
        "schedule(...)",
        "dispatch(...)",
        "operate(...)",
        "Forbidden public APIs are rejected by this contract text",
    ):
        assert token in text


def test_architecture_rules_forbid_runtime_behavior():
    text = CONTRACT.read_text(encoding="utf-8")

    for token in (
        "Resume Contract consumes Snapshot Consumer public result only",
        "Resume Contract must not call Snapshot Builder directly",
        "Resume Contract must not duplicate Snapshot validation logic",
        "Resume Contract must not perform Recovery",
        "Resume Contract must not schedule",
        "Resume Contract must not dispatch",
        "Resume Contract must not call Operator",
        "Resume Contract must not persist, audit, journal, replay, or execute",
        "No piecemeal architecture patches",
        "Runtime execution remains forbidden",
    ):
        assert token in text


def test_no_runtime_resume_implementation_module_added():
    forbidden_paths = (
        Path("core/runtime/aer_runtime_resume.py"),
        Path("core/runtime/aer_runtime_resume_contract.py"),
        Path("core/runtime/aer_runtime_resume_plan.py"),
        Path("core/runtime/aer_runtime_resume_execution.py"),
        Path("core/runtime/aer_runtime_resume_integration.py"),
    )

    for path in forbidden_paths:
        assert not path.exists()


def test_inventory_marks_runtime_resume_contract_as_missing_implementation():
    assert INVENTORY.exists()

    text = INVENTORY.read_text(encoding="utf-8")

    for token in (
        "Runtime Resume",
        "docs/contracts/runtime/resume_v1.md",
        "TBD",
        "Missing Implementation",
        "Package 126 contract/spec + seal only; implementation remains future work",
    ):
        assert token in text


def test_package_sequence_contains_package_126_resume_contract_entry():
    assert PACKAGE_SEQUENCE.exists()

    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")

    for token in (
        "Package 126: Runtime Resume Contract",
        "docs/contracts/runtime/resume_v1.md",
        "tests/test_aer_runtime_resume_contract.py",
        "docs/contracts/runtime/inventory.md",
        "Eligibility / Planning / Execution Boundary are separate",
        "must never collapse into one public API",
        "deterministic resume_token rule",
        "Boundary Matrix",
        "upstream and downstream boundaries",
        "does not implement execution",
        "no runtime implementation module",
        "Final decision: GO",
    ):
        assert token in text


def test_runtime_resume_contract_final_decision_is_unambiguous():
    text = CONTRACT.read_text(encoding="utf-8")

    assert text.count("Final decision:") == 1
    assert text.rstrip().endswith("Final decision: GO") or text.rstrip().endswith(
        "Final decision: NO-GO"
    )
