from core.runtime.aer_runtime_recovery_disabled_binding import (
    RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY,
    prepare_recovery_disabled_runtime_binding_report,
)
from core.runtime.aer_runtime_recovery_runtime_binding_points import (
    RECOVERY_RUNTIME_BINDING_POINTS_REPORT_CONTRACT,
    prepare_recovery_runtime_binding_points_report,
)


def _approval():
    return {
        "contract": "aer.runtime.recovery.binding_approval_report.v1",
        "prepared": True,
        "blocked": False,
        "denied": False,
        "status": "prepared",
        "approval_granted": False,
        "binding_allowed": False,
        "binding_enabled": False,
        "runtime_binding_applied": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "canonical_event": {
            "contract": "aer.runtime.recovery.event.v1",
            "entry_id": RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY,
            "event_emitted": False,
        },
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def _disabled_binding():
    return prepare_recovery_disabled_runtime_binding_report(_approval())


def test_binding_points_are_declared_but_not_registered():
    report = prepare_recovery_runtime_binding_points_report(_disabled_binding())
    assert report["contract"] == RECOVERY_RUNTIME_BINDING_POINTS_REPORT_CONTRACT
    assert report["prepared"] is True
    assert report["binding_points_declared"] is True
    assert report["binding_points_registered"] is False
    assert report["runtime_hook_registered"] is False
    assert report["runtime_binding_applied"] is False
    assert report["runtime_surface_touched"] is False
    assert report["binding_enabled"] is False
    assert report["recovery_enabled"] is False
    assert report["event_emitted"] is False
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_binding_points_keep_single_entry_shape():
    report = prepare_recovery_runtime_binding_points_report(_disabled_binding())
    assert report["binding_entry"] == RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY
    assert report["binding_points"] == [
        {
            "point_id": RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY,
            "surface": "runtime",
            "mode": "disabled",
            "registered": False,
            "calls_runtime": False,
            "emits_event": False,
            "executes_recovery": False,
        }
    ]


def test_binding_points_block_invalid_disabled_binding():
    report = prepare_recovery_runtime_binding_points_report({"contract": "wrong"})
    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["binding_points"] == []
    assert report["disabled_binding_reference"] == {}
    assert "missing or incompatible" in report["reason"]


def test_binding_points_denied_status_still_does_not_register():
    report = prepare_recovery_runtime_binding_points_report(
        _disabled_binding(), requested_status="denied"
    )
    assert report["denied"] is True
    assert report["status"] == "denied"
    assert report["binding_points_registered"] is False
    assert report["runtime_hook_registered"] is False
    assert report["runtime_binding_applied"] is False
