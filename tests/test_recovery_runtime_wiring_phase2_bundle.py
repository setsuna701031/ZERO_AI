from pathlib import Path


ADMISSION_SOURCE = Path("core/runtime/recovery_execution_admission.py")
DISPATCHER_SOURCE = Path("core/runtime/recovery_execution_dispatcher.py")
COORDINATOR_SOURCE = Path("core/runtime/recovery_execution_coordinator.py")
RUNTIME_COORDINATOR_SOURCE = Path("core/runtime/recovery_runtime_coordinator.py")
AGGREGATOR_SOURCE = Path("core/runtime/recovery_status_aggregator.py")
WIRING_CLOSURE_REVIEW = Path("docs/runtime_recovery_wiring_closure_review.md")
ACTIVATION_GO_REVIEW = Path("docs/runtime_activation_go_review.md")
MILESTONE_SEAL = Path("docs/recovery_runtime_milestone_seal.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

EXPECTED_RESULTS = {
    "admission": {
        "enabled": False,
        "admission_status": "stub",
        "admission_granted": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    },
    "dispatcher": {
        "enabled": False,
        "dispatcher_status": "stub",
        "dispatch_allowed": False,
        "execution_allowed": False,
        "recovery_dispatched": False,
        "runtime_state_mutated": False,
    },
    "coordinator": {
        "enabled": False,
        "coordinator_status": "stub",
        "coordination_active": False,
        "execution_allowed": False,
        "recovery_executed": False,
        "runtime_state_mutated": False,
    },
    "runtime_coordinator": {
        "enabled": False,
        "runtime_coordinator_status": "stub",
        "pipeline_bound": False,
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    },
    "aggregator": {
        "enabled": False,
        "aggregator_status": "stub",
        "status_projection": "disabled",
        "admission_status": "stub",
        "dispatch_status": "stub",
        "coordination_status": "stub",
        "execution_allowed": False,
        "recovery_enabled": False,
        "runtime_state_mutated": False,
    },
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


def test_all_five_runtime_modules_import_and_expose_exact_all():
    from core.runtime import recovery_execution_admission
    from core.runtime import recovery_execution_coordinator
    from core.runtime import recovery_execution_dispatcher
    from core.runtime import recovery_runtime_coordinator
    from core.runtime import recovery_status_aggregator

    assert recovery_execution_admission.__all__ == [
        "prepare_recovery_execution_admission"
    ]
    assert recovery_execution_dispatcher.__all__ == [
        "prepare_recovery_execution_dispatcher"
    ]
    assert recovery_execution_coordinator.__all__ == [
        "prepare_recovery_execution_coordinator"
    ]
    assert recovery_runtime_coordinator.__all__ == [
        "prepare_recovery_runtime_coordinator"
    ]
    assert recovery_status_aggregator.__all__ == ["prepare_recovery_status_aggregator"]


def test_prepare_functions_return_exact_disabled_dicts():
    from core.runtime.recovery_execution_admission import (
        prepare_recovery_execution_admission,
    )
    from core.runtime.recovery_execution_coordinator import (
        prepare_recovery_execution_coordinator,
    )
    from core.runtime.recovery_execution_dispatcher import (
        prepare_recovery_execution_dispatcher,
    )
    from core.runtime.recovery_runtime_coordinator import (
        prepare_recovery_runtime_coordinator,
    )
    from core.runtime.recovery_status_aggregator import (
        prepare_recovery_status_aggregator,
    )

    results = {
        "admission": prepare_recovery_execution_admission(),
        "dispatcher": prepare_recovery_execution_dispatcher(),
        "coordinator": prepare_recovery_execution_coordinator(),
        "runtime_coordinator": prepare_recovery_runtime_coordinator(),
        "aggregator": prepare_recovery_status_aggregator(),
    }

    for name, result in results.items():
        assert type(result) is dict
        assert result == EXPECTED_RESULTS[name]


def test_prepare_functions_return_fresh_dicts():
    from core.runtime.recovery_execution_admission import (
        prepare_recovery_execution_admission,
    )

    first = prepare_recovery_execution_admission()
    second = prepare_recovery_execution_admission()

    assert first == second
    assert first is not second


def test_all_execution_mutation_and_recovery_flags_are_false():
    for result in EXPECTED_RESULTS.values():
        assert result["enabled"] is False
        assert result["execution_allowed"] is False
        assert result["runtime_state_mutated"] is False
        for key in (
            "recovery_enabled",
            "admission_granted",
            "dispatch_allowed",
            "recovery_dispatched",
            "coordination_active",
            "recovery_executed",
            "pipeline_bound",
        ):
            if key in result:
                assert result[key] is False


def test_forbidden_imports_classes_and_dataclasses_are_absent():
    for path in (
        ADMISSION_SOURCE,
        DISPATCHER_SOURCE,
        COORDINATOR_SOURCE,
        RUNTIME_COORDINATOR_SOURCE,
        AGGREGATOR_SOURCE,
    ):
        text = _text(path)
        assert "import " not in text
        assert "from " not in text
        assert "class " not in text
        assert "dataclass" not in text
        assert text.count("def prepare_") == 1
        for forbidden in FORBIDDEN_IMPORT_TARGETS:
            assert forbidden not in text


def test_docs_298_to_300_exist_and_contain_required_statements():
    assert WIRING_CLOSURE_REVIEW.exists()
    assert ACTIVATION_GO_REVIEW.exists()
    assert MILESTONE_SEAL.exists()

    closure = _text(WIRING_CLOSURE_REVIEW)
    go_review = _text(ACTIVATION_GO_REVIEW)
    seal = _text(MILESTONE_SEAL)

    assert "Disabled admission path exists." in closure
    assert "Disabled dispatcher exists." in closure
    assert "Disabled coordinator exists." in closure
    assert "Disabled runtime coordinator exists." in closure
    assert "Disabled status aggregator exists." in closure
    assert "No recovery execution is implemented." in closure
    assert "No runtime state mutation is implemented." in closure
    assert "No persistence is implemented." in closure
    assert "No subprocess is spawned." in closure
    assert "No hooks are registered." in closure
    assert "No endpoints are invoked." in closure

    assert "GO / NO-GO decision: GO" in go_review
    assert "Activation Blockers" in go_review
    assert "Conditions Required Before Enabling Recovery" in go_review
    assert "Risk Matrix" in go_review
    assert "Boundary Matrix" in go_review
    assert "Activation remains disabled." in go_review

    assert "Recovery Runtime Milestone Seal" in seal
    assert "Packages 257-300 Completion Map" in seal
    assert "Contract layer completed." in seal
    assert "Skeleton layer completed." in seal
    assert "Integration layer completed." in seal
    assert "Activation-control layer completed." in seal
    assert "Wiring-control layer completed." in seal
    assert "Phase 2 pipeline stubs completed." in seal
    assert "Final decision: GO. Next package: Package 301." in seal


def test_package_sequence_contains_packages_293_to_300():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("293", "294", "295", "296", "297", "298", "299", "300"):
        assert f"## Package {package_number}" in text

    assert "Package 293: Recovery Execution Admission Stub" in text
    assert "Package 294: Recovery Execution Dispatcher Stub" in text
    assert "Package 295: Recovery Execution Coordinator Stub" in text
    assert "Package 296: Recovery Runtime Coordinator Stub" in text
    assert "Package 297: Recovery Status Aggregator Stub" in text
    assert "Package 298: Recovery Wiring Closure Review" in text
    assert "Package 299: Runtime Activation GO Review" in text
    assert "Package 300: Recovery Runtime Milestone Seal" in text


def test_package_300_contains_final_go_to_package_301():
    seal = _text(MILESTONE_SEAL)
    sequence = _text(PACKAGE_SEQUENCE)

    assert "Final decision: GO. Next package: Package 301." in seal
    assert "Final decision: GO. Next package: Package 301." in sequence
