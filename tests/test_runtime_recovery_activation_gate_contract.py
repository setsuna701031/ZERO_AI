from pathlib import Path


def test_activation_gate_contract_exists_and_pins_schema() -> None:
    text = Path("docs/contracts/runtime/recovery_activation_gate_v1.md").read_text(encoding="utf-8")
    assert "Package 211" in text
    assert "aer.runtime.recovery.activation_gate.v1" in text
    assert "aer.runtime.recovery.binding_endpoint_invocation_report.v1" in text


def test_activation_gate_contract_forbids_runtime_behavior() -> None:
    text = Path("docs/contracts/runtime/recovery_activation_gate_v1.md").read_text(encoding="utf-8")
    required = [
        "execute Recovery",
        "enable Recovery",
        "open the activation gate",
        "grant activation",
        "register runtime hooks",
        "apply runtime bindings",
        "invoke endpoints",
        "emit runtime events",
        "mutate runtime state",
        "persist, replay, audit, journal, subprocess, or perform file IO",
    ]
    for phrase in required:
        assert phrase in text


def test_activation_gate_contract_requires_disabled_fields() -> None:
    text = Path("docs/contracts/runtime/recovery_activation_gate_v1.md").read_text(encoding="utf-8")
    for phrase in [
        "gate_enabled: False",
        "gate_open: False",
        "activation_allowed: False",
        "endpoint_invoked: False",
        "binding_disabled: True",
        "runtime_hook_registered: False",
        "event_emitted: False",
        "recovery_enabled: False",
    ]:
        assert phrase in text
