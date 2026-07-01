from pathlib import Path


def test_recovery_disabled_runtime_binding_contract_exists_and_pins_contract_id():
    path = Path("docs/contracts/runtime/recovery_disabled_runtime_binding_v1.md")
    text = path.read_text(encoding="utf-8")
    assert "aer.runtime.recovery.disabled_runtime_binding_report.v1" in text
    assert "runtime_recovery_single_entry" in text


def test_contract_forbids_runtime_binding_behavior():
    text = Path("docs/contracts/runtime/recovery_disabled_runtime_binding_v1.md").read_text(encoding="utf-8")
    required = [
        "runtime hook registration is forbidden",
        "runtime binding application is forbidden",
        "runtime mainline wiring is forbidden",
        "event emission is forbidden",
        "runtime mutation is forbidden",
    ]
    for phrase in required:
        assert phrase in text
