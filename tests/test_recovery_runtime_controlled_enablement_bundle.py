from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_enablement_v1.md")
GATE_SOURCE = Path("core/runtime/recovery_enablement_gate.py")
POLICY_SOURCE = Path("core/runtime/recovery_enablement_policy.py")
PROJECTION_SOURCE = Path("core/runtime/recovery_enablement_status_projection.py")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
ENABLEMENT_SEAL = Path("docs/runtime_recovery_enablement_seal.md")
READINESS_REVIEW = Path("docs/runtime_recovery_enablement_readiness_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")

CONTRACT_NAMES = (
    "RecoveryEnablementRequest",
    "RecoveryEnablementResult",
    "RecoveryEnablementFailure",
    "RecoveryEnablementPolicy",
    "RecoveryEnablementOwnership",
    "RecoveryEnablementLifecycle",
)

EXPECTED_GATE = {
    "enabled": False,
    "gate_status": "disabled",
    "enablement_allowed": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
}

EXPECTED_POLICY = {
    "enabled": False,
    "policy_status": "stub",
    "enablement_policy_result": "reserved",
    "enablement_allowed": False,
    "execution_allowed": False,
    "runtime_state_mutated": False,
}

EXPECTED_PROJECTION = {
    "enabled": False,
    "projection_status": "stub",
    "enablement_status": "disabled",
    "policy_status": "stub",
    "gate_status": "disabled",
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


def test_three_runtime_modules_import_and_expose_exact_all():
    from core.runtime import recovery_enablement_gate
    from core.runtime import recovery_enablement_policy
    from core.runtime import recovery_enablement_status_projection

    assert recovery_enablement_gate.__all__ == ["prepare_recovery_enablement_gate"]
    assert recovery_enablement_policy.__all__ == ["prepare_recovery_enablement_policy"]
    assert recovery_enablement_status_projection.__all__ == [
        "prepare_recovery_enablement_status_projection"
    ]


def test_prepare_recovery_enablement_gate_returns_expected_disabled_dict():
    from core.runtime.recovery_enablement_gate import prepare_recovery_enablement_gate

    result = prepare_recovery_enablement_gate()

    assert type(result) is dict
    assert result == EXPECTED_GATE


def test_prepare_recovery_enablement_policy_returns_expected_disabled_dict():
    from core.runtime.recovery_enablement_policy import (
        prepare_recovery_enablement_policy,
    )

    result = prepare_recovery_enablement_policy()

    assert type(result) is dict
    assert result == EXPECTED_POLICY


def test_prepare_recovery_enablement_status_projection_returns_expected_disabled_dict():
    from core.runtime.recovery_enablement_status_projection import (
        prepare_recovery_enablement_status_projection,
    )

    result = prepare_recovery_enablement_status_projection()

    assert type(result) is dict
    assert result == EXPECTED_PROJECTION


def test_prepare_functions_return_fresh_deterministic_dicts():
    from core.runtime.recovery_enablement_gate import prepare_recovery_enablement_gate

    first = prepare_recovery_enablement_gate()
    second = prepare_recovery_enablement_gate()

    assert first == second
    assert first is not second


def test_all_enablement_execution_mutation_and_recovery_flags_are_false():
    for result in (EXPECTED_GATE, EXPECTED_POLICY, EXPECTED_PROJECTION):
        assert result["enabled"] is False
        assert result["execution_allowed"] is False
        assert result["runtime_state_mutated"] is False
        for key in ("enablement_allowed", "recovery_enabled"):
            if key in result:
                assert result[key] is False


def test_forbidden_imports_classes_and_dataclasses_are_absent():
    for path in (GATE_SOURCE, POLICY_SOURCE, PROJECTION_SOURCE):
        text = _text(path)
        assert "import " not in text
        assert "from " not in text
        assert "class " not in text
        assert "dataclass" not in text
        assert text.count("def prepare_") == 1
        for forbidden in FORBIDDEN_IMPORT_TARGETS:
            assert forbidden not in text


def test_inventory_contains_recovery_enablement_v1():
    text = _text(INVENTORY)

    assert "recovery_enablement_v1" in text


def test_docs_contain_enablement_seal_and_readiness_review():
    seal = _text(ENABLEMENT_SEAL)
    review = _text(READINESS_REVIEW)

    assert "Runtime Recovery Enablement Seal" in seal
    assert "Enablement exists only as disabled data." in seal
    assert "No recovery execution is implemented." in seal
    assert "No runtime mutation is implemented." in seal
    assert "No checkpoint write is implemented." in seal
    assert "No rollback execution is implemented." in seal
    assert "No gateway activation is implemented." in seal
    assert "Package 305 does not add persistence." in seal
    assert "Package 305 does not spawn subprocesses." in seal
    assert "Package 305 does not invoke endpoints." in seal
    assert "Package 305 does not register hooks." in seal

    assert "Runtime Recovery Enablement Readiness Review" in review
    assert "GO / NO-GO decision: GO" in review
    assert "Enablement Prerequisites" in review
    assert "Execution Blockers" in review
    assert "Boundary Matrix" in review
    assert "Risk Table" in review
    assert "Recovery execution remains disabled." in review
    assert "Final decision: GO. Next package: Package 307." in review


def test_package_sequence_contains_packages_301_to_306():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("301", "302", "303", "304", "305", "306"):
        assert f"## Package {package_number}" in text

    assert "Package 301: Recovery Enablement Contract" in text
    assert "Package 302: Recovery Enablement Gate" in text
    assert "Package 303: Recovery Enablement Policy" in text
    assert "Package 304: Recovery Enablement Status Projection" in text
    assert "Package 305: Recovery Enablement Seal" in text
    assert "Package 306: Recovery Enablement Readiness Review" in text


def test_package_306_contains_final_go_to_package_307():
    review = _text(READINESS_REVIEW)
    sequence = _text(PACKAGE_SEQUENCE)

    assert "Final decision: GO. Next package: Package 307." in review
    assert "Final decision: GO. Next package: Package 307." in sequence
