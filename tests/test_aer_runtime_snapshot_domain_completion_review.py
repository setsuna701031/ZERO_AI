from pathlib import Path


REVIEW_DOC = Path("docs/aer_runtime_snapshot_domain_completion_review.md")
SNAPSHOT_MODULE = Path("core/runtime/aer_runtime_snapshot.py")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def test_snapshot_domain_completion_review_document_exists_and_covers_required_scope():
    assert REVIEW_DOC.exists()

    text = REVIEW_DOC.read_text(encoding="utf-8")

    assert "Snapshot Domain Completion Review" in text

    for area in (
        "Public API Review",
        "Contract Coverage Review",
        "Validation Coverage Review",
        "Error Taxonomy Review",
        "Architecture Boundaries Review",
        "Responsibility Matrix",
        "Determinism and Purity Review",
        "Evolution Readiness Review",
        "Integration Readiness",
    ):
        assert area in text


def test_snapshot_domain_completion_review_contains_decision_and_package_limits():
    text = REVIEW_DOC.read_text(encoding="utf-8")

    assert "GO means Snapshot v1 domain is complete enough to begin runtime integration in the next package" in text
    assert "NO-GO means runtime integration is blocked" in text
    assert "Final decision:" in text
    assert "Final decision: GO" in text or "Final decision: NO-GO" in text
    assert "Package 121 does not authorize runtime mainline integration" in text
    assert "runtime mainline integration" in text
    assert "no runtime mainline integration" in text
    assert "documentation plus seal test only" in text
    assert "not piecemeal patches" in text


def test_snapshot_domain_completion_review_contains_public_api_contract_validation_and_taxonomy_items():
    text = REVIEW_DOC.read_text(encoding="utf-8")

    for token in (
        "build_snapshot_from_resume_summary",
        "validate_snapshot",
        "snapshot_to_summary",
        "__all__",
        "approved Snapshot public API",
        "Snapshot v1 schema",
        "Resume Summary Adapter Contract",
        "Field-level mapping table",
        "Required",
        "optional",
        "default",
        "deterministic `snapshot_id`",
        "required fields",
        "unknown fields",
        "Schema version",
        "Type validation",
        "Identity validation",
        "Lineage validation",
        "Status validation",
        "Consistency validation",
        "Determinism validation",
        "Invalid snapshot behavior",
        "exactly one category",
        "descriptive-only",
        "no auto-repair",
    ):
        assert token in text

    for category in (
        "Schema Error",
        "Required Field Error",
        "Unknown Field Error",
        "Type Error",
        "Identity Error",
        "Lineage Error",
        "Status Error",
        "Consistency Error",
        "Version Error",
        "Determinism Error",
    ):
        assert category in text


def test_snapshot_domain_completion_review_contains_forbidden_dependency_list_and_purity_rules():
    text = REVIEW_DOC.read_text(encoding="utf-8")

    assert "Forbidden dependency list" in text

    for forbidden in (
        "IO",
        "storage",
        "persistence",
        "replay",
        "recovery",
        "audit",
        "journal",
        "scheduler",
        "operator",
        "runtime dispatcher",
        "work-package pipeline",
        "runtime mainline integration",
        "no time",
        "no random",
        "no `uuid4`",
        "no process, environment, or filesystem dependency",
        "does not mutate input",
        "stable canonical JSON and SHA-256",
    ):
        assert forbidden in text


def test_snapshot_domain_completion_review_contains_responsibility_matrix_with_single_owners():
    text = REVIEW_DOC.read_text(encoding="utf-8")

    assert "Responsibility Matrix" in text
    assert "exactly one owning domain" in text
    assert "Snapshot shall not absorb responsibilities owned by Runtime Integration" in text
    assert "architectural boundary for all future integration packages" in text
    assert "No capability in this matrix has shared ownership" in text

    expected_rows = {
        "Snapshot Builder": "Snapshot",
        "Snapshot Validator": "Snapshot",
        "`snapshot_id` generation": "Snapshot",
        "Resume Summary": "Resume Summary",
        "Runtime Resume": "Runtime Integration",
        "Runtime Recovery": "Runtime Integration",
        "Scheduler": "Runtime Integration",
        "Operator": "Runtime Integration",
        "Persistence": "Runtime Integration",
        "Audit": "Runtime Integration",
        "Journal": "Runtime Integration",
        "Runtime Dispatcher": "Runtime Integration",
    }

    for capability, owner in expected_rows.items():
        assert f"| {capability} | {owner} |" in text


def test_snapshot_domain_completion_review_requires_v2_boundary_and_no_piecemeal_resolution():
    text = REVIEW_DOC.read_text(encoding="utf-8")

    assert "Snapshot v1 compatibility boundary" in text
    assert "Future Snapshot v2 migration requires a dedicated v2 contract before implementation" in text
    assert "what is allowed to evolve later" not in text.lower()
    assert "Future v2 work may add migration rules" in text
    assert "must remain sealed" in text
    assert "complete architecture-resolution package, not piecemeal patches" in text


def test_snapshot_module_exists_and_review_does_not_authorize_package_121_mainline_integration():
    assert SNAPSHOT_MODULE.exists()

    text = REVIEW_DOC.read_text(encoding="utf-8")

    assert "Package 121 does not authorize runtime mainline integration" in text
    assert "Still forbidden in Package 121" in text
    assert "runtime mainline integration" in text
    assert "Final decision: GO" in text


def test_package_sequence_contains_package_121():
    assert PACKAGE_SEQUENCE.exists()

    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")

    assert "Package 121: Snapshot Domain Completion Review" in text
    assert "docs/aer_runtime_snapshot_domain_completion_review.md" in text
    assert "no runtime mainline integration" in text
