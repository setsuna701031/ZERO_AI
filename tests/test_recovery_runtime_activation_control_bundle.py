from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_activation_request_v1.md")
GATE_SOURCE = Path("core/runtime/recovery_activation_gate.py")
POLICY_SOURCE = Path("core/runtime/recovery_activation_policy.py")
BRIDGE_SOURCE = Path("core/runtime/recovery_activation_admission_bridge.py")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
OBSERVATION_SEAL = Path("docs/runtime_recovery_activation_observation_seal.md")
READINESS_REVIEW = Path("docs/runtime_recovery_controlled_activation_readiness_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

CONTRACT_NAMES = (
    "RecoveryActivationRequest",
    "RecoveryActivationResult",
    "RecoveryActivationFailure",
    "RecoveryActivationPolicy",
    "RecoveryActivationOwnership",
    "RecoveryActivationLifecycle",
)

FORBIDDEN_IMPORT_TARGETS = (
    "aer_runtime_recovery_gateway",
    "aer_runtime_recovery_bridge",
    "aer_runtime_recovery_executor",
    "aer_runtime_recovery_scheduler_adapter",
    "aer_runtime_recovery_operator_adapter",
    "aer_runtime_recovery_supervisor_adapter",
    "aer_runtime_recovery_native_adapter",
    "aer_runtime_recovery_runtime_integration",
    "runtime_recovery_executor",
    "runtime_recovery_integration",
    "runtime_supervisor",
    "operator",
    "scheduler",
    "planner",
    "native",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_contract_doc_exists_and_has_required_names():
    assert CONTRACT.exists()
    text = _text(CONTRACT)
    for name in CONTRACT_NAMES:
        assert name in text


def test_three_runtime_modules_import_and_expose_exact_all():
    from core.runtime import recovery_activation_admission_bridge
    from core.runtime import recovery_activation_gate
    from core.runtime import recovery_activation_policy

    assert recovery_activation_gate.__all__ == ["prepare_recovery_activation_gate"]
    assert recovery_activation_policy.__all__ == ["prepare_recovery_activation_policy"]
    assert recovery_activation_admission_bridge.__all__ == [
        "prepare_recovery_activation_admission_bridge"
    ]


def test_prepare_recovery_activation_gate_returns_expected_disabled_dict():
    from core.runtime.recovery_activation_gate import prepare_recovery_activation_gate

    result = prepare_recovery_activation_gate()

    assert type(result) is dict
    assert result == {
        "enabled": False,
        "gate_status": "disabled",
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }


def test_prepare_recovery_activation_policy_returns_expected_stub_dict():
    from core.runtime.recovery_activation_policy import prepare_recovery_activation_policy

    result = prepare_recovery_activation_policy()

    assert type(result) is dict
    assert result == {
        "enabled": False,
        "policy_status": "stub",
        "activation_policy_result": "reserved",
        "activation_allowed": False,
        "execution_allowed": False,
        "runtime_state_mutated": False,
    }


def test_prepare_recovery_activation_admission_bridge_returns_expected_stub_dict():
    from core.runtime.recovery_activation_admission_bridge import (
        prepare_recovery_activation_admission_bridge,
    )

    result = prepare_recovery_activation_admission_bridge()

    assert type(result) is dict
    assert result == {
        "enabled": False,
        "bridge_status": "stub",
        "admission_bound": False,
        "activation_allowed": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }


def test_all_activation_execution_mutation_flags_are_false():
    from core.runtime.recovery_activation_admission_bridge import (
        prepare_recovery_activation_admission_bridge,
    )
    from core.runtime.recovery_activation_gate import prepare_recovery_activation_gate
    from core.runtime.recovery_activation_policy import prepare_recovery_activation_policy

    results = (
        prepare_recovery_activation_gate(),
        prepare_recovery_activation_policy(),
        prepare_recovery_activation_admission_bridge(),
    )

    for result in results:
        assert result["enabled"] is False
        assert result["activation_allowed"] is False
        assert result["execution_allowed"] is False
        assert result["runtime_state_mutated"] is False
        if "recovery_enabled" in result:
            assert result["recovery_enabled"] is False
        if "admission_bound" in result:
            assert result["admission_bound"] is False


def test_forbidden_imports_classes_and_dataclasses_are_absent_from_source_text():
    for path in (GATE_SOURCE, POLICY_SOURCE, BRIDGE_SOURCE):
        text = _text(path)
        assert "import " not in text
        assert "from " not in text
        assert "class " not in text
        assert "dataclass" not in text
        for forbidden in FORBIDDEN_IMPORT_TARGETS:
            assert forbidden not in text


def test_inventory_contains_recovery_activation_request_v1():
    text = _text(INVENTORY)
    assert "recovery_activation_request_v1" in text


def test_docs_contain_activation_observation_seal_and_readiness_review():
    seal = _text(OBSERVATION_SEAL)
    review = _text(READINESS_REVIEW)

    assert "Runtime Recovery Activation Observation Seal" in seal
    assert "Activation is observable only." in seal
    assert "No recovery execution is implemented." in seal
    assert "No gateway activation is implemented." in seal
    assert "Runtime Recovery Controlled Activation Readiness Review" in review
    assert "GO / NO-GO decision: GO" in review
    assert "Activation blockers" in review


def test_package_sequence_contains_packages_281_to_286():
    text = _text(PACKAGE_SEQUENCE)
    for package_number in ("281", "282", "283", "284", "285", "286"):
        assert f"## Package {package_number}" in text
    assert "Package 281: Recovery Activation Request Contract" in text
    assert "Package 282: Recovery Activation Gate Stub" in text
    assert "Package 283: Recovery Activation Policy Stub" in text
    assert "Package 284: Recovery Activation Admission Bridge Stub" in text
    assert "Package 285: Recovery Activation Observation Seal" in text
    assert "Package 286: Recovery Controlled Activation Readiness Review" in text


def test_package_286_contains_final_go_to_package_287():
    review = _text(READINESS_REVIEW)
    sequence = _text(PACKAGE_SEQUENCE)

    assert "Final decision: GO. Next package: Package 287." in review
    assert "Final decision: GO. Next package: Package 287." in sequence
