from pathlib import Path

from core.runtime.aer_runtime_recovery_binding_candidate import prepare_recovery_binding_candidate_report
from core.runtime.aer_runtime_recovery_binding_validator import (
    RECOVERY_BINDING_VALIDATOR_REPORT_CONTRACT,
    validate_recovery_binding_candidate_report,
)


def _plan():
    return {
        "prepared": True,
        "blocked": False,
        "denied": False,
        "status": "prepared",
        "single_entry_only": True,
        "runtime_mainline_wiring_enabled": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _candidate():
    return prepare_recovery_binding_candidate_report(_plan(), candidate_id="candidate-1")


def test_validator_contract_doc_exists():
    text = Path("docs/contracts/runtime/recovery_binding_validator_v1.md").read_text(encoding="utf-8")
    assert "Package 192" in text
    assert RECOVERY_BINDING_VALIDATOR_REPORT_CONTRACT in text
    assert "policy_validated" in text
    assert "preflight_validated" in text
    assert "binding_application_allowed: `False`" in text


def test_validator_prepared_report_is_passive():
    report = validate_recovery_binding_candidate_report(_candidate(), validator_id="validator-1")
    assert report["contract"] == RECOVERY_BINDING_VALIDATOR_REPORT_CONTRACT
    assert report["prepared"] is True
    assert report["candidate_valid"] is True
    assert report["policy_validated"] is True
    assert report["preflight_validated"] is True
    assert report["registry_validated"] is True
    assert report["framework_validated"] is True
    assert report["binding_application_allowed"] is False
    assert report["binding_registered"] is False
    assert report["runtime_bound"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_validator_blocks_invalid_candidate():
    report = validate_recovery_binding_candidate_report({"status": "prepared"})
    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["candidate_valid"] is False
    assert report["binding_candidate_reference"] == {}


def test_validator_denied_status_never_applies_binding():
    report = validate_recovery_binding_candidate_report(_candidate(), requested_status="denied")
    assert report["denied"] is True
    assert report["binding_application_allowed"] is False
    assert report["runtime_bound"] is False
