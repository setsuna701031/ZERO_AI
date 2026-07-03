from pathlib import Path


REENTRY_REVIEW = Path("docs/runtime_mainline_reentry_review.md")
PHASE_CLOSURE = Path("docs/runtime_recovery_phase_closure_summary.md")
RESUME_GO = Path("docs/runtime_mainline_resume_go_review.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
ARCHITECTURE_CLOSURE = Path("docs/recovery_controlled_activation_architecture_closure_seal.md")
DECISION_BOUNDARY = Path("core/runtime/recovery_controlled_activation_decision_boundary.py")
AUTHORIZATION_BLOCKER = Path(
    "core/runtime/recovery_controlled_activation_authorization_effect_blocker_policy.py"
)

GO_DECISION = "GO for returning to runtime mainline development"
DISABLED_GUARANTEES = (
    "No recovery execution enabled.",
    "No autonomous activation enabled.",
    "No scheduler behavior changed.",
    "No executor behavior changed.",
    "No runtime mutation added.",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_packages_457_to_464_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("457", "458", "459", "460", "461", "462", "463", "464"):
        assert f"## Package {package_number}" in text

    assert "Runtime Mainline Re-entry Review" in text
    assert GO_DECISION in text


def test_review_docs_exist():
    assert REENTRY_REVIEW.exists()
    assert PHASE_CLOSURE.exists()
    assert RESUME_GO.exists()


def test_recovery_closure_evidence_exists():
    assert ARCHITECTURE_CLOSURE.exists()
    assert DECISION_BOUNDARY.exists()
    assert AUTHORIZATION_BLOCKER.exists()

    review = _text(REENTRY_REVIEW)
    assert "Recovery controlled activation closure exists" in review
    assert "Decision boundary exists" in review
    assert "Authorization blocker exists" in review
    assert "Recovery activation remains disabled." in review
    assert "Runtime ownership boundaries remain intact." in review


def test_go_decision_exists_in_all_docs():
    for path in (REENTRY_REVIEW, PHASE_CLOSURE, RESUME_GO):
        text = _text(path)
        assert GO_DECISION in text


def test_recovery_phase_closure_recorded():
    summary = _text(PHASE_CLOSURE)
    assert "Recovery controlled activation architecture closure is recorded." in summary
    assert "Decision boundary is recorded." in summary
    assert "Authorization blocker is recorded." in summary
    assert "recovery controlled activation phase is sealed as disabled architecture only" in summary


def test_runtime_disabled_guarantees_remain_documented():
    for path in (REENTRY_REVIEW, PHASE_CLOSURE, RESUME_GO):
        text = _text(path)
        for guarantee in DISABLED_GUARANTEES:
            assert guarantee in text


def test_no_forbidden_runtime_change_language_is_present():
    go_review = _text(RESUME_GO)
    assert "No new runtime modules." in go_review
    assert "No code path changes." in go_review
    assert "No scheduler edits." in go_review
    assert "No executor edits." in go_review
    assert "No activation edits." in go_review
