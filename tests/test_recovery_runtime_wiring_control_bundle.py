from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_wiring_control_v1.md")
CONTROLLER_SOURCE = Path("core/runtime/recovery_wiring_controller.py")
BRIDGE_SOURCE = Path("core/runtime/recovery_activation_integration_bridge.py")
PROJECTION_SOURCE = Path("core/runtime/recovery_wiring_status_projection.py")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
WIRING_CONTROL_SEAL = Path("docs/runtime_recovery_wiring_control_seal.md")
READINESS_REVIEW = Path("docs/runtime_recovery_wiring_readiness_review_v2.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

CONTRACT_NAMES = (
    "RecoveryWiringControlRequest",
    "RecoveryWiringControlResult",
    "RecoveryWiringControlFailure",
    "RecoveryWiringControlPolicy",
    "RecoveryWiringControlOwnership",
    "RecoveryWiringControlLifecycle",
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
    "recovery_activation_gate",
    "recovery_activation_policy",
    "recovery_activation_admission_bridge",
    "recovery_runtime_integration",
    "recovery_executor_integration",
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
    from core.runtime import recovery_activation_integration_bridge
    from core.runtime import recovery_wiring_controller
    from core.runtime import recovery_wiring_status_projection

    assert recovery_wiring_controller.__all__ == ["prepare_recovery_wiring_controller"]
    assert recovery_activation_integration_bridge.__all__ == [
        "prepare_recovery_activation_integration_bridge"
    ]
    assert recovery_wiring_status_projection.__all__ == [
        "prepare_recovery_wiring_status_projection"
    ]


def test_prepare_recovery_wiring_controller_returns_expected_disabled_dict():
    from core.runtime.recovery_wiring_controller import prepare_recovery_wiring_controller

    result = prepare_recovery_wiring_controller()

    assert type(result) is dict
    assert result == {
        "enabled": False,
        "controller_status": "stub",
        "wiring_allowed": False,
        "activation_bound": False,
        "integration_bound": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }


def test_prepare_recovery_activation_integration_bridge_returns_expected_stub_dict():
    from core.runtime.recovery_activation_integration_bridge import (
        prepare_recovery_activation_integration_bridge,
    )

    result = prepare_recovery_activation_integration_bridge()

    assert type(result) is dict
    assert result == {
        "enabled": False,
        "bridge_status": "stub",
        "activation_bound": False,
        "integration_bound": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }


def test_prepare_recovery_wiring_status_projection_returns_expected_disabled_dict():
    from core.runtime.recovery_wiring_status_projection import (
        prepare_recovery_wiring_status_projection,
    )

    result = prepare_recovery_wiring_status_projection()

    assert type(result) is dict
    assert result == {
        "enabled": False,
        "projection_status": "stub",
        "wiring_status": "disabled",
        "activation_status": "disabled",
        "integration_status": "disabled",
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }


def test_all_wiring_activation_execution_and_mutation_flags_are_false():
    from core.runtime.recovery_activation_integration_bridge import (
        prepare_recovery_activation_integration_bridge,
    )
    from core.runtime.recovery_wiring_controller import prepare_recovery_wiring_controller
    from core.runtime.recovery_wiring_status_projection import (
        prepare_recovery_wiring_status_projection,
    )

    results = (
        prepare_recovery_wiring_controller(),
        prepare_recovery_activation_integration_bridge(),
        prepare_recovery_wiring_status_projection(),
    )

    for result in results:
        assert result["enabled"] is False
        assert result["execution_allowed"] is False
        assert result["recovery_enabled"] is False
        assert result["runtime_state_mutated"] is False
        for key in ("wiring_allowed", "activation_bound", "integration_bound"):
            if key in result:
                assert result[key] is False


def test_forbidden_imports_classes_and_dataclasses_are_absent_from_source_text():
    for path in (CONTROLLER_SOURCE, BRIDGE_SOURCE, PROJECTION_SOURCE):
        text = _text(path)
        assert "import " not in text
        assert "from " not in text
        assert "class " not in text
        assert "dataclass" not in text
        for forbidden in FORBIDDEN_IMPORT_TARGETS:
            assert forbidden not in text


def test_inventory_contains_recovery_wiring_control_v1():
    text = _text(INVENTORY)
    assert "recovery_wiring_control_v1" in text


def test_docs_contain_wiring_control_seal_and_readiness_review_v2():
    seal = _text(WIRING_CONTROL_SEAL)
    review = _text(READINESS_REVIEW)

    assert "Runtime Recovery Wiring Control Seal" in seal
    assert "Wiring control is disabled." in seal
    assert "The activation/integration bridge is stub only." in seal
    assert "The status projection is data only." in seal
    assert "No runtime mutation is implemented." in seal
    assert "No recovery execution is implemented." in seal
    assert "Runtime Recovery Wiring Readiness Review v2" in review
    assert "GO / NO-GO decision: GO" in review
    assert "Wiring prerequisites" in review
    assert "Activation-control prerequisites" in review
    assert "Integration prerequisites" in review
    assert "Blockers" in review
    assert "Boundary Matrix" in review
    assert "Risk Table" in review
    assert "Final decision: GO. Next package: Package 293." in review


def test_package_sequence_contains_packages_287_to_292():
    text = _text(PACKAGE_SEQUENCE)
    for package_number in ("287", "288", "289", "290", "291", "292"):
        assert f"## Package {package_number}" in text
    assert "Package 287: Recovery Wiring Control Contract" in text
    assert "Package 288: Recovery Wiring Controller Stub" in text
    assert "Package 289: Recovery Activation -> Integration Bridge Stub" in text
    assert "Package 290: Recovery Wiring Status Projection" in text
    assert "Package 291: Recovery Wiring Control Seal" in text
    assert "Package 292: Recovery Wiring Readiness Review v2" in text


def test_package_292_contains_final_go_to_package_293():
    review = _text(READINESS_REVIEW)
    sequence = _text(PACKAGE_SEQUENCE)

    assert "Final decision: GO. Next package: Package 293." in review
    assert "Final decision: GO. Next package: Package 293." in sequence
