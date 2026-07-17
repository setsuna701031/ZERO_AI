from pathlib import Path


ANCHOR = Path("docs/runtime_mainline_resume_anchor.md")
PLAN = Path("docs/runtime_mainline_continuation_plan.md")
BOUNDARY_SEAL = Path("docs/runtime_mainline_resume_boundary_seal.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")
REENTRY_REVIEW = Path("docs/runtime_mainline_reentry_review.md")
PHASE_CLOSURE = Path("docs/runtime_recovery_phase_closure_summary.md")
RESUME_GO = Path("docs/runtime_mainline_resume_go_review.md")

RESUME_STATUS = (
    "Recovery phase is closed.",
    "Runtime mainline is active again.",
    "Previous disabled guarantees remain unchanged.",
    "Future packages continue from runtime ownership model.",
)

DISABLED_GUARANTEES = (
    "No recovery activation.",
    "No autonomous execution change.",
    "No scheduler behavior change.",
    "No executor behavior change.",
    "No mutation path change.",
)

NEXT_ALLOWED_AREAS = (
    "runtime integration cleanup",
    "runtime lifecycle completion",
    "runtime observability",
    "runtime operator interface",
    "runtime deployment readiness",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_packages_465_to_472_are_explicitly_defined():
    text = _text(PACKAGE_SEQUENCE)

    for package_number in ("465", "466", "467", "468", "469", "470", "471", "472"):
        assert f"## Package {package_number}" in text

    assert "Runtime Mainline Resume Anchor" in text
    assert "runtime mainline continuation anchor" in text


def test_anchor_docs_and_continuation_plan_exist():
    assert ANCHOR.exists()
    assert PLAN.exists()
    assert BOUNDARY_SEAL.exists()


def test_recovery_closure_is_referenced():
    assert REENTRY_REVIEW.exists()
    assert PHASE_CLOSURE.exists()
    assert RESUME_GO.exists()

    anchor = _text(ANCHOR)
    assert "Recovery controlled activation closure exists." in anchor
    assert "Runtime mainline re-entry review exists." in anchor
    assert "Runtime recovery phase closure summary exists." in anchor
    assert "Runtime mainline resume GO review exists." in anchor


def test_runtime_resume_is_recorded():
    for path in (ANCHOR, PLAN, BOUNDARY_SEAL):
        text = _text(path)
        for status in RESUME_STATUS:
            assert status in text


def test_disabled_guarantees_remain_documented():
    for path in (ANCHOR, PLAN, BOUNDARY_SEAL):
        text = _text(path)
        for guarantee in DISABLED_GUARANTEES:
            assert guarantee in text


def test_next_allowed_areas_are_documented():
    for path in (ANCHOR, PLAN, BOUNDARY_SEAL):
        text = _text(path)
        for area in NEXT_ALLOWED_AREAS:
            assert area in text


def test_forbidden_runtime_changes_are_documented():
    boundary = _text(BOUNDARY_SEAL)
    assert "No new core/runtime files." in boundary
    assert "No scheduler edits." in boundary
    assert "No executor edits." in boundary
    assert "No activation edits." in boundary
    assert "No behavior changes." in boundary
