from core.runtime.aer_runtime_recovery_preflight import RECOVERY_PREFLIGHT_ELIGIBILITY_CONTRACT
from core.runtime.aer_runtime_recovery_preflight_report import (
    RECOVERY_PREFLIGHT_REPORT_CONTRACT,
    prepare_recovery_preflight_report,
)


def _preflight():
    return {
        "contract": RECOVERY_PREFLIGHT_ELIGIBILITY_CONTRACT,
        "prepared": True,
        "blocked": False,
        "denied": False,
        "status": "prepared",
        "preflight_only": True,
        "eligible": True,
        "eligibility_state": "eligible",
        "observe_only": True,
        "dry_run": True,
        "single_entry_only": True,
        "runtime_binding_allowed": False,
        "runtime_mainline_wiring_allowed": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "canonical_event": {"event_emitted": False},
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def test_preflight_report_prepared_from_eligibility():
    report = prepare_recovery_preflight_report(_preflight(), report_id="r-1")
    assert report["contract"] == RECOVERY_PREFLIGHT_REPORT_CONTRACT
    assert report["report_id"] == "r-1"
    assert report["prepared"] is True
    assert report["eligible"] is True
    assert report["preflight_report_only"] is True
    assert report["runtime_binding_allowed"] is False
    assert report["runtime_mainline_wiring_allowed"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["canonical_event"]["event_emitted"] is False
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_preflight_report_blocks_invalid_eligibility():
    report = prepare_recovery_preflight_report({"contract": "wrong"})
    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["eligible"] is False
    assert report["preflight_reference"] == {}


def test_preflight_report_denied_status():
    report = prepare_recovery_preflight_report(_preflight(), requested_status="denied")
    assert report["prepared"] is False
    assert report["blocked"] is False
    assert report["denied"] is True
    assert report["recovery_enabled"] is False


def test_preflight_report_has_strict_public_surface():
    import core.runtime.aer_runtime_recovery_preflight_report as module

    assert module.__all__ == [
        "RECOVERY_PREFLIGHT_REPORT_CONTRACT",
        "RECOVERY_PREFLIGHT_REPORT_ALLOWED_STATUSES",
        "prepare_recovery_preflight_report",
    ]
