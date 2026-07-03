from pathlib import Path


SOURCE = Path("core/runtime/recovery_controlled_activation_decision_boundary.py")
CONTRACT = Path("docs/contracts/runtime/recovery_controlled_activation_decision_boundary_v1.md")
INVENTORY = Path("docs/contracts/runtime/inventory.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
BOUNDARY_SEAL = Path("docs/runtime_recovery_controlled_activation_decision_boundary_seal.md")
READINESS_REVIEW = Path(
    "docs/runtime_recovery_controlled_activation_decision_boundary_readiness_review.md"
)
MILESTONE = Path("docs/recovery_controlled_activation_decision_boundary_milestone_seal.md")

EXPECTED_BOUNDARY = {
    "enabled": False,
    "decision_status": "blocked",
    "activation_allowed": False,
    "authorization_granted": False,
    "execution_allowed": False,
    "recovery_enabled": False,
    "runtime_state_mutated": False,
    "reason": "controlled_activation_not_enabled",
}

FORBIDDEN_SOURCE_TEXT = (
    "import ",
    "from ",
    "class ",
    "dataclass",
    "executor",
    "scheduler",
    "dispatcher",
    "gateway",
    "bridge",
    "adapter",
    "integration",
    "os.",
    "environ",
    "time.",
    "time(",
    "random",
    "thread",
    "network",
    "subprocess",
    "worker",
    "timer",
    "hook",
    "checkpoint",
    "rollback",
    "retry",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_packages_441_to_448_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("441", "442", "443", "444", "445", "446", "447", "448"):
        assert f"## Package {package_number}" in text

    assert "Recovery Controlled Activation Decision Boundary Finalizer" in text


def test_contract_docs_and_inventory_registration_exist():
    assert CONTRACT.exists()
    assert BOUNDARY_SEAL.exists()
    assert READINESS_REVIEW.exists()
    assert MILESTONE.exists()

    contract = _text(CONTRACT)
    for field in EXPECTED_BOUNDARY:
        assert field in contract
    assert "aer.runtime.recovery.controlled_activation_decision_boundary.v1" in contract
    assert "recovery controlled activation state" in contract
    assert "authorization blocker state" in contract
    assert "readiness state" in contract
    assert "policy state" in contract
    assert "Future activation requires a separate GO package." in contract

    inventory = _text(INVENTORY)
    assert "Runtime Recovery Controlled Activation Decision Boundary" in inventory
    assert "recovery_controlled_activation_decision_boundary_v1" in inventory
    assert "recovery_controlled_activation_decision_boundary.py" in inventory


def test_runtime_module_imports_and_exposes_exact_all():
    from core.runtime import recovery_controlled_activation_decision_boundary

    assert recovery_controlled_activation_decision_boundary.__all__ == [
        "prepare_recovery_controlled_activation_decision_boundary"
    ]


def test_boundary_returns_expected_disabled_output():
    from core.runtime.recovery_controlled_activation_decision_boundary import (
        prepare_recovery_controlled_activation_decision_boundary,
    )

    result = prepare_recovery_controlled_activation_decision_boundary()

    assert type(result) is dict
    assert result == EXPECTED_BOUNDARY


def test_boundary_output_is_deterministic_and_fresh():
    from core.runtime.recovery_controlled_activation_decision_boundary import (
        prepare_recovery_controlled_activation_decision_boundary,
    )

    first = prepare_recovery_controlled_activation_decision_boundary()
    second = prepare_recovery_controlled_activation_decision_boundary(
        recovery_controlled_activation_state={"enabled": False},
        authorization_blocker_state={"authorization_effect_blocked": True},
        readiness_state={"ready": False},
        policy_state={"enabled": False},
    )

    assert first == second
    assert first is not second


def test_disabled_state_has_no_activation_execution_authorization_or_mutation_path():
    assert EXPECTED_BOUNDARY["enabled"] is False
    assert EXPECTED_BOUNDARY["decision_status"] == "blocked"
    assert EXPECTED_BOUNDARY["activation_allowed"] is False
    assert EXPECTED_BOUNDARY["authorization_granted"] is False
    assert EXPECTED_BOUNDARY["execution_allowed"] is False
    assert EXPECTED_BOUNDARY["recovery_enabled"] is False
    assert EXPECTED_BOUNDARY["runtime_state_mutated"] is False
    assert EXPECTED_BOUNDARY["reason"] == "controlled_activation_not_enabled"


def test_no_executor_scheduler_or_runtime_dependency_imports_exist():
    text = _text(SOURCE)

    assert text.count("def prepare_") == 1
    for forbidden in FORBIDDEN_SOURCE_TEXT:
        assert forbidden not in text


def test_docs_preserve_boundary_and_readiness_seal():
    boundary = _text(BOUNDARY_SEAL)
    readiness = _text(READINESS_REVIEW)
    milestone = _text(MILESTONE)

    assert "Decision boundary cannot grant authorization." in boundary
    assert "Decision boundary cannot mutate runtime state." in boundary
    assert "Real activation is not approved." in readiness
    assert "Executor connection is not approved." in readiness
    assert "Scheduler connection is not approved." in readiness
    assert "Packages 441-448 Completion Map" in milestone
    assert "Future activation requires a separate GO package." in milestone
