from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_controlled_activation_grant_v1.md")
POLICY_SOURCE = Path("core/runtime/recovery_controlled_activation_grant_policy.py")
PROJECTION_SOURCE = Path("core/runtime/recovery_controlled_activation_grant_projection.py")
AUDIT_SOURCE = Path("core/runtime/recovery_controlled_activation_grant_audit.py")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
BOUNDARY_SEAL = Path("docs/runtime_recovery_controlled_activation_grant_boundary_seal.md")
READINESS_REVIEW = Path(
    "docs/runtime_recovery_controlled_activation_grant_readiness_review.md"
)
GO_REVIEW = Path("docs/runtime_recovery_controlled_activation_grant_go_review.md")
MILESTONE = Path("docs/recovery_controlled_activation_grant_milestone_seal.md")

EXPECTED_POLICY = {
    "enabled": False,
    "grant_status": "reserved",
    "grant_version": "v1_reserved",
    "permit_granted": False,
    "activation_granted": False,
    "activation_allowed": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
    "reason": "future_package",
    "metadata": {},
}

EXPECTED_PROJECTION = {
    "enabled": False,
    "grant_status": "reserved",
    "activation_granted": False,
    "activation_allowed": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
    "reason": "future_package",
    "metadata": {},
}

EXPECTED_AUDIT = {
    "enabled": False,
    "audit_status": "stub",
    "grant_issued": False,
    "activation_occurred": False,
    "execution_occurred": False,
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
    "feature_flag",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_packages_353_to_360_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("353", "354", "355", "356", "357", "358", "359", "360"):
        assert f"## Package {package_number}" in text


def test_contract_doc_exists_and_has_required_fields():
    assert CONTRACT.exists()
    text = _text(CONTRACT)
    for field in EXPECTED_POLICY:
        assert field in text
    assert "aer.runtime.recovery.controlled_activation_grant.v1" in text
    assert "Grant status vocabulary" in text


def test_runtime_modules_import_and_expose_exact_all():
    from core.runtime import recovery_controlled_activation_grant_audit
    from core.runtime import recovery_controlled_activation_grant_policy
    from core.runtime import recovery_controlled_activation_grant_projection

    assert recovery_controlled_activation_grant_policy.__all__ == [
        "prepare_recovery_controlled_activation_grant_policy"
    ]
    assert recovery_controlled_activation_grant_projection.__all__ == [
        "prepare_recovery_controlled_activation_grant_projection"
    ]
    assert recovery_controlled_activation_grant_audit.__all__ == [
        "prepare_recovery_controlled_activation_grant_audit"
    ]


def test_prepare_functions_return_expected_disabled_metadata():
    from core.runtime.recovery_controlled_activation_grant_audit import (
        prepare_recovery_controlled_activation_grant_audit,
    )
    from core.runtime.recovery_controlled_activation_grant_policy import (
        prepare_recovery_controlled_activation_grant_policy,
    )
    from core.runtime.recovery_controlled_activation_grant_projection import (
        prepare_recovery_controlled_activation_grant_projection,
    )

    results = (
        (prepare_recovery_controlled_activation_grant_policy(), EXPECTED_POLICY),
        (prepare_recovery_controlled_activation_grant_projection(), EXPECTED_PROJECTION),
        (prepare_recovery_controlled_activation_grant_audit(), EXPECTED_AUDIT),
    )

    for result, expected in results:
        assert type(result) is dict
        assert result == expected


def test_prepare_functions_return_fresh_deterministic_dicts():
    from core.runtime.recovery_controlled_activation_grant_policy import (
        prepare_recovery_controlled_activation_grant_policy,
    )

    first = prepare_recovery_controlled_activation_grant_policy()
    second = prepare_recovery_controlled_activation_grant_policy()

    assert first == second
    assert first is not second
    assert first["metadata"] is not second["metadata"]


def test_all_grant_activation_execution_mutation_and_recovery_flags_are_false():
    for result in (EXPECTED_POLICY, EXPECTED_PROJECTION, EXPECTED_AUDIT):
        assert result["enabled"] is False
        assert result["recovery_enabled"] is False
        assert result["runtime_state_mutated"] is False
        assert result["reason"] == "future_package"
        if "permit_granted" in result:
            assert result["permit_granted"] is False
        if "grant_issued" in result:
            assert result["grant_issued"] is False
        if "activation_granted" in result:
            assert result["activation_granted"] is False
        if "activation_allowed" in result:
            assert result["activation_allowed"] is False
        if "execution_allowed" in result:
            assert result["execution_allowed"] is False
        if "activation_occurred" in result:
            assert result["activation_occurred"] is False
        if "execution_occurred" in result:
            assert result["execution_occurred"] is False


def test_forbidden_imports_classes_and_runtime_wiring_are_absent():
    for path in (POLICY_SOURCE, PROJECTION_SOURCE, AUDIT_SOURCE):
        text = _text(path)
        assert text.count("def prepare_") == 1
        for forbidden in FORBIDDEN_SOURCE_TEXT:
            assert forbidden not in text


def test_inventory_and_docs_contain_disabled_grant_milestone():
    inventory = _text(INVENTORY)
    boundary = _text(BOUNDARY_SEAL)
    readiness = _text(READINESS_REVIEW)
    go_review = _text(GO_REVIEW)
    milestone = _text(MILESTONE)

    assert "recovery_controlled_activation_grant_v1" in inventory
    assert "Grant cannot enable recovery." in boundary
    assert "Grant cannot mutate runtime state." in boundary
    assert "GO / NO-GO decision: GO for disabled grant layer only." in readiness
    assert "Real grant issuance is not approved." in readiness
    assert "Recovery Runtime remains disabled." in go_review
    assert "Packages 353-360 Completion Map" in milestone
    assert "All new APIs are disabled/data-only." in milestone
    assert "Final decision: GO for disabled controlled activation grant milestone. Next package: Package 361." in milestone
