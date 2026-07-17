from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_controlled_activation_admission_decision_v1.md")
POLICY_SOURCE = Path("core/runtime/recovery_controlled_activation_admission_decision_policy.py")
PROJECTION_SOURCE = Path(
    "core/runtime/recovery_controlled_activation_admission_decision_projection.py"
)
AUDIT_SOURCE = Path("core/runtime/recovery_controlled_activation_admission_decision_audit.py")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
BOUNDARY_SEAL = Path(
    "docs/runtime_recovery_controlled_activation_admission_decision_boundary_seal.md"
)
READINESS_REVIEW = Path(
    "docs/runtime_recovery_controlled_activation_admission_decision_readiness_review.md"
)
GO_REVIEW = Path("docs/runtime_recovery_controlled_activation_admission_decision_go_review.md")
MILESTONE = Path("docs/recovery_controlled_activation_admission_decision_milestone_seal.md")

EXPECTED_POLICY = {
    "enabled": False,
    "admission_decision_status": "reserved",
    "admission_decision_version": "v1_reserved",
    "admission_decision_eligible": False,
    "admission_decision_recorded": False,
    "admission_decision_effective": False,
    "admission_approved": False,
    "authorization_effective": False,
    "activation_allowed": False,
    "execution_permission_granted": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
    "reason": "future_package",
    "metadata": {},
}

EXPECTED_PROJECTION = {
    "enabled": False,
    "admission_decision_status": "reserved",
    "admission_decision_version": "v1_reserved",
    "admission_decision_eligible": False,
    "admission_decision_recorded": False,
    "admission_decision_effective": False,
    "admission_approved": False,
    "authorization_effective": False,
    "activation_allowed": False,
    "execution_permission_granted": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
    "reason": "future_package",
}

EXPECTED_AUDIT = {
    "enabled": False,
    "audit_status": "stub",
    "admission_decision_took_effect": False,
    "admission_occurred": False,
    "authorization_effective": False,
    "activation_occurred": False,
    "execution_permission_granted": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
    "reason": "future_package",
    "metadata": {},
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
    "worker",
    "hook",
    "checkpoint",
    "rollback",
    "retry",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_packages_401_to_408_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("401", "402", "403", "404", "405", "406", "407", "408"):
        assert f"## Package {package_number}" in text

    assert "Recovery Controlled Activation Admission Decision Implementation Bundle" in text


def test_contract_doc_exists_and_has_required_fields():
    assert CONTRACT.exists()
    text = _text(CONTRACT)
    for field in EXPECTED_POLICY:
        assert field in text
    assert "aer.runtime.recovery.controlled_activation_admission_decision.v1" in text
    assert "decision record, status, and eligibility information only" in text
    assert "Non-Authorization Boundary" in text
    assert "Non-Activation Boundary" in text
    assert "Non-Execution Boundary" in text
    assert "Runtime Mutation Boundary" in text


def test_runtime_modules_import_and_expose_exact_all():
    from core.runtime import recovery_controlled_activation_admission_decision_audit
    from core.runtime import recovery_controlled_activation_admission_decision_policy
    from core.runtime import recovery_controlled_activation_admission_decision_projection

    assert recovery_controlled_activation_admission_decision_policy.__all__ == [
        "prepare_recovery_controlled_activation_admission_decision_policy"
    ]
    assert recovery_controlled_activation_admission_decision_projection.__all__ == [
        "prepare_recovery_controlled_activation_admission_decision_projection"
    ]
    assert recovery_controlled_activation_admission_decision_audit.__all__ == [
        "prepare_recovery_controlled_activation_admission_decision_audit"
    ]


def test_prepare_functions_return_expected_disabled_metadata():
    from core.runtime.recovery_controlled_activation_admission_decision_audit import (
        prepare_recovery_controlled_activation_admission_decision_audit,
    )
    from core.runtime.recovery_controlled_activation_admission_decision_policy import (
        prepare_recovery_controlled_activation_admission_decision_policy,
    )
    from core.runtime.recovery_controlled_activation_admission_decision_projection import (
        prepare_recovery_controlled_activation_admission_decision_projection,
    )

    results = (
        (prepare_recovery_controlled_activation_admission_decision_policy(), EXPECTED_POLICY),
        (
            prepare_recovery_controlled_activation_admission_decision_projection(),
            EXPECTED_PROJECTION,
        ),
        (prepare_recovery_controlled_activation_admission_decision_audit(), EXPECTED_AUDIT),
    )

    for result, expected in results:
        assert type(result) is dict
        assert result == expected


def test_prepare_functions_return_fresh_deterministic_dicts():
    from core.runtime.recovery_controlled_activation_admission_decision_policy import (
        prepare_recovery_controlled_activation_admission_decision_policy,
    )

    first = prepare_recovery_controlled_activation_admission_decision_policy()
    second = prepare_recovery_controlled_activation_admission_decision_policy()

    assert first == second
    assert first is not second
    assert first["metadata"] is not second["metadata"]


def test_outputs_are_decision_record_only_and_disabled():
    for result in (EXPECTED_POLICY, EXPECTED_PROJECTION, EXPECTED_AUDIT):
        assert result["enabled"] is False
        assert result["recovery_enabled"] is False
        assert result["runtime_state_mutated"] is False
        assert result["reason"] == "future_package"
        if "admission_decision_eligible" in result:
            assert result["admission_decision_eligible"] is False
        if "admission_decision_recorded" in result:
            assert result["admission_decision_recorded"] is False
        if "admission_decision_effective" in result:
            assert result["admission_decision_effective"] is False
        if "admission_decision_took_effect" in result:
            assert result["admission_decision_took_effect"] is False
        if "admission_approved" in result:
            assert result["admission_approved"] is False
        if "admission_occurred" in result:
            assert result["admission_occurred"] is False
        if "authorization_effective" in result:
            assert result["authorization_effective"] is False
        if "activation_allowed" in result:
            assert result["activation_allowed"] is False
        if "activation_occurred" in result:
            assert result["activation_occurred"] is False
        if "execution_permission_granted" in result:
            assert result["execution_permission_granted"] is False


def test_forbidden_imports_classes_and_runtime_wiring_are_absent():
    for path in (POLICY_SOURCE, PROJECTION_SOURCE, AUDIT_SOURCE):
        text = _text(path)
        assert text.count("def prepare_") == 1
        for forbidden in FORBIDDEN_SOURCE_TEXT:
            assert forbidden not in text


def test_inventory_and_docs_contain_disabled_admission_decision_milestone():
    inventory = _text(INVENTORY)
    boundary = _text(BOUNDARY_SEAL)
    readiness = _text(READINESS_REVIEW)
    go_review = _text(GO_REVIEW)
    milestone = _text(MILESTONE)

    assert "recovery_controlled_activation_admission_decision_v1" in inventory
    assert "Admission decision cannot make authorization effective." in boundary
    assert "Admission decision cannot mutate runtime state." in boundary
    assert "GO / NO-GO decision: GO for disabled admission decision record layer only." in readiness
    assert "Real admission decision is not approved." in readiness
    assert "Recovery Runtime remains disabled." in go_review
    assert "Packages 401-408 Completion Map" in milestone
    assert "All new APIs are disabled/data-only." in milestone
    assert "Final decision: GO for disabled controlled activation admission decision milestone. Next package: Package 409 only after explicit package definition exists." in milestone
