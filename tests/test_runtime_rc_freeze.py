from pathlib import Path


RC_FREEZE_REVIEW = Path("docs/runtime_rc_freeze_review.md")
RC_BOUNDARY_LOCK = Path("docs/runtime_rc_boundary_lock.md")
RC_CHANGE_POLICY = Path("docs/runtime_rc_change_policy.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
THIS_TEST = Path("tests/test_runtime_rc_freeze.py")

COMPLETED_AREAS = (
    "Recovery Closure",
    "Mainline Re-entry",
    "Lifecycle",
    "Observability",
    "Operator Interface",
    "Deployment Readiness",
    "Release Readiness",
)

FROZEN_BOUNDARIES = (
    "Scheduler ownership frozen.",
    "Executor ownership frozen.",
    "Operator ownership frozen.",
    "Recovery ownership frozen.",
    "Deployment ownership frozen.",
    "Mutation authority frozen as absent.",
    "Activation authority frozen as disabled.",
)

FORBIDDEN_DIRECT_MODIFICATIONS = (
    "Scheduler bypass forbidden.",
    "Executor bypass forbidden.",
    "Recovery reactivation forbidden.",
    "Authority escalation forbidden.",
    "Uncontrolled mutation forbidden.",
)

CHANGE_REQUIREMENTS = (
    "review gates",
    "rollback requirement",
    "focused test requirement",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _rc_package_text() -> str:
    text = _text(PACKAGE_SEQUENCE)
    marker = "## Package 521"
    assert marker in text
    return text[text.index(marker) :]


def test_packages_521_to_528_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("521", "522", "523", "524", "525", "526", "527", "528"):
        assert f"## Package {package_number}" in text

    assert "Runtime RC Freeze Seal" in text
    assert "Documentation/test only." in text


def test_rc_freeze_docs_exist():
    assert RC_FREEZE_REVIEW.exists()
    assert RC_BOUNDARY_LOCK.exists()
    assert RC_CHANGE_POLICY.exists()


def test_rc_freeze_exists_and_records_baseline():
    text = _text(RC_FREEZE_REVIEW)
    assert "RC Baseline State" in text
    assert "Runtime RC baseline state is frozen" in text
    assert "Frozen Ownership Boundaries" in text
    assert "Future Change Requirements" in text
    for area in COMPLETED_AREAS:
        assert area in text


def test_ownership_boundaries_exist():
    for path in (RC_FREEZE_REVIEW, RC_BOUNDARY_LOCK):
        text = _text(path)
        assert "Scheduler ownership unchanged." in text or "Scheduler ownership frozen." in text
        assert "Executor ownership unchanged." in text or "Executor ownership frozen." in text
        assert "Operator behavior unchanged." in text

    review_text = _text(RC_FREEZE_REVIEW)
    for boundary in FROZEN_BOUNDARIES:
        assert boundary in review_text


def test_activation_remains_disabled():
    for path in (RC_FREEZE_REVIEW, RC_BOUNDARY_LOCK, RC_CHANGE_POLICY):
        text = _text(path)
        assert "Activation remains disabled." in text
        assert "activation behavior" in text.lower()


def test_recovery_remains_closed():
    for path in (RC_FREEZE_REVIEW, RC_BOUNDARY_LOCK, RC_CHANGE_POLICY):
        text = _text(path)
        assert "Recovery remains disabled." in text
        assert "Recovery remains closed." in text or "Recovery surface frozen closed." in text


def test_scheduler_executor_changes_require_future_package():
    for path in (RC_FREEZE_REVIEW, RC_CHANGE_POLICY):
        text = _text(path)
        assert "Scheduler changes require future package approval." in text
        assert "Executor changes require future package approval." in text

    policy_text = _text(RC_CHANGE_POLICY)
    assert "future scheduler package" in policy_text
    assert "future executor package" in policy_text


def test_boundary_lock_forbids_direct_modifications():
    text = _text(RC_BOUNDARY_LOCK)
    for phrase in FORBIDDEN_DIRECT_MODIFICATIONS:
        assert phrase in text


def test_change_policy_requires_review_rollback_and_tests():
    text = _text(RC_CHANGE_POLICY)
    for phrase in CHANGE_REQUIREMENTS:
        assert phrase in text
    assert "Required Review Gates" in text
    assert "Rollback Requirement" in text
    assert "Test Requirement" in text


def test_no_runtime_imports_in_focused_test():
    lines = _text(THIS_TEST).splitlines()
    import_lines = [
        line
        for line in lines
        if line.startswith("import ") or line.startswith("from ")
    ]
    assert import_lines == ["from pathlib import Path"]


def test_rc_package_sequence_records_scope_and_validation():
    text = _rc_package_text()
    assert "no runtime code changes" in text
    assert "no scheduler changes" in text
    assert "no executor changes" in text
    assert "no operator behavior changes" in text
    assert "no activation or deployment behavior" in text
    assert "py -m pytest tests/test_runtime_rc_freeze.py -q" in text
    assert "do not run full suite, nightly, regression, or long validation" in text
