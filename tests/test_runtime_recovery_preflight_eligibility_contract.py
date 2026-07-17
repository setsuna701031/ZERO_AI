from __future__ import annotations

from pathlib import Path

DOC = Path("docs/contracts/runtime/recovery_preflight_eligibility_v1.md")


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_preflight_eligibility_contract_exists() -> None:
    assert DOC.exists()
    assert "# Runtime Recovery Preflight Eligibility v1" in _text()


def test_preflight_eligibility_contract_pins_schema_and_upstream() -> None:
    text = _text()
    assert "zero.runtime.recovery.preflight_eligibility.v1" in text
    assert "aer.runtime.recovery.preflight_eligibility_report.v1" in text
    assert "aer.runtime.recovery.observation_report.v1" in text
    assert "runtime_recovery_single_entry" in text
    assert "canonical Recovery event" in text


def test_preflight_eligibility_contract_denies_runtime_binding_and_execution() -> None:
    text = _text()
    for phrase in (
        "eligible_for_runtime_binding`: always `False`",
        "eligible_for_recovery_execution`: always `False`",
        "runtime_binding_allowed`: always `False`",
        "recovery_execution_allowed`: always `False`",
        "event_emitted`: always `False`",
        "runtime_surface_touched`: always `False`",
        "executes_recovery`: always `False`",
        "side_effects_performed`: always `False`",
    ):
        assert phrase in text


def test_preflight_eligibility_contract_lists_denied_capabilities() -> None:
    text = _text()
    for phrase in (
        "Recovery execution",
        "Recovery enablement",
        "Runtime mainline wiring",
        "Runtime binding",
        "Route activation",
        "Event emission",
        "Scheduler, Operator, Dispatcher, Supervisor, and Native Runtime calls",
        "Persistence, replay, audit, journal, subprocess, and file IO",
    ):
        assert phrase in text


def test_preflight_eligibility_contract_forbids_behavior() -> None:
    text = _text()
    for phrase in (
        "execute Recovery",
        "enable Recovery by default",
        "bind Runtime",
        "emit Runtime events",
        "mutate Runtime state",
        "call scheduler, operator, dispatcher, supervisor, or native runtime behavior",
        "create or call a Recovery executor",
        "inspect Runtime modules",
        "scan source files",
        "run broad validation",
    ):
        assert phrase in text
