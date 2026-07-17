from pathlib import Path

from core.runtime.aer_runtime_recovery_binding_candidate import (
    RECOVERY_BINDING_CANDIDATE_CONTRACT,
    RECOVERY_BINDING_CANDIDATE_ENTRY,
    prepare_recovery_binding_candidate_report,
)


def _plan():
    return {
        "contract": "aer.runtime.recovery.binding_planner_report.v1",
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


def test_binding_candidate_contract_doc_exists_and_pins_boundaries():
    text = Path("docs/contracts/runtime/recovery_binding_candidate_v1.md").read_text(encoding="utf-8")
    assert "Package 191" in text
    assert RECOVERY_BINDING_CANDIDATE_CONTRACT in text
    assert RECOVERY_BINDING_CANDIDATE_ENTRY in text
    assert "binding_application_allowed: `False`" in text
    assert "recovery_enabled: `False`" in text


def test_binding_candidate_prepared_report_is_passive():
    report = prepare_recovery_binding_candidate_report(_plan(), candidate_id="candidate-1")
    assert report["contract"] == RECOVERY_BINDING_CANDIDATE_CONTRACT
    assert report["prepared"] is True
    assert report["status"] == "prepared"
    assert report["candidate_entry"] == RECOVERY_BINDING_CANDIDATE_ENTRY
    assert report["binding_application_allowed"] is False
    assert report["binding_registered"] is False
    assert report["runtime_bound"] is False
    assert report["runtime_mainline_wiring_enabled"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["approval_required"] is True
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_binding_candidate_blocks_invalid_plan():
    report = prepare_recovery_binding_candidate_report({"status": "prepared"})
    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["status"] == "blocked"
    assert report["binding_plan_reference"] == {}


def test_binding_candidate_denies_non_single_entry():
    report = prepare_recovery_binding_candidate_report(_plan(), requested_entry="scheduler")
    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["candidate_entry"] is None
    assert "single_entry" in report["reason"]
