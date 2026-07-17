from core.runtime.aer_runtime_recovery_observation_report import RECOVERY_OBSERVATION_REPORT_CONTRACT
from core.runtime.aer_runtime_recovery_preflight import (
    RECOVERY_PREFLIGHT_ELIGIBILITY_CONTRACT,
    prepare_recovery_preflight_eligibility,
)


def _observation():
    return {
        "contract": RECOVERY_OBSERVATION_REPORT_CONTRACT,
        "prepared": True,
        "blocked": False,
        "denied": False,
        "status": "prepared",
        "observe_only": True,
        "dry_run": True,
        "single_entry_only": True,
        "runtime_surface_touched": False,
        "surface_probe_executed": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "canonical_event": {
            "contract": "aer.runtime.recovery.event.v1",
            "entry_id": "runtime_recovery_single_entry",
            "event_emitted": False,
        },
        "observation_report_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def test_preflight_prepared_from_observation_report():
    report = prepare_recovery_preflight_eligibility(_observation(), preflight_id="pf-1")
    assert report["contract"] == RECOVERY_PREFLIGHT_ELIGIBILITY_CONTRACT
    assert report["preflight_id"] == "pf-1"
    assert report["prepared"] is True
    assert report["eligible"] is True
    assert report["eligibility_state"] == "eligible"
    assert report["runtime_binding_allowed"] is False
    assert report["runtime_mainline_wiring_allowed"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["canonical_event"]["event_emitted"] is False
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_preflight_blocks_invalid_observation():
    report = prepare_recovery_preflight_eligibility({"contract": "wrong"})
    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["eligible"] is False
    assert report["observation_reference"] == {}


def test_preflight_denies_enablement_request():
    report = prepare_recovery_preflight_eligibility(_observation(), request_enablement=True)
    assert report["prepared"] is False
    assert report["denied"] is True
    assert report["recovery_enabled"] is False


def test_preflight_has_strict_public_surface():
    import core.runtime.aer_runtime_recovery_preflight as module

    assert module.__all__ == [
        "RECOVERY_PREFLIGHT_ELIGIBILITY_CONTRACT",
        "RECOVERY_PREFLIGHT_ALLOWED_STATUSES",
        "RECOVERY_PREFLIGHT_DENIED_CAPABILITIES",
        "prepare_recovery_preflight_eligibility",
    ]


def test_preflight_source_has_no_forbidden_runtime_tokens():
    from pathlib import Path

    source = Path("core/runtime/aer_runtime_recovery_preflight.py").read_text(encoding="utf-8")
    forbidden = ("subprocess.", "open(", ".write(", "emit_event", "Scheduler(", "TaskRunner(")
    for token in forbidden:
        assert token not in source
