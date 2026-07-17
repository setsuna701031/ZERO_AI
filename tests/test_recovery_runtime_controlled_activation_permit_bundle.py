from pathlib import Path


CONTRACT = Path("docs/contracts/runtime/recovery_controlled_activation_permit_v1.md")
POLICY_SOURCE = Path("core/runtime/recovery_controlled_activation_permit_policy.py")
PROJECTION_SOURCE = Path("core/runtime/recovery_controlled_activation_permit_projection.py")
AUDIT_SOURCE = Path("core/runtime/recovery_controlled_activation_permit_audit.py")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
BOUNDARY_SEAL = Path("docs/runtime_recovery_controlled_activation_permit_boundary_seal.md")
READINESS_REVIEW = Path(
    "docs/runtime_recovery_controlled_activation_permit_readiness_review.md"
)
GO_REVIEW = Path("docs/runtime_recovery_controlled_activation_permit_go_review.md")
MILESTONE = Path("docs/recovery_controlled_activation_permit_milestone_seal.md")

EXPECTED_POLICY = {
    "enabled": False,
    "permit_status": "reserved",
    "permit_version": "v1_reserved",
    "authorization_status": "disabled",
    "activation_allowed": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
    "reason": "future_package",
    "metadata": {},
}

EXPECTED_PROJECTION = {
    "enabled": False,
    "projection_status": "stub",
    "permit_status": "reserved",
    "authorization_status": "disabled",
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
    "permit_status": "reserved",
    "authorization_status": "disabled",
    "activation_allowed": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
    "audit_log_written": False,
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


def test_packages_345_to_352_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("345", "346", "347", "348", "349", "350", "351", "352"):
        assert f"## Package {package_number}" in text


def test_contract_doc_exists_and_has_required_fields():
    assert CONTRACT.exists()
    text = _text(CONTRACT)
    for field in EXPECTED_POLICY:
        assert field in text
    assert "aer.runtime.recovery.controlled_activation_permit.v1" in text
    assert "Permit status vocabulary" in text


def test_runtime_modules_import_and_expose_exact_all():
    from core.runtime import recovery_controlled_activation_permit_audit
    from core.runtime import recovery_controlled_activation_permit_policy
    from core.runtime import recovery_controlled_activation_permit_projection

    assert recovery_controlled_activation_permit_policy.__all__ == [
        "prepare_recovery_controlled_activation_permit_policy"
    ]
    assert recovery_controlled_activation_permit_projection.__all__ == [
        "prepare_recovery_controlled_activation_permit_projection"
    ]
    assert recovery_controlled_activation_permit_audit.__all__ == [
        "prepare_recovery_controlled_activation_permit_audit"
    ]


def test_prepare_functions_return_expected_disabled_metadata():
    from core.runtime.recovery_controlled_activation_permit_audit import (
        prepare_recovery_controlled_activation_permit_audit,
    )
    from core.runtime.recovery_controlled_activation_permit_policy import (
        prepare_recovery_controlled_activation_permit_policy,
    )
    from core.runtime.recovery_controlled_activation_permit_projection import (
        prepare_recovery_controlled_activation_permit_projection,
    )

    results = (
        (prepare_recovery_controlled_activation_permit_policy(), EXPECTED_POLICY),
        (prepare_recovery_controlled_activation_permit_projection(), EXPECTED_PROJECTION),
        (prepare_recovery_controlled_activation_permit_audit(), EXPECTED_AUDIT),
    )

    for result, expected in results:
        assert type(result) is dict
        assert result == expected


def test_prepare_functions_return_fresh_deterministic_dicts():
    from core.runtime.recovery_controlled_activation_permit_policy import (
        prepare_recovery_controlled_activation_permit_policy,
    )

    first = prepare_recovery_controlled_activation_permit_policy()
    second = prepare_recovery_controlled_activation_permit_policy()

    assert first == second
    assert first is not second
    assert first["metadata"] is not second["metadata"]


def test_all_permit_activation_execution_mutation_and_recovery_flags_are_false():
    for result in (EXPECTED_POLICY, EXPECTED_PROJECTION, EXPECTED_AUDIT):
        assert result["enabled"] is False
        assert result["authorization_status"] == "disabled"
        assert result["activation_allowed"] is False
        assert result["execution_allowed"] is False
        assert result["recovery_enabled"] is False
        assert result["runtime_state_mutated"] is False
        assert result["reason"] == "future_package"
        if "audit_log_written" in result:
            assert result["audit_log_written"] is False


def test_forbidden_imports_classes_and_runtime_wiring_are_absent():
    for path in (POLICY_SOURCE, PROJECTION_SOURCE, AUDIT_SOURCE):
        text = _text(path)
        assert text.count("def prepare_") == 1
        for forbidden in FORBIDDEN_SOURCE_TEXT:
            assert forbidden not in text


def test_inventory_and_docs_contain_disabled_permit_milestone():
    inventory = _text(INVENTORY)
    boundary = _text(BOUNDARY_SEAL)
    readiness = _text(READINESS_REVIEW)
    go_review = _text(GO_REVIEW)
    milestone = _text(MILESTONE)

    assert "recovery_controlled_activation_permit_v1" in inventory
    assert "Permit layer cannot allow activation." in boundary
    assert "Permit layer cannot mutate runtime state." in boundary
    assert "GO / NO-GO decision: GO for disabled permit readiness only." in readiness
    assert "Disabled permit layer is structurally ready." in readiness
    assert "Recovery Runtime remains disabled." in go_review
    assert "Packages 345-352 Completion Map" in milestone
    assert "All new APIs are disabled/data-only." in milestone
    assert "Final decision: GO for disabled controlled activation permit milestone. Next package: Package 353." in milestone
