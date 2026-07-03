from pathlib import Path


CONTRACT = Path(
    "docs/contracts/runtime/recovery_controlled_activation_authorization_boundary_v1.md"
)
CONTRACT_SOURCE = Path(
    "core/runtime/recovery_controlled_activation_authorization_boundary_contract.py"
)
POLICY_SOURCE = Path("core/runtime/recovery_controlled_activation_authorization_boundary_policy.py")
PROJECTION_SOURCE = Path(
    "core/runtime/recovery_controlled_activation_authorization_boundary_projection.py"
)
AUDIT_SOURCE = Path("core/runtime/recovery_controlled_activation_authorization_boundary_audit.py")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
BOUNDARY_SEAL = Path("docs/runtime_recovery_controlled_activation_authorization_boundary_seal.md")
READINESS_REVIEW = Path(
    "docs/runtime_recovery_controlled_activation_authorization_boundary_readiness_review.md"
)
GO_REVIEW = Path("docs/runtime_recovery_controlled_activation_authorization_boundary_go_review.md")
MILESTONE = Path(
    "docs/recovery_controlled_activation_authorization_boundary_implementation_bundle_milestone_seal.md"
)

EXPECTED_CONTRACT = {
    "enabled": False,
    "authorization_boundary_status": "reserved",
    "authorization_boundary_version": "v1_reserved",
    "authorization_boundary_eligible": False,
    "authorization_recorded": False,
    "authorization_effective": False,
    "execution_grant_created": False,
    "execution_permission_granted": False,
    "runtime_permission_escalated": False,
    "activation_allowed": False,
    "activation_occurred": False,
    "recovery_execution_allowed": False,
    "recovery_executed": False,
    "runtime_state_mutated": False,
    "reason": "future_package",
    "metadata": {},
}

EXPECTED_POLICY = dict(EXPECTED_CONTRACT)
EXPECTED_PROJECTION = {
    key: value for key, value in EXPECTED_CONTRACT.items() if key != "metadata"
}
EXPECTED_AUDIT = {
    "enabled": False,
    "audit_status": "stub",
    "authorization_boundary_took_effect": False,
    "authorization_recorded": False,
    "authorization_effective": False,
    "execution_grant_created": False,
    "execution_permission_granted": False,
    "runtime_permission_escalated": False,
    "activation_occurred": False,
    "recovery_execution_allowed": False,
    "recovery_executed": False,
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


def test_packages_417_to_424_are_explicitly_defined_and_authorized():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("417", "418", "419", "420", "421", "422", "423", "424"):
        assert f"## Package {package_number}" in text

    assert "Recovery Controlled Activation Authorization Boundary Implementation Bundle" in text
    assert "allow a future implementation bundle to create the authorization boundary contract" in text
    assert "allow a future implementation bundle to create the focused bundle test" in text


def test_contract_doc_exists_and_has_required_fields():
    assert CONTRACT.exists()
    text = _text(CONTRACT)
    for field in EXPECTED_CONTRACT:
        assert field in text
    assert "aer.runtime.recovery.controlled_activation_authorization_boundary.v1" in text
    assert "authorization record, status, and eligibility information only" in text
    assert "Authorization Record Boundary" in text
    assert "Non-Activation Boundary" in text
    assert "Non-Execution Boundary" in text
    assert "Runtime Mutation Boundary" in text


def test_runtime_modules_import_and_expose_exact_all():
    from core.runtime import recovery_controlled_activation_authorization_boundary_audit
    from core.runtime import recovery_controlled_activation_authorization_boundary_contract
    from core.runtime import recovery_controlled_activation_authorization_boundary_policy
    from core.runtime import recovery_controlled_activation_authorization_boundary_projection

    assert recovery_controlled_activation_authorization_boundary_contract.__all__ == [
        "prepare_recovery_controlled_activation_authorization_boundary_contract"
    ]
    assert recovery_controlled_activation_authorization_boundary_policy.__all__ == [
        "prepare_recovery_controlled_activation_authorization_boundary_policy"
    ]
    assert recovery_controlled_activation_authorization_boundary_projection.__all__ == [
        "prepare_recovery_controlled_activation_authorization_boundary_projection"
    ]
    assert recovery_controlled_activation_authorization_boundary_audit.__all__ == [
        "prepare_recovery_controlled_activation_authorization_boundary_audit"
    ]


def test_prepare_functions_return_expected_disabled_metadata():
    from core.runtime.recovery_controlled_activation_authorization_boundary_audit import (
        prepare_recovery_controlled_activation_authorization_boundary_audit,
    )
    from core.runtime.recovery_controlled_activation_authorization_boundary_contract import (
        prepare_recovery_controlled_activation_authorization_boundary_contract,
    )
    from core.runtime.recovery_controlled_activation_authorization_boundary_policy import (
        prepare_recovery_controlled_activation_authorization_boundary_policy,
    )
    from core.runtime.recovery_controlled_activation_authorization_boundary_projection import (
        prepare_recovery_controlled_activation_authorization_boundary_projection,
    )

    results = (
        (
            prepare_recovery_controlled_activation_authorization_boundary_contract(),
            EXPECTED_CONTRACT,
        ),
        (prepare_recovery_controlled_activation_authorization_boundary_policy(), EXPECTED_POLICY),
        (
            prepare_recovery_controlled_activation_authorization_boundary_projection(),
            EXPECTED_PROJECTION,
        ),
        (prepare_recovery_controlled_activation_authorization_boundary_audit(), EXPECTED_AUDIT),
    )

    for result, expected in results:
        assert type(result) is dict
        assert result == expected


def test_prepare_functions_return_fresh_deterministic_dicts():
    from core.runtime.recovery_controlled_activation_authorization_boundary_contract import (
        prepare_recovery_controlled_activation_authorization_boundary_contract,
    )

    first = prepare_recovery_controlled_activation_authorization_boundary_contract()
    second = prepare_recovery_controlled_activation_authorization_boundary_contract()

    assert first == second
    assert first is not second
    assert first["metadata"] is not second["metadata"]


def test_outputs_are_authorization_record_only_and_disabled():
    for result in (EXPECTED_CONTRACT, EXPECTED_POLICY, EXPECTED_PROJECTION, EXPECTED_AUDIT):
        assert result["enabled"] is False
        assert result["authorization_effective"] is False
        assert result["execution_grant_created"] is False
        assert result["execution_permission_granted"] is False
        assert result["runtime_permission_escalated"] is False
        assert result["activation_occurred"] is False
        assert result["recovery_execution_allowed"] is False
        assert result["recovery_executed"] is False
        assert result["runtime_state_mutated"] is False
        assert result["reason"] == "future_package"


def test_forbidden_imports_classes_and_runtime_wiring_are_absent():
    for path in (CONTRACT_SOURCE, POLICY_SOURCE, PROJECTION_SOURCE, AUDIT_SOURCE):
        text = _text(path)
        assert text.count("def prepare_") == 1
        for forbidden in FORBIDDEN_SOURCE_TEXT:
            assert forbidden not in text


def test_inventory_and_docs_contain_disabled_authorization_boundary_milestone():
    inventory = _text(INVENTORY)
    boundary = _text(BOUNDARY_SEAL)
    readiness = _text(READINESS_REVIEW)
    go_review = _text(GO_REVIEW)
    milestone = _text(MILESTONE)

    assert "recovery_controlled_activation_authorization_boundary_v1" in inventory
    assert "Authorization boundary cannot make authorization effective." in boundary
    assert "Authorization boundary cannot mutate runtime state." in boundary
    assert "GO / NO-GO decision: GO for disabled authorization boundary record layer only." in readiness
    assert "Execution grant is not approved." in readiness
    assert "Recovery Runtime remains disabled." in go_review
    assert "Packages 417-424 Completion Map" in milestone
    assert "All new APIs are disabled/data-only." in milestone
    assert "Authorization boundary is authorization record only." in milestone
    assert "Final decision: GO for disabled controlled activation authorization boundary implementation bundle milestone. Next package requires explicit package definition." in milestone
