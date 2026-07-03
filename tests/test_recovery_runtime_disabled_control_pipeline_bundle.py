from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_control_pipeline_v1.md")
PIPELINE_SOURCE = Path("core/runtime/recovery_control_pipeline.py")
STATUS_SOURCE = Path("core/runtime/recovery_control_pipeline_status.py")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
SAFETY_SEAL = Path("docs/runtime_recovery_control_pipeline_safety_seal.md")
READINESS_REVIEW = Path("docs/runtime_recovery_control_pipeline_readiness_review.md")
MILESTONE_SEAL = Path("docs/recovery_control_pipeline_milestone_seal.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

CONTRACT_NAMES = (
    "RecoveryControlPipelineRequest",
    "RecoveryControlPipelineResult",
    "RecoveryControlPipelineFailure",
    "RecoveryControlPipelinePolicy",
    "RecoveryControlPipelineOwnership",
    "RecoveryControlPipelineLifecycle",
)

EXPECTED_PIPELINE = {
    "enabled": False,
    "pipeline_status": "disabled",
    "enablement_status": "disabled",
    "wiring_status": "disabled",
    "admission_status": "stub",
    "dispatch_status": "stub",
    "coordination_status": "stub",
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
}

EXPECTED_STATUS = {
    "enabled": False,
    "projection_status": "stub",
    "pipeline_status": "disabled",
    "enablement_status": "disabled",
    "wiring_status": "disabled",
    "admission_status": "stub",
    "dispatch_status": "stub",
    "coordination_status": "stub",
    "execution_allowed": False,
    "recovery_enabled": False,
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


def test_two_runtime_modules_import_and_expose_exact_all():
    from core.runtime import recovery_control_pipeline
    from core.runtime import recovery_control_pipeline_status

    assert recovery_control_pipeline.__all__ == ["prepare_recovery_control_pipeline"]
    assert recovery_control_pipeline_status.__all__ == [
        "prepare_recovery_control_pipeline_status"
    ]


def test_prepare_recovery_control_pipeline_returns_expected_disabled_dict():
    from core.runtime.recovery_control_pipeline import prepare_recovery_control_pipeline

    result = prepare_recovery_control_pipeline()

    assert type(result) is dict
    assert result == EXPECTED_PIPELINE


def test_prepare_recovery_control_pipeline_status_returns_expected_disabled_dict():
    from core.runtime.recovery_control_pipeline_status import (
        prepare_recovery_control_pipeline_status,
    )

    result = prepare_recovery_control_pipeline_status()

    assert type(result) is dict
    assert result == EXPECTED_STATUS


def test_prepare_functions_return_fresh_deterministic_dicts():
    from core.runtime.recovery_control_pipeline import prepare_recovery_control_pipeline

    first = prepare_recovery_control_pipeline()
    second = prepare_recovery_control_pipeline()

    assert first == second
    assert first is not second


def test_all_pipeline_execution_mutation_and_recovery_flags_are_false():
    for result in (EXPECTED_PIPELINE, EXPECTED_STATUS):
        assert result["enabled"] is False
        assert result["pipeline_status"] == "disabled"
        assert result["execution_allowed"] is False
        assert result["recovery_enabled"] is False
        assert result["runtime_state_mutated"] is False


def test_forbidden_imports_classes_and_dataclasses_are_absent():
    for path in (PIPELINE_SOURCE, STATUS_SOURCE):
        text = _text(path)
        assert "import " not in text
        assert "from " not in text
        assert "class " not in text
        assert "dataclass" not in text
        assert text.count("def prepare_") == 1
        for forbidden in FORBIDDEN_IMPORT_TARGETS:
            assert forbidden not in text


def test_inventory_contains_recovery_control_pipeline_v1():
    text = _text(INVENTORY)

    assert "recovery_control_pipeline_v1" in text


def test_docs_contain_safety_seal_readiness_review_and_milestone_seal():
    safety = _text(SAFETY_SEAL)
    review = _text(READINESS_REVIEW)
    milestone = _text(MILESTONE_SEAL)

    assert "Runtime Recovery Control Pipeline Safety Seal" in safety
    assert "Pipeline is disabled." in safety
    assert "Enablement is disabled." in safety
    assert "Wiring is disabled." in safety
    assert "Admission is stub only." in safety
    assert "Dispatch is stub only." in safety
    assert "Coordination is stub only." in safety
    assert "Status projection is data only." in safety
    assert "No recovery execution is implemented." in safety
    assert "No runtime mutation is implemented." in safety
    assert "No checkpoint write is implemented." in safety
    assert "No rollback execution is implemented." in safety
    assert "No gateway activation is implemented." in safety
    assert "Package 310 does not add persistence." in safety
    assert "Package 310 does not spawn subprocesses." in safety
    assert "Package 310 does not invoke endpoints." in safety
    assert "Package 310 does not register hooks." in safety

    assert "Runtime Recovery Control Pipeline Readiness Review" in review
    assert "GO / NO-GO decision: GO" in review
    assert "Execution Blockers" in review
    assert "Prerequisites For Future Controlled Activation" in review
    assert "Boundary Matrix" in review
    assert "Risk Table" in review
    assert "Execution remains disabled." in review

    assert "Recovery Control Pipeline Milestone Seal" in milestone
    assert "Packages 301-312 Completion Map" in milestone
    assert "Enablement layer completed." in milestone
    assert "Wiring control layer completed." in milestone
    assert "Disabled control pipeline completed." in milestone
    assert "Final decision: GO. Next package: Package 313." in milestone


def test_package_sequence_contains_packages_307_to_312():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("307", "308", "309", "310", "311", "312"):
        assert f"## Package {package_number}" in text

    assert "Package 307: Recovery Control Pipeline Contract" in text
    assert "Package 308: Recovery Control Pipeline Stub" in text
    assert "Package 309: Recovery Control Pipeline Status Projection" in text
    assert "Package 310: Recovery Control Pipeline Safety Seal" in text
    assert "Package 311: Recovery Control Pipeline Readiness Review" in text
    assert "Package 312: Recovery Control Pipeline Milestone Seal" in text


def test_package_312_contains_final_go_to_package_313():
    milestone = _text(MILESTONE_SEAL)
    sequence = _text(PACKAGE_SEQUENCE)

    assert "Final decision: GO. Next package: Package 313." in milestone
    assert "Final decision: GO. Next package: Package 313." in sequence
