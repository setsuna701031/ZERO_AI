from __future__ import annotations

from pathlib import Path

DOC = Path("docs/contracts/runtime/recovery_preflight_report_v1.md")


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_preflight_report_contract_exists() -> None:
    assert DOC.exists()
    assert "# Runtime Recovery Preflight Report v1" in _text()


def test_preflight_report_contract_pins_schema_and_upstream() -> None:
    text = _text()
    assert "zero.runtime.recovery.preflight_report.v1" in text
    assert "aer.runtime.recovery.preflight_report.v1" in text
    assert "aer.runtime.recovery.preflight_eligibility_report.v1" in text
    assert "runtime_recovery_single_entry" in text
    assert "Package 169 canonical event" in text


def test_preflight_report_contract_never_authorizes_runtime_binding() -> None:
    text = _text()
    for phrase in (
        "runtime_binding_allowed`: always `False`",
        "runtime_mainline_wiring_allowed`: always `False`",
        "recovery_execution_allowed`: always `False`",
        "event_emitted`: always `False`",
        "recovery_enabled`: always `False`",
        "runtime_surface_touched`: always `False`",
        "executes_recovery`: always `False`",
        "side_effects_performed`: always `False`",
    ):
        assert phrase in text


def test_preflight_report_contract_limits_go_meaning() -> None:
    text = _text()
    assert "not permission to activate Recovery" in text
    assert "bind Runtime mainline" in text
    assert "controlled non-executing binding candidate" in text


def test_preflight_report_contract_forbids_behavior() -> None:
    text = _text()
    for phrase in (
        "execute Recovery",
        "enable Recovery by default",
        "bind Runtime",
        "authorize Runtime mainline wiring",
        "emit Runtime events",
        "mutate Runtime state",
        "call scheduler, operator, dispatcher, supervisor, or native runtime behavior",
        "create or call a Recovery executor",
        "inspect Runtime modules",
        "scan source files",
        "run broad validation",
    ):
        assert phrase in text
