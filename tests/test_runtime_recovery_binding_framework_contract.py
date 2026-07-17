from pathlib import Path


def test_binding_framework_contract_doc_exists_and_pins_boundaries() -> None:
    text = Path("docs/contracts/runtime/recovery_runtime_binding_framework_v1.md").read_text(encoding="utf-8")

    assert "aer.runtime.recovery.binding_framework.v1" in text
    assert "runtime_recovery_single_entry" in text
    assert "Recovery remains disabled" in text
    assert "Runtime mainline wiring remains disallowed" in text
    assert "Event emission remains disallowed" in text
    assert "Runtime mutation remains disallowed" in text


def test_binding_framework_contract_forbids_runtime_behavior() -> None:
    text = Path("docs/contracts/runtime/recovery_runtime_binding_framework_v1.md").read_text(encoding="utf-8")

    for phrase in (
        "Scheduler, operator, dispatcher, supervisor, and native runtime behavior must not be called",
        "Persistence, replay, audit, journal, subprocess, and file IO are forbidden",
        "Any runtime registration, activation, event emission, or Recovery execution must stop",
    ):
        assert phrase in text
