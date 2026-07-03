from pathlib import Path


CLOSURE_REVIEW = Path("docs/runtime_recovery_controlled_activation_closure_review.md")
FINAL_GO_REVIEW = Path("docs/recovery_controlled_activation_final_go_review.md")
ARCHITECTURE_SEAL = Path("docs/recovery_controlled_activation_architecture_closure_seal.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
ACTIVATION_CONTRACT = Path("docs/contracts/runtime/recovery_controlled_activation_v1.md")
AUTHORIZATION_BLOCKER = Path(
    "core/runtime/recovery_controlled_activation_authorization_effect_blocker_policy.py"
)
DECISION_BOUNDARY = Path("core/runtime/recovery_controlled_activation_decision_boundary.py")
READINESS_REVIEW = Path(
    "docs/runtime_recovery_controlled_activation_decision_boundary_readiness_review.md"
)
INVENTORY = Path("docs/contracts/runtime/inventory.md")

DISABLED_GUARANTEES = (
    "Runtime activation remains disabled.",
    "Recovery execution remains disabled.",
    "Authorization grant remains disabled.",
    "Mutation remains disabled.",
    "Scheduler wiring remains disabled.",
    "Executor wiring remains disabled.",
)

FORBIDDEN_ENABLING_LANGUAGE = (
    "activation permission is granted",
    "runtime enabling is approved",
    "recovery execution is approved",
    "authorization grant is approved",
    "mutation is approved",
    "scheduler wiring is approved",
    "executor wiring is approved",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_packages_449_to_456_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("449", "450", "451", "452", "453", "454", "455", "456"):
        assert f"## Package {package_number}" in text

    assert "Recovery Controlled Activation Closure Review" in text
    assert "GO for architecture closure only" in text


def test_closure_docs_exist():
    assert CLOSURE_REVIEW.exists()
    assert FINAL_GO_REVIEW.exists()
    assert ARCHITECTURE_SEAL.exists()


def test_closure_review_verifies_required_surfaces():
    for path in (
        ACTIVATION_CONTRACT,
        AUTHORIZATION_BLOCKER,
        DECISION_BOUNDARY,
        READINESS_REVIEW,
        INVENTORY,
    ):
        assert path.exists()

    closure = _text(CLOSURE_REVIEW)
    assert "Activation contract exists" in closure
    assert "Authorization blocker exists" in closure
    assert "Decision boundary exists" in closure
    assert "Readiness review exists" in closure
    assert "Inventory registration exists" in closure
    assert "All activation paths remain disabled." in closure


def test_go_decision_and_disabled_guarantees_exist():
    for path in (CLOSURE_REVIEW, FINAL_GO_REVIEW, ARCHITECTURE_SEAL):
        text = _text(path)
        assert "Final decision: GO for architecture closure only." in text
        for guarantee in DISABLED_GUARANTEES:
            assert guarantee in text


def test_no_activation_permission_or_runtime_enabling_language_exists():
    for path in (CLOSURE_REVIEW, FINAL_GO_REVIEW, ARCHITECTURE_SEAL):
        text = _text(path)
        for phrase in FORBIDDEN_ENABLING_LANGUAGE:
            assert phrase not in text


def test_no_new_runtime_module_is_declared_by_closure_docs():
    for path in (CLOSURE_REVIEW, FINAL_GO_REVIEW, ARCHITECTURE_SEAL):
        text = _text(path)
        assert "No new Python runtime module" in text or "does not add runtime behavior" in text
        assert "No activation code" in text or "activation code" in text
        assert "No executor connection" in text or "executor connection" in text
        assert "No scheduler connection" in text or "scheduler connection" in text


def test_inventory_contains_disabled_chain_registrations():
    inventory = _text(INVENTORY)
    assert "Runtime Recovery Controlled Activation" in inventory
    assert "Runtime Recovery Controlled Activation Authorization Effect Blocker" in inventory
    assert "Runtime Recovery Controlled Activation Decision Boundary" in inventory
    assert "remains disabled" in inventory
