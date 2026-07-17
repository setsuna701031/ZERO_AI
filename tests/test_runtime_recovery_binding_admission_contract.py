from pathlib import Path


def test_binding_admission_contract_exists_and_pins_contract_ids():
    text = Path("docs/contracts/runtime/recovery_binding_admission_v1.md").read_text(encoding="utf-8")
    assert "Package 203" in text
    assert "aer.runtime.recovery.binding_admission_evaluation.v1" in text
    assert "aer.runtime.recovery.binding_admission_report.v1" in text
    assert "runtime_recovery_single_entry" in text


def test_binding_admission_contract_forbids_runtime_actions():
    text = Path("docs/contracts/runtime/recovery_binding_admission_v1.md").read_text(encoding="utf-8")
    required = [
        "execute Recovery",
        "enable Recovery",
        "grant admission",
        "register runtime hooks",
        "apply runtime binding",
        "emit events",
        "mutate runtime state",
    ]
    for phrase in required:
        assert phrase in text


def test_package_sequence_appends_203_to_206():
    text = Path("docs/aer_evolution_v2_package_sequence.md").read_text(encoding="utf-8")
    for package in ("Package 203", "Package 204", "Package 205", "Package 206"):
        assert f"## {package}" in text
    assert "Runtime Recovery Binding Admission Evaluator helper" in text
    assert "Runtime Recovery Binding Admission Readiness Review" in text
