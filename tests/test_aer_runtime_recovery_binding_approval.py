from pathlib import Path

from core.runtime.aer_runtime_recovery_binding_candidate import prepare_recovery_binding_candidate_report
from core.runtime.aer_runtime_recovery_binding_validator import validate_recovery_binding_candidate_report
from core.runtime.aer_runtime_recovery_binding_approval import (
    RECOVERY_BINDING_APPROVAL_REPORT_CONTRACT,
    prepare_recovery_binding_approval_report,
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


def _validator():
    candidate = prepare_recovery_binding_candidate_report(_plan(), candidate_id="candidate-1")
    return validate_recovery_binding_candidate_report(candidate, validator_id="validator-1")


def test_approval_contract_doc_exists():
    text = Path("docs/contracts/runtime/recovery_binding_approval_v1.md").read_text(encoding="utf-8")
    assert "Package 193" in text
    assert RECOVERY_BINDING_APPROVAL_REPORT_CONTRACT in text
    assert "approval_granted: `False`" in text
    assert "binding_application_allowed: `False`" in text


def test_approval_report_prepared_but_not_granted():
    report = prepare_recovery_binding_approval_report(_validator(), approval_id="approval-1")
    assert report["contract"] == RECOVERY_BINDING_APPROVAL_REPORT_CONTRACT
    assert report["prepared"] is True
    assert report["approval_report_prepared"] is True
    assert report["approval_required"] is True
    assert report["approval_granted"] is False
    assert report["binding_application_allowed"] is False
    assert report["binding_registered"] is False
    assert report["runtime_bound"] is False
    assert report["runtime_mainline_wiring_enabled"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_approval_grant_request_is_denied():
    report = prepare_recovery_binding_approval_report(_validator(), approval_granted=True)
    assert report["prepared"] is False
    assert report["denied"] is True
    assert report["approval_granted"] is False
    assert "prohibited" in report["reason"]


def test_approval_blocks_invalid_validator():
    report = prepare_recovery_binding_approval_report({"status": "prepared"})
    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["binding_validator_reference"] == {}
