from pathlib import Path

DOC = Path("docs/runtime_recovery_wiring_inventory.md")


def test_wiring_inventory_exists_and_lists_entry_surfaces():
    text = DOC.read_text(encoding="utf-8")
    assert "Package 220" in text
    for phrase in [
        "runtime_recovery_single_entry",
        "recovery_binding_endpoint",
        "activation_gate",
        "activation_simulation",
        "scheduler_surface",
        "operator_surface",
        "supervisor_surface",
        "native_runtime_surface",
        "watchdog_surface",
    ]:
        assert phrase in text


def test_wiring_inventory_keeps_surfaces_disabled():
    text = DOC.read_text(encoding="utf-8")
    for phrase in [
        "No runtime hook registration",
        "No binding application",
        "No endpoint invocation",
        "No Recovery execution",
        "No event emission",
        "No state mutation",
    ]:
        assert phrase in text
