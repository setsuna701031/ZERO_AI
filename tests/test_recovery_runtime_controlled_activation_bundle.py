from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_controlled_activation_v1.md")
GATE_SOURCE = Path("core/runtime/recovery_controlled_activation_gate.py")
POLICY_SOURCE = Path("core/runtime/recovery_controlled_activation_policy.py")
PROJECTION_SOURCE = Path("core/runtime/recovery_controlled_activation_projection.py")
AUDIT_SOURCE = Path("core/runtime/recovery_controlled_activation_audit.py")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
SEAL = Path("docs/runtime_recovery_controlled_activation_skeleton_seal.md")
REVIEW = Path("docs/runtime_recovery_controlled_activation_skeleton_readiness_review.md")
MILESTONE = Path("docs/recovery_controlled_activation_milestone_seal.md")

CONTRACT_NAMES = (
    "RecoveryControlledActivationRequest",
    "RecoveryControlledActivationResult",
    "RecoveryControlledActivationFailure",
    "RecoveryControlledActivationPolicy",
    "RecoveryControlledActivationOwnership",
    "RecoveryControlledActivationLifecycle",
)

EXPECTED_GATE = {
    "enabled": False,
    "gate_status": "disabled",
    "activation_allowed": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
    "reason": "future_package",
}

EXPECTED_POLICY = {
    "enabled": False,
    "policy_status": "reserved",
    "activation_allowed": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
    "reason": "future_package",
}

EXPECTED_PROJECTION = {
    "enabled": False,
    "projection_status": "stub",
    "activation_status": "disabled",
    "activation_allowed": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
    "reason": "future_package",
}

EXPECTED_AUDIT = {
    "enabled": False,
    "audit_status": "stub",
    "activation_recorded": False,
    "activation_allowed": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
    "reason": "future_package",
}

FORBIDDEN_SOURCE_TEXT = (
    "import ",
    "from ",
    "class ",
    "dataclass",
    "scheduler",
    "dispatcher",
    "executor",
    "gateway",
    "bridge",
    "adapter",
    "integration",
    "thread",
    "timer",
    "subprocess",
    "feature_flag",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_sequence_reaches_package_320_before_321_entries():
    text = _text(PACKAGE_SEQUENCE)

    assert "## Package 320" in text
    assert "Final decision: GO. Next package: Package 321." in text


def test_contract_doc_exists_and_has_required_names():
    assert CONTRACT.exists()
    text = _text(CONTRACT)
    for name in CONTRACT_NAMES:
        assert name in text


def test_runtime_modules_import_and_expose_exact_all():
    from core.runtime import recovery_controlled_activation_audit
    from core.runtime import recovery_controlled_activation_gate
    from core.runtime import recovery_controlled_activation_policy
    from core.runtime import recovery_controlled_activation_projection

    assert recovery_controlled_activation_gate.__all__ == [
        "prepare_recovery_controlled_activation_gate"
    ]
    assert recovery_controlled_activation_policy.__all__ == [
        "prepare_recovery_controlled_activation_policy"
    ]
    assert recovery_controlled_activation_projection.__all__ == [
        "prepare_recovery_controlled_activation_projection"
    ]
    assert recovery_controlled_activation_audit.__all__ == [
        "prepare_recovery_controlled_activation_audit"
    ]


def test_prepare_functions_return_expected_disabled_metadata():
    from core.runtime.recovery_controlled_activation_audit import (
        prepare_recovery_controlled_activation_audit,
    )
    from core.runtime.recovery_controlled_activation_gate import (
        prepare_recovery_controlled_activation_gate,
    )
    from core.runtime.recovery_controlled_activation_policy import (
        prepare_recovery_controlled_activation_policy,
    )
    from core.runtime.recovery_controlled_activation_projection import (
        prepare_recovery_controlled_activation_projection,
    )

    results = (
        (prepare_recovery_controlled_activation_gate(), EXPECTED_GATE),
        (prepare_recovery_controlled_activation_policy(), EXPECTED_POLICY),
        (prepare_recovery_controlled_activation_projection(), EXPECTED_PROJECTION),
        (prepare_recovery_controlled_activation_audit(), EXPECTED_AUDIT),
    )

    for result, expected in results:
        assert type(result) is dict
        assert result == expected


def test_prepare_functions_return_fresh_deterministic_dicts():
    from core.runtime.recovery_controlled_activation_gate import (
        prepare_recovery_controlled_activation_gate,
    )

    first = prepare_recovery_controlled_activation_gate()
    second = prepare_recovery_controlled_activation_gate()

    assert first == second
    assert first is not second


def test_all_activation_execution_mutation_and_recovery_flags_are_false():
    for result in (EXPECTED_GATE, EXPECTED_POLICY, EXPECTED_PROJECTION, EXPECTED_AUDIT):
        assert result["enabled"] is False
        assert result["activation_allowed"] is False
        assert result["execution_allowed"] is False
        assert result["recovery_enabled"] is False
        assert result["runtime_state_mutated"] is False
        assert result["reason"] == "future_package"


def test_forbidden_imports_classes_and_runtime_wiring_are_absent():
    for path in (GATE_SOURCE, POLICY_SOURCE, PROJECTION_SOURCE, AUDIT_SOURCE):
        text = _text(path)
        assert text.count("def prepare_") == 1
        for forbidden in FORBIDDEN_SOURCE_TEXT:
            assert forbidden not in text


def test_inventory_and_docs_contain_controlled_activation_skeleton():
    inventory = _text(INVENTORY)
    seal = _text(SEAL)
    review = _text(REVIEW)
    milestone = _text(MILESTONE)

    assert "recovery_controlled_activation_v1" in inventory
    assert "Controlled activation remains disabled." in seal
    assert "No scheduler wiring is implemented." in seal
    assert "No dispatcher wiring is implemented." in seal
    assert "No executor wiring is implemented." in seal
    assert "No gateway behavior mutation is implemented." in seal
    assert "No background worker is implemented." in seal
    assert "No thread or timer creation is implemented." in seal
    assert "No feature flag enabling is implemented." in seal
    assert "GO / NO-GO decision: GO" in review
    assert "Recovery Runtime remains disabled." in review
    assert "Recovery Controlled Activation Milestone Seal" in milestone
    assert "Final decision: GO. Next package: Package 329." in milestone


def test_package_sequence_contains_packages_321_to_328():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("321", "322", "323", "324", "325", "326", "327", "328"):
        assert f"## Package {package_number}" in text

    assert "Package 321: Recovery Controlled Activation Contract" in text
    assert "Package 322: Recovery Controlled Activation Gate Skeleton" in text
    assert "Package 323: Recovery Controlled Activation Policy Skeleton" in text
    assert "Package 324: Recovery Controlled Activation Projection Skeleton" in text
    assert "Package 325: Recovery Controlled Activation Audit Skeleton" in text
    assert "Package 326: Recovery Controlled Activation Skeleton Seal" in text
    assert "Package 327: Recovery Controlled Activation Skeleton Readiness Review" in text
    assert "Package 328: Recovery Controlled Activation Milestone Seal" in text
