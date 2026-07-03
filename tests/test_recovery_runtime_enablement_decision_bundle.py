from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_enablement_decision_v1.md")
DECISION_SOURCE = Path("core/runtime/recovery_enablement_decision.py")
PROJECTION_SOURCE = Path("core/runtime/recovery_enablement_decision_projection.py")
AUDIT_SOURCE = Path("core/runtime/recovery_enablement_decision_audit.py")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
BOUNDARY_SEAL = Path("docs/runtime_recovery_enablement_decision_boundary_seal.md")
BLOCKER_REVIEW = Path("docs/runtime_recovery_execution_blocker_review.md")
GO_REVIEW = Path("docs/runtime_recovery_controlled_enablement_go_review.md")
MILESTONE_SEAL = Path("docs/recovery_enablement_decision_milestone_seal.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

CONTRACT_NAMES = (
    "RecoveryEnablementDecisionRequest",
    "RecoveryEnablementDecisionResult",
    "RecoveryEnablementDecisionFailure",
    "RecoveryEnablementDecisionPolicy",
    "RecoveryEnablementDecisionOwnership",
    "RecoveryEnablementDecisionLifecycle",
)

EXPECTED_DECISION = {
    "enabled": False,
    "decision_status": "disabled",
    "decision": "blocked",
    "enablement_allowed": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
}

EXPECTED_PROJECTION = {
    "enabled": False,
    "projection_status": "stub",
    "decision_status": "disabled",
    "decision": "blocked",
    "enablement_allowed": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
}

EXPECTED_AUDIT = {
    "enabled": False,
    "audit_status": "stub",
    "decision_recorded": False,
    "decision": "blocked",
    "enablement_allowed": False,
    "execution_allowed": False,
    "runtime_state_mutated": False,
}

FORBIDDEN_IMPORT_TARGETS = (
    "gateway",
    "supervisor",
    "operator",
    "scheduler",
    "planner",
    "native",
    "bridge",
    "executor",
    "adapter",
    "integration",
    "legacy",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_contract_doc_exists_and_has_required_names():
    assert CONTRACT.exists()
    text = _text(CONTRACT)
    for name in CONTRACT_NAMES:
        assert name in text


def test_three_runtime_modules_import_and_expose_exact_all():
    from core.runtime import recovery_enablement_decision
    from core.runtime import recovery_enablement_decision_audit
    from core.runtime import recovery_enablement_decision_projection

    assert recovery_enablement_decision.__all__ == [
        "prepare_recovery_enablement_decision"
    ]
    assert recovery_enablement_decision_projection.__all__ == [
        "prepare_recovery_enablement_decision_projection"
    ]
    assert recovery_enablement_decision_audit.__all__ == [
        "prepare_recovery_enablement_decision_audit"
    ]


def test_prepare_functions_return_expected_disabled_blocked_dicts():
    from core.runtime.recovery_enablement_decision import (
        prepare_recovery_enablement_decision,
    )
    from core.runtime.recovery_enablement_decision_audit import (
        prepare_recovery_enablement_decision_audit,
    )
    from core.runtime.recovery_enablement_decision_projection import (
        prepare_recovery_enablement_decision_projection,
    )

    results = (
        (prepare_recovery_enablement_decision(), EXPECTED_DECISION),
        (prepare_recovery_enablement_decision_projection(), EXPECTED_PROJECTION),
        (prepare_recovery_enablement_decision_audit(), EXPECTED_AUDIT),
    )

    for result, expected in results:
        assert type(result) is dict
        assert result == expected


def test_prepare_functions_return_fresh_deterministic_dicts():
    from core.runtime.recovery_enablement_decision import (
        prepare_recovery_enablement_decision,
    )

    first = prepare_recovery_enablement_decision()
    second = prepare_recovery_enablement_decision()

    assert first == second
    assert first is not second


def test_all_enablement_execution_mutation_and_recovery_flags_are_false():
    for result in (EXPECTED_DECISION, EXPECTED_PROJECTION, EXPECTED_AUDIT):
        assert result["enabled"] is False
        assert result["decision"] == "blocked"
        assert result["enablement_allowed"] is False
        assert result["execution_allowed"] is False
        assert result["runtime_state_mutated"] is False
        if "recovery_enabled" in result:
            assert result["recovery_enabled"] is False


def test_forbidden_imports_classes_and_dataclasses_are_absent():
    for path in (DECISION_SOURCE, PROJECTION_SOURCE, AUDIT_SOURCE):
        text = _text(path)
        assert "import " not in text
        assert "from " not in text
        assert "class " not in text
        assert "dataclass" not in text
        assert text.count("def prepare_") == 1
        for forbidden in FORBIDDEN_IMPORT_TARGETS:
            assert forbidden not in text


def test_inventory_contains_recovery_enablement_decision_v1():
    text = _text(INVENTORY)

    assert "recovery_enablement_decision_v1" in text


def test_docs_contain_boundary_seal_blocker_review_go_review_and_milestone():
    boundary = _text(BOUNDARY_SEAL)
    blocker = _text(BLOCKER_REVIEW)
    go_review = _text(GO_REVIEW)
    milestone = _text(MILESTONE_SEAL)

    assert "Runtime Recovery Enablement Decision Boundary Seal" in boundary
    assert "Decision is blocked by default." in boundary
    assert "Enablement is not granted." in boundary
    assert "Execution is not allowed." in boundary
    assert "Decision audit is stub/data only." in boundary
    assert "No runtime mutation is implemented." in boundary
    assert "No gateway activation is implemented." in boundary
    assert "Package 317 does not add persistence." in boundary
    assert "Package 317 does not spawn subprocesses." in boundary
    assert "Package 317 does not invoke endpoints." in boundary
    assert "Package 317 does not register hooks." in boundary

    assert "Runtime Recovery Execution Blocker Review" in blocker
    assert "Execution Blockers Checklist" in blocker
    assert "Blockers That Must Remain Active" in blocker
    assert "Blockers Required Before Activation" in blocker
    assert "Boundary Matrix" in blocker
    assert "Risk Table" in blocker
    assert "Execution remains disabled." in blocker

    assert "Runtime Recovery Controlled Enablement GO Review" in go_review
    assert "GO / NO-GO decision for future Package 321" in go_review
    assert "Prerequisites For Limited Enablement" in go_review
    assert "Constraints For Future Enablement" in go_review
    assert "Package 319 still does not enable recovery." in go_review

    assert "Recovery Enablement Decision Milestone Seal" in milestone
    assert "Packages 301-320 Completion Map" in milestone
    assert "Enablement layer completed." in milestone
    assert "Control pipeline completed." in milestone
    assert "Enablement decision layer completed." in milestone
    assert "Final decision: GO. Next package: Package 321." in milestone


def test_package_sequence_contains_packages_313_to_320():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("313", "314", "315", "316", "317", "318", "319", "320"):
        assert f"## Package {package_number}" in text

    assert "Package 313: Recovery Enablement Decision Contract" in text
    assert "Package 314: Recovery Enablement Decision Stub" in text
    assert "Package 315: Recovery Enablement Decision Projection" in text
    assert "Package 316: Recovery Enablement Decision Audit Stub" in text
    assert "Package 317: Recovery Enablement Decision Boundary Seal" in text
    assert "Package 318: Recovery Execution Blocker Review" in text
    assert "Package 319: Recovery Controlled Enablement GO Review" in text
    assert "Package 320: Recovery Enablement Decision Milestone Seal" in text


def test_package_320_contains_final_go_to_package_321():
    milestone = _text(MILESTONE_SEAL)
    sequence = _text(PACKAGE_SEQUENCE)

    assert "Final decision: GO. Next package: Package 321." in milestone
    assert "Final decision: GO. Next package: Package 321." in sequence
