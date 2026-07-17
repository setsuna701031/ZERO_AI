from core.runtime.aer_runtime_recovery_binding_admission import (
    RECOVERY_BINDING_ADMISSION_ENTRY,
    prepare_recovery_binding_admission_evaluation,
)
from core.runtime.aer_runtime_recovery_binding_admission_report import (
    RECOVERY_BINDING_ADMISSION_REPORT_CONTRACT,
    prepare_recovery_binding_admission_report,
)


def _canonical_event():
    return {
        "contract": "aer.runtime.recovery.event.v1",
        "entry_id": RECOVERY_BINDING_ADMISSION_ENTRY,
        "route_id": "route-1",
        "source_surface": "runtime",
        "gate_state": "off",
        "event_emitted": False,
    }


def _disabled_binding():
    return {
        "contract": "aer.runtime.recovery.disabled_runtime_binding_report.v1",
        "prepared": True,
        "blocked": False,
        "denied": False,
        "status": "prepared",
        "single_entry_only": True,
        "binding_entry": RECOVERY_BINDING_ADMISSION_ENTRY,
        "binding_skeleton": True,
        "binding_enabled": False,
        "bound_to_runtime": False,
        "runtime_hook_registered": False,
        "runtime_binding_applied": False,
        "recovery_enabled": False,
        "event_emitted": False,
        "canonical_event": _canonical_event(),
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _binding_points():
    return {
        "contract": "aer.runtime.recovery.runtime_binding_points_report.v1",
        "prepared": True,
        "blocked": False,
        "denied": False,
        "status": "prepared",
        "single_entry_only": True,
        "binding_entry": RECOVERY_BINDING_ADMISSION_ENTRY,
        "binding_points_declared": True,
        "binding_points_registered": False,
        "runtime_hook_registered": False,
        "runtime_binding_applied": False,
        "runtime_surface_touched": False,
        "binding_enabled": False,
        "recovery_enabled": False,
        "event_emitted": False,
        "canonical_event": _canonical_event(),
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _evaluation():
    return prepare_recovery_binding_admission_evaluation(_disabled_binding(), _binding_points())


def test_binding_admission_report_prepared_but_not_granted():
    report = prepare_recovery_binding_admission_report(_evaluation())
    assert report["contract"] == RECOVERY_BINDING_ADMISSION_REPORT_CONTRACT
    assert report["prepared"] is True
    assert report["status"] == "prepared"
    assert report["admission_reported"] is True
    assert report["admission_granted"] is False
    assert report["admission_allowed"] is False
    assert report["binding_admitted"] is False
    assert report["runtime_accepts_binding"] is False
    assert report["runtime_hook_registered"] is False
    assert report["runtime_binding_applied"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["canonical_event"]["event_emitted"] is False
    assert report["admission_report_only"] is True
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_binding_admission_report_blocks_invalid_evaluation():
    report = prepare_recovery_binding_admission_report({})
    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["status"] == "blocked"
    assert report["binding_admission_evaluation_reference"] == {}
    assert report["admission_granted"] is False


def test_binding_admission_report_denied_status_still_has_no_effects():
    report = prepare_recovery_binding_admission_report(_evaluation(), requested_status="denied")
    assert report["denied"] is True
    assert report["status"] == "denied"
    assert report["admission_granted"] is False
    assert report["runtime_binding_applied"] is False
    assert "runtime_binding_application" in report["denied_capabilities"]
