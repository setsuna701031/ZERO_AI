from pathlib import Path


BLUEPRINT = Path("docs/aer_runtime_snapshot_integration_blueprint.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
SNAPSHOT_MODULE = Path("core/runtime/aer_runtime_snapshot.py")


def test_runtime_snapshot_integration_blueprint_exists_and_has_required_sections():
    assert BLUEPRINT.exists()

    text = BLUEPRINT.read_text(encoding="utf-8")

    for section in (
        "Runtime Snapshot Integration Blueprint",
        "Purpose",
        "Domain Boundary",
        "Responsibility Matrix",
        "Single Source of Domain Logic",
        "Runtime Lifecycle",
        "Integration API",
        "Dependency Rules",
        "Failure Boundary",
        "Evolution Strategy",
        "Package Plan",
        "Architecture Risks",
        "GO / NO-GO",
    ):
        assert section in text


def test_blueprint_defines_complete_domain_boundaries():
    text = BLUEPRINT.read_text(encoding="utf-8")

    for boundary in (
        "Snapshot Domain",
        "Runtime Integration Domain",
        "Recovery Domain",
        "Scheduler",
        "Operator",
        "Persistence",
        "Audit",
        "Journal",
        "Dispatcher",
        "Work Package Runtime",
    ):
        assert boundary in text


def test_blueprint_responsibility_matrix_has_single_owner_for_required_capabilities():
    text = BLUEPRINT.read_text(encoding="utf-8")

    assert "Every capability has exactly one owning domain" in text
    assert "No shared ownership is allowed" in text
    assert "Snapshot shall not absorb responsibilities owned by Runtime Integration" in text
    assert "architectural boundary for all future Runtime Snapshot integration packages" in text

    expected_rows = {
        "Resume Summary": "Resume Summary",
        "Snapshot Builder": "Snapshot",
        "Snapshot Validator": "Snapshot",
        "Runtime Snapshot Consumer": "Runtime Integration",
        "Runtime Resume": "Runtime Integration",
        "Runtime Recovery": "Runtime Integration",
        "Scheduler": "Runtime Integration",
        "Operator": "Runtime Integration",
        "Persistence": "Runtime Integration",
        "Audit": "Runtime Integration",
        "Journal": "Runtime Integration",
        "Runtime Dispatcher": "Runtime Integration",
        "Work Package Runtime": "Runtime Integration",
    }

    for capability, owner in expected_rows.items():
        assert f"| {capability} | {owner} |" in text


def test_blueprint_seals_single_source_of_domain_logic():
    text = BLUEPRINT.read_text(encoding="utf-8")

    for rule in (
        "Runtime Integration may orchestrate domain boundaries",
        "shall not duplicate, reimplement, or replace domain logic",
        "Integration layer may orchestrate.",
        "Integration layer shall not duplicate Domain logic.",
        "Domain rules must remain owned by the Domain.",
        "Integration layer consumes Domain public APIs only.",
        "Any new Domain behavior must be added in the owning Domain, not in the Integration layer.",
        "must not compute Snapshot identity",
        "validate Snapshot structure independently",
        "repair Snapshot payloads",
        "build Snapshot payloads",
        "not only Runtime Snapshot Consumer",
    ):
        assert rule in text


def test_blueprint_lifecycle_and_integration_api_are_complete():
    text = BLUEPRINT.read_text(encoding="utf-8")

    for lifecycle_step in (
        "Resume Summary",
        "Snapshot Build",
        "Snapshot Validation",
        "Snapshot Accepted",
        "Runtime Integration",
        "Resume",
        "Recovery",
        "Scheduling and Operator Coordination",
        "Dispatcher and Execution",
        "Persistence, Audit, and Journal",
        "Next Snapshot",
    ):
        assert lifecycle_step in text

    for api_term in (
        "Allowed input",
        "Allowed output",
        "Allowed caller",
        "Allowed callee",
        "Forbidden caller",
        "Forbidden callee",
        "Runtime Snapshot Consumer",
        "Resume Integration",
        "Recovery Integration",
        "Scheduler Integration",
        "Operator Integration",
        "Dispatcher Integration",
        "Persistence Integration",
        "Audit Integration",
        "Journal Integration",
        "Work Package Runtime Integration",
    ):
        assert api_term in text


def test_blueprint_dependency_failure_and_evolution_rules_are_explicit():
    text = BLUEPRINT.read_text(encoding="utf-8")

    for token in (
        "Allowed dependencies",
        "Forbidden dependencies",
        "No circular dependency rule",
        "Snapshot remains independent",
        "Every failure belongs to exactly one owner",
        "Validation failure",
        "Integration failure",
        "Resume failure",
        "Recovery failure",
        "Dispatcher failure",
        "Ownership violation",
        "Future",
        "v2",
        "v3",
        "Migration boundary",
        "Compatibility boundary",
        "Deprecation strategy",
    ):
        assert token in text


def test_blueprint_package_plan_covers_complete_roadmap_with_acceptance_criteria():
    text = BLUEPRINT.read_text(encoding="utf-8")

    for package in (
        "Package 123: Runtime Snapshot Consumer",
        "Package 124: Resume Integration",
        "Package 125: Recovery Integration",
        "Package 126: Scheduler Integration",
        "Package 127: Operator Integration",
        "Package 128: Dispatcher Integration",
        "Package 129: Runtime Mainline Landing",
        "Package 130: Integration Closure Review",
    ):
        assert package in text

    for required in ("Goal:", "Inputs:", "Outputs:", "Dependencies:", "Acceptance criteria:"):
        assert text.count(required) >= 8


def test_blueprint_architecture_risks_and_decision_are_sealed():
    text = BLUEPRINT.read_text(encoding="utf-8")

    for risk in (
        "Patch-driven architecture",
        "Responsibility drift",
        "Hidden dependency",
        "Circular dependency",
        "Runtime leakage",
        "Snapshot scope expansion",
        "Integration shortcut",
        "Future migration breakage",
    ):
        assert risk in text

    assert "GO means Runtime Integration architecture is complete enough to begin implementation packages" in text
    assert "NO-GO means implementation is blocked" in text
    assert "one complete architecture package, never by piecemeal patches" in text
    assert text.rstrip().endswith("Final decision: GO") or text.rstrip().endswith("Final decision: NO-GO")


def test_blueprint_is_architecture_only_and_does_not_authorize_runtime_integration():
    text = BLUEPRINT.read_text(encoding="utf-8")

    assert "documentation + seal only" in text
    assert "does not implement runtime integration" in text
    assert "modify runtime behavior" in text
    assert "modify Snapshot Builder" in text
    assert "modify Snapshot Validator" in text
    assert "Do not" not in SNAPSHOT_MODULE.read_text(encoding="utf-8")


def test_package_sequence_contains_package_122_blueprint():
    assert PACKAGE_SEQUENCE.exists()

    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")

    assert "Package 122: Runtime Snapshot Integration Blueprint" in text
    assert "docs/aer_runtime_snapshot_integration_blueprint.md" in text
    assert "tests/test_aer_runtime_snapshot_integration_blueprint.py" in text
    assert "documentation + seal only" in text
    assert "does not implement runtime integration" in text
