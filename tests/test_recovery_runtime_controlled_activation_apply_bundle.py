from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_controlled_activation_apply_v1.md")
POLICY_SOURCE = Path("core/runtime/recovery_controlled_activation_apply_policy.py")
PROJECTION_SOURCE = Path("core/runtime/recovery_controlled_activation_apply_projection.py")
AUDIT_SOURCE = Path("core/runtime/recovery_controlled_activation_apply_audit.py")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
BOUNDARY_SEAL = Path("docs/runtime_recovery_controlled_activation_apply_boundary_seal.md")
READINESS_REVIEW = Path(
    "docs/runtime_recovery_controlled_activation_apply_readiness_review.md"
)
GO_REVIEW = Path("docs/runtime_recovery_controlled_activation_apply_go_review.md")
MILESTONE = Path("docs/recovery_controlled_activation_apply_milestone_seal.md")

EXPECTED_POLICY = {
    "enabled": False,
    "apply_status": "reserved",
    "apply_version": "v1_reserved",
    "commit_consumed": False,
    "grant_consumed": False,
    "permit_consumed": False,
    "authorization_confirmed": False,
    "activation_applied": False,
    "activation_allowed": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
    "reason": "future_package",
    "metadata": {},
}

EXPECTED_PROJECTION = {
    "enabled": False,
    "apply_status": "reserved",
    "apply_version": "v1_reserved",
    "commit_consumed": False,
    "grant_consumed": False,
    "permit_consumed": False,
    "authorization_confirmed": False,
    "activation_applied": False,
    "activation_allowed": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
    "reason": "future_package",
}

EXPECTED_AUDIT = {
    "enabled": False,
    "audit_status": "stub",
    "activation_apply_occurred": False,
    "commit_consumed": False,
    "grant_consumed": False,
    "permit_consumed": False,
    "authorization_confirmed": False,
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


def test_packages_369_to_376_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("369", "370", "371", "372", "373", "374", "375", "376"):
        assert f"## Package {package_number}" in text


def test_contract_doc_exists_and_has_required_fields():
    assert CONTRACT.exists()
    text = _text(CONTRACT)
    for field in EXPECTED_POLICY:
        assert field in text
    assert "aer.runtime.recovery.controlled_activation_apply.v1" in text
    assert "Apply status vocabulary" in text
    assert "Commit consumption vocabulary" in text
    assert "Grant consumption vocabulary" in text
    assert "Permit consumption vocabulary" in text
    assert "Authorization boundary vocabulary" in text


def test_runtime_modules_import_and_expose_exact_all():
    from core.runtime import recovery_controlled_activation_apply_audit
    from core.runtime import recovery_controlled_activation_apply_policy
    from core.runtime import recovery_controlled_activation_apply_projection

    assert recovery_controlled_activation_apply_policy.__all__ == [
        "prepare_recovery_controlled_activation_apply_policy"
    ]
    assert recovery_controlled_activation_apply_projection.__all__ == [
        "prepare_recovery_controlled_activation_apply_projection"
    ]
    assert recovery_controlled_activation_apply_audit.__all__ == [
        "prepare_recovery_controlled_activation_apply_audit"
    ]


def test_prepare_functions_return_expected_disabled_metadata():
    from core.runtime.recovery_controlled_activation_apply_audit import (
        prepare_recovery_controlled_activation_apply_audit,
    )
    from core.runtime.recovery_controlled_activation_apply_policy import (
        prepare_recovery_controlled_activation_apply_policy,
    )
    from core.runtime.recovery_controlled_activation_apply_projection import (
        prepare_recovery_controlled_activation_apply_projection,
    )

    results = (
        (prepare_recovery_controlled_activation_apply_policy(), EXPECTED_POLICY),
        (prepare_recovery_controlled_activation_apply_projection(), EXPECTED_PROJECTION),
        (prepare_recovery_controlled_activation_apply_audit(), EXPECTED_AUDIT),
    )

    for result, expected in results:
        assert type(result) is dict
        assert result == expected


def test_prepare_functions_return_fresh_deterministic_dicts():
    from core.runtime.recovery_controlled_activation_apply_policy import (
        prepare_recovery_controlled_activation_apply_policy,
    )

    first = prepare_recovery_controlled_activation_apply_policy()
    second = prepare_recovery_controlled_activation_apply_policy()

    assert first == second
    assert first is not second
    assert first["metadata"] is not second["metadata"]


def test_all_apply_activation_execution_mutation_and_recovery_flags_are_false():
    for result in (EXPECTED_POLICY, EXPECTED_PROJECTION, EXPECTED_AUDIT):
        assert result["enabled"] is False
        assert result["recovery_enabled"] is False
        assert result["runtime_state_mutated"] is False
        assert result["reason"] == "future_package"
        if "commit_consumed" in result:
            assert result["commit_consumed"] is False
        if "grant_consumed" in result:
            assert result["grant_consumed"] is False
        if "permit_consumed" in result:
            assert result["permit_consumed"] is False
        if "authorization_confirmed" in result:
            assert result["authorization_confirmed"] is False
        if "activation_applied" in result:
            assert result["activation_applied"] is False
        if "activation_allowed" in result:
            assert result["activation_allowed"] is False
        if "execution_allowed" in result:
            assert result["execution_allowed"] is False
        if "activation_apply_occurred" in result:
            assert result["activation_apply_occurred"] is False
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


def test_inventory_and_docs_contain_disabled_apply_milestone():
    inventory = _text(INVENTORY)
    boundary = _text(BOUNDARY_SEAL)
    readiness = _text(READINESS_REVIEW)
    go_review = _text(GO_REVIEW)
    milestone = _text(MILESTONE)

    assert "recovery_controlled_activation_apply_v1" in inventory
    assert "Apply cannot enable recovery." in boundary
    assert "Apply cannot mutate runtime state." in boundary
    assert "GO / NO-GO decision: GO for disabled apply layer only." in readiness
    assert "Real apply is not approved." in readiness
    assert "Recovery Runtime remains disabled." in go_review
    assert "Packages 369-376 Completion Map" in milestone
    assert "All new APIs are disabled/data-only." in milestone
    assert "Final decision: GO for disabled controlled activation apply milestone. Next package: Package 377." in milestone
