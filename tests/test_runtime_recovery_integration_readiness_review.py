from __future__ import annotations

from pathlib import Path


DOC = Path("docs/runtime_recovery_integration_readiness_review.md")


def _text() -> str:
    assert DOC.exists(), f"missing {DOC}"
    return DOC.read_text(encoding="utf-8")


def test_readiness_review_covers_packages_179_to_181() -> None:
    text = _text()

    assert "Package 182: Runtime Recovery Integration Readiness Review" in text
    assert "Package 179: Runtime Recovery Integration Blueprint" in text
    assert "Package 180: Runtime Recovery Surface Inventory" in text
    assert "Package 181: Recovery Runtime Binding Policy v1" in text


def test_readiness_checklist_keeps_recovery_disabled() -> None:
    text = _text()

    for phrase in [
        "Single entry remains `runtime_recovery_single_entry`",
        "Kill switch remains off/safe by default",
        "Recovery enablement remains false",
        "Canonical event schema remains required",
        "Dry-run boundaries remain preserved",
        "Observation boundaries remain preserved",
        "Runtime surfaces remain unbound",
        "Runtime behavior remains uncalled",
        "Recovery execution remains disabled",
    ]:
        assert phrase in text


def test_readiness_decision_allows_preflight_not_activation() -> None:
    text = _text()

    assert "Final decision: GO." in text
    assert "ready to begin a later non-executing preflight eligibility phase" in text
    assert "not ready for Recovery execution" in text
    assert "not ready for" in text and "Runtime state mutation" in text


def test_readiness_names_next_package_183() -> None:
    text = _text()

    assert "Next package: Package 183." in text
    assert "Runtime Recovery Preflight Eligibility / Non-Executing Binding Guard" in text


def test_readiness_forbids_runtime_calls_and_broad_validation() -> None:
    text = _text()

    for phrase in [
        "executing Recovery",
        "enabling Recovery by default",
        "mutating runtime state",
        "emitting real runtime events",
        "calling Scheduler",
        "calling Operator",
        "calling Dispatcher",
        "calling Supervisor",
        "calling Native Runtime",
        "running broad validation",
    ]:
        assert phrase in text
