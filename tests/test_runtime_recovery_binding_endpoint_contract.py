from pathlib import Path


def test_binding_endpoint_contract_exists_and_pins_disabled_endpoint() -> None:
    text = Path("docs/contracts/runtime/recovery_binding_endpoint_v1.md").read_text(encoding="utf-8")
    assert "aer.runtime.recovery.binding_endpoint_report.v1" in text
    assert "runtime_recovery_binding_endpoint" in text
    assert "endpoint_enabled: false" in text
    assert "endpoint_invokable: false" in text
    assert "runtime_hook_registered: false" in text
    assert "recovery_enabled: false" in text


def test_binding_endpoint_contract_forbids_runtime_behavior() -> None:
    text = Path("docs/contracts/runtime/recovery_binding_endpoint_v1.md").read_text(encoding="utf-8")
    required = [
        "must not register a hook",
        "apply a binding",
        "mutate runtime state",
        "emit events",
        "execute Recovery",
        "call Runtime surfaces",
    ]
    for phrase in required:
        assert phrase in text
