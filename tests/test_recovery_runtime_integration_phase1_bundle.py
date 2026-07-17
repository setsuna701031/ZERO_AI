from pathlib import Path


RUNTIME_INTEGRATION_SOURCE = Path("core/runtime/recovery_runtime_integration.py")
EXECUTOR_INTEGRATION_SOURCE = Path("core/runtime/recovery_executor_integration.py")
TRANSITION_INTEGRATION_SOURCE = Path("core/runtime/recovery_state_transition_integration.py")
CHECKPOINT_INTEGRATION_SOURCE = Path("core/runtime/recovery_checkpoint_integration.py")
GATEWAY_BRIDGE_SOURCE = Path("core/runtime/recovery_gateway_runtime_bridge.py")
SUPERVISOR_OBSERVATION_SOURCE = Path("core/runtime/recovery_supervisor_observation.py")
INTEGRATION_SEAL = Path("docs/runtime_recovery_integration_seal.md")
ACTIVATION_REVIEW = Path("docs/runtime_recovery_activation_readiness_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

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


def test_all_six_modules_import_and_expose_exact_all():
    from core.runtime import recovery_checkpoint_integration
    from core.runtime import recovery_executor_integration
    from core.runtime import recovery_gateway_runtime_bridge
    from core.runtime import recovery_runtime_integration
    from core.runtime import recovery_state_transition_integration
    from core.runtime import recovery_supervisor_observation

    assert recovery_runtime_integration.__all__ == ["prepare_recovery_runtime_integration"]
    assert recovery_executor_integration.__all__ == ["prepare_recovery_executor_integration"]
    assert recovery_state_transition_integration.__all__ == ["prepare_recovery_state_transition_integration"]
    assert recovery_checkpoint_integration.__all__ == ["prepare_recovery_checkpoint_integration"]
    assert recovery_gateway_runtime_bridge.__all__ == ["prepare_recovery_gateway_runtime_bridge"]
    assert recovery_supervisor_observation.__all__ == ["prepare_recovery_supervisor_observation"]


def test_prepare_recovery_runtime_integration_returns_expected_disabled_stub_dict():
    from core.runtime.recovery_runtime_integration import prepare_recovery_runtime_integration

    result = prepare_recovery_runtime_integration()

    assert type(result) is dict
    assert result == {
        "enabled": False,
        "integration_status": "stub",
        "wiring_active": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }


def test_prepare_recovery_executor_integration_returns_expected_disabled_stub_dict():
    from core.runtime.recovery_executor_integration import prepare_recovery_executor_integration

    result = prepare_recovery_executor_integration()

    assert type(result) is dict
    assert result == {
        "enabled": False,
        "executor_integration_status": "stub",
        "executor_bound": False,
        "execution_allowed": False,
        "recovery_executed": False,
        "runtime_state_mutated": False,
    }


def test_prepare_recovery_state_transition_integration_returns_expected_disabled_stub_dict():
    from core.runtime.recovery_state_transition_integration import (
        prepare_recovery_state_transition_integration,
    )

    result = prepare_recovery_state_transition_integration()

    assert type(result) is dict
    assert result == {
        "enabled": False,
        "state_transition_integration_status": "stub",
        "transition_bound": False,
        "transition_applied": False,
        "runtime_state_mutated": False,
    }


def test_prepare_recovery_checkpoint_integration_returns_expected_disabled_stub_dict():
    from core.runtime.recovery_checkpoint_integration import prepare_recovery_checkpoint_integration

    result = prepare_recovery_checkpoint_integration()

    assert type(result) is dict
    assert result == {
        "enabled": False,
        "checkpoint_integration_status": "stub",
        "checkpoint_bound": False,
        "checkpoint_created": False,
        "checkpoint_restored": False,
        "runtime_state_mutated": False,
    }


def test_prepare_recovery_gateway_runtime_bridge_returns_expected_disabled_stub_dict():
    from core.runtime.recovery_gateway_runtime_bridge import prepare_recovery_gateway_runtime_bridge

    result = prepare_recovery_gateway_runtime_bridge()

    assert type(result) is dict
    assert result == {
        "enabled": False,
        "bridge_status": "stub",
        "gateway_bound": False,
        "runtime_bound": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    }


def test_prepare_recovery_supervisor_observation_returns_expected_disabled_stub_dict():
    from core.runtime.recovery_supervisor_observation import prepare_recovery_supervisor_observation

    result = prepare_recovery_supervisor_observation()

    assert type(result) is dict
    assert result == {
        "enabled": False,
        "observation_status": "stub",
        "supervisor_bound": False,
        "observation_active": False,
        "recovery_controlled": False,
        "runtime_state_mutated": False,
    }


def test_all_mutation_execution_and_activation_flags_are_false():
    from core.runtime.recovery_checkpoint_integration import prepare_recovery_checkpoint_integration
    from core.runtime.recovery_executor_integration import prepare_recovery_executor_integration
    from core.runtime.recovery_gateway_runtime_bridge import prepare_recovery_gateway_runtime_bridge
    from core.runtime.recovery_runtime_integration import prepare_recovery_runtime_integration
    from core.runtime.recovery_state_transition_integration import (
        prepare_recovery_state_transition_integration,
    )
    from core.runtime.recovery_supervisor_observation import prepare_recovery_supervisor_observation

    results = (
        prepare_recovery_runtime_integration(),
        prepare_recovery_executor_integration(),
        prepare_recovery_state_transition_integration(),
        prepare_recovery_checkpoint_integration(),
        prepare_recovery_gateway_runtime_bridge(),
        prepare_recovery_supervisor_observation(),
    )

    for result in results:
        assert result["enabled"] is False
        assert result["runtime_state_mutated"] is False
        for key in (
            "execution_allowed",
            "recovery_enabled",
            "recovery_executed",
            "transition_applied",
            "checkpoint_created",
            "checkpoint_restored",
            "gateway_bound",
            "runtime_bound",
            "supervisor_bound",
            "observation_active",
            "recovery_controlled",
            "wiring_active",
            "executor_bound",
            "transition_bound",
            "checkpoint_bound",
        ):
            if key in result:
                assert result[key] is False


def test_forbidden_imports_are_absent_from_source_text():
    sources = (
        RUNTIME_INTEGRATION_SOURCE,
        EXECUTOR_INTEGRATION_SOURCE,
        TRANSITION_INTEGRATION_SOURCE,
        CHECKPOINT_INTEGRATION_SOURCE,
        GATEWAY_BRIDGE_SOURCE,
        SUPERVISOR_OBSERVATION_SOURCE,
    )
    for path in sources:
        text = _text(path)
        assert "import " not in text
        assert "from " not in text
        assert "class " not in text
        assert "dataclass" not in text
        for forbidden in FORBIDDEN_IMPORT_TARGETS:
            assert forbidden not in text


def test_docs_contain_integration_seal_and_activation_readiness_review():
    seal = _text(INTEGRATION_SEAL)
    review = _text(ACTIVATION_REVIEW)

    assert "Runtime Recovery Integration Seal" in seal
    assert "All integration modules are disabled." in seal
    assert "No checkpoint write is implemented." in seal
    assert "No supervisor control is implemented." in seal
    assert "Runtime Recovery Activation Readiness Review" in review
    assert "GO / NO-GO readiness decision: GO" in review
    assert "activation blockers" in review.lower()


def test_package_sequence_contains_packages_273_to_280():
    text = _text(PACKAGE_SEQUENCE)
    for package_number in ("273", "274", "275", "276", "277", "278", "279", "280"):
        assert f"## Package {package_number}" in text
    assert "Package 273: Recovery Runtime Wiring Activation Stub" in text
    assert "Package 274: RecoveryExecutor Integration Stub" in text
    assert "Package 275: RecoveryStateTransition Integration Stub" in text
    assert "Package 276: RecoveryCheckpoint Integration Stub" in text
    assert "Package 277: RecoveryGateway Runtime Bridge Stub" in text
    assert "Package 278: Supervisor Observation Stub" in text
    assert "Package 279: Recovery Integration Seal" in text
    assert "Package 280: Recovery Activation Readiness Review" in text


def test_package_280_contains_final_go_to_package_281():
    review = _text(ACTIVATION_REVIEW)
    sequence = _text(PACKAGE_SEQUENCE)

    assert "Final decision: GO. Next package: Package 281." in review
    assert "Final decision: GO. Next package: Package 281." in sequence
