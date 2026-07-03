from pathlib import Path


WIRING_SOURCE = Path("core/runtime/recovery_runtime_wiring.py")
EXECUTOR_SOURCE = Path("core/runtime/recovery_executor.py")
TRANSITION_SOURCE = Path("core/runtime/recovery_state_transition.py")
CHECKPOINT_SOURCE = Path("core/runtime/recovery_checkpoint.py")
SEAL = Path("docs/runtime_recovery_implementation_seal.md")
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
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_all_four_modules_import_and_expose_exact_all():
    from core.runtime import recovery_checkpoint
    from core.runtime import recovery_executor
    from core.runtime import recovery_runtime_wiring
    from core.runtime import recovery_state_transition

    assert recovery_runtime_wiring.__all__ == ["prepare_recovery_runtime_wiring"]
    assert recovery_executor.__all__ == ["prepare_recovery_executor"]
    assert recovery_state_transition.__all__ == ["prepare_recovery_state_transition"]
    assert recovery_checkpoint.__all__ == ["prepare_recovery_checkpoint"]


def test_prepare_recovery_runtime_wiring_returns_expected_inert_dict():
    from core.runtime.recovery_runtime_wiring import prepare_recovery_runtime_wiring

    result = prepare_recovery_runtime_wiring()

    assert type(result) is dict
    assert result == {
        "enabled": False,
        "wiring_status": "inert",
        "runtime_state_mutated": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "gateway_called": False,
        "executor_called": False,
        "metadata": {},
    }


def test_prepare_recovery_executor_returns_expected_skeleton_dict():
    from core.runtime.recovery_executor import prepare_recovery_executor

    result = prepare_recovery_executor()

    assert type(result) is dict
    assert result == {
        "enabled": False,
        "executor_status": "skeleton",
        "execution_allowed": False,
        "recovery_executed": False,
        "runtime_state_mutated": False,
        "metadata": {},
    }


def test_prepare_recovery_state_transition_returns_expected_skeleton_dict():
    from core.runtime.recovery_state_transition import prepare_recovery_state_transition

    result = prepare_recovery_state_transition()

    assert type(result) is dict
    assert result == {
        "enabled": False,
        "transition_status": "skeleton",
        "transition_applied": False,
        "runtime_state_mutated": False,
        "metadata": {},
    }


def test_prepare_recovery_checkpoint_returns_expected_skeleton_dict():
    from core.runtime.recovery_checkpoint import prepare_recovery_checkpoint

    result = prepare_recovery_checkpoint()

    assert type(result) is dict
    assert result == {
        "enabled": False,
        "checkpoint_status": "skeleton",
        "checkpoint_created": False,
        "checkpoint_restored": False,
        "runtime_state_mutated": False,
        "metadata": {},
    }


def test_no_runtime_mutation_flags_are_true():
    from core.runtime.recovery_checkpoint import prepare_recovery_checkpoint
    from core.runtime.recovery_executor import prepare_recovery_executor
    from core.runtime.recovery_runtime_wiring import prepare_recovery_runtime_wiring
    from core.runtime.recovery_state_transition import prepare_recovery_state_transition

    results = (
        prepare_recovery_runtime_wiring(),
        prepare_recovery_executor(),
        prepare_recovery_state_transition(),
        prepare_recovery_checkpoint(),
    )

    for result in results:
        assert result["enabled"] is False
        assert result["runtime_state_mutated"] is False


def test_forbidden_imports_are_absent_from_source_text():
    for path in (WIRING_SOURCE, EXECUTOR_SOURCE, TRANSITION_SOURCE, CHECKPOINT_SOURCE):
        text = _text(path)
        assert "import " not in text
        assert "from " not in text
        for forbidden in FORBIDDEN_IMPORT_TARGETS:
            assert forbidden not in text


def test_no_classes_or_dataclasses_are_defined():
    for path in (WIRING_SOURCE, EXECUTOR_SOURCE, TRANSITION_SOURCE, CHECKPOINT_SOURCE):
        text = _text(path)
        assert "class " not in text
        assert "dataclass" not in text


def test_package_sequence_contains_packages_268_to_272():
    text = _text(PACKAGE_SEQUENCE)
    for package_number in ("268", "269", "270", "271", "272"):
        assert f"## Package {package_number}" in text
    assert "Package 268: Recovery Runtime Inert Wiring" in text
    assert "Package 269: RecoveryExecutor Skeleton" in text
    assert "Package 270: RecoveryStateTransition Skeleton" in text
    assert "Package 271: RecoveryCheckpoint Skeleton" in text
    assert "Package 272: Recovery Implementation Seal" in text


def test_seal_doc_contains_final_go_to_package_273():
    text = _text(SEAL)
    assert "Runtime Recovery Implementation Seal" in text
    assert "all modules are inert" in text.lower()
    assert "No Real Recovery Execution" in text
    assert "No Gateway, Supervisor, Operator, Or Native Wiring" in text
    assert "Final decision: GO. Next package: Package 273." in text
