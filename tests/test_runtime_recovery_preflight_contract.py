from pathlib import Path


def test_preflight_contract_exists_and_pins_non_executing_boundary():
    text = Path("docs/contracts/runtime/recovery_preflight_contract_v1.md").read_text(encoding="utf-8")
    assert "Recovery Preflight Eligibility v1" in text
    assert "`preflight_only: True`" in text
    assert "`runtime_binding_allowed: False`" in text
    assert "`runtime_mainline_wiring_allowed: False`" in text
    assert "`event_emitted: False`" in text
    assert "`recovery_enabled: False`" in text
    assert "`executes_recovery: False`" in text
    assert "does not bind runtime" in text


def test_preflight_contract_has_no_activation_claims():
    text = Path("docs/contracts/runtime/recovery_preflight_contract_v1.md").read_text(encoding="utf-8")
    forbidden = ("Recovery Started", "Runtime Activated", "Scheduler Activated", "real activation")
    for token in forbidden:
        assert token not in text
