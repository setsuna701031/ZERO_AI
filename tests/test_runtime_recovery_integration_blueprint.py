from __future__ import annotations

from pathlib import Path


DOC = Path("docs/runtime_recovery_integration_blueprint.md")


def _text() -> str:
    assert DOC.exists(), f"missing {DOC}"
    return DOC.read_text(encoding="utf-8")


def test_blueprint_defines_single_entry_architecture_without_activation() -> None:
    text = _text()

    assert "Package 179: Runtime Recovery Integration Blueprint" in text
    assert "runtime_recovery_single_entry" in text
    assert "kill switch check" in text
    assert "canonical Recovery event" in text
    assert "preflight eligibility report" in text
    assert "active Recovery execution path is intentionally out of scope" in text


def test_blueprint_seals_owner_boundaries() -> None:
    text = _text()

    required = [
        "Recovery wiring layer",
        "Recovery kill-switch layer",
        "Recovery event route layer",
        "Recovery dry-run layer",
        "Recovery observation layer",
        "Future Runtime integration package",
        "Future Recovery execution package",
    ]
    for phrase in required:
        assert phrase in text


def test_blueprint_escalation_ladder_stops_before_binding_implementation() -> None:
    text = _text()

    for state in [
        "contract_only",
        "prepared",
        "dry_run",
        "observe_only",
        "preflight_only",
        "bound_disabled",
        "bound_guarded",
        "enabled_controlled",
    ]:
        assert state in text

    assert "does not authorize `bound_disabled`, `bound_guarded`, or `enabled_controlled` implementation" in text


def test_blueprint_forbids_runtime_behavior_and_broad_validation() -> None:
    text = _text()

    forbidden = [
        "execute Recovery",
        "enable Recovery by default",
        "mutate runtime state",
        "emit real runtime events",
        "call Scheduler",
        "call Operator",
        "call Dispatcher",
        "call Supervisor",
        "call Native Runtime",
        "run broad validation",
    ]
    for phrase in forbidden:
        assert phrase in text


def test_blueprint_go_and_next_package() -> None:
    text = _text()

    assert "Final decision: GO." in text
    assert "Package 180" in text
    assert "does not authorize active Runtime wiring" in text
