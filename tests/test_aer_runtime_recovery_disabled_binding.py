from core.runtime.aer_runtime_recovery_disabled_binding import (
    RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY,
    RECOVERY_DISABLED_RUNTIME_BINDING_REPORT_CONTRACT,
    prepare_recovery_disabled_runtime_binding_report,
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


def test_disabled_binding_report_prepared_but_not_bound():
    report = prepare_recovery_disabled_runtime_binding_report(_approval(), binding_id="bind-1")
    assert report["contract"] == RECOVERY_DISABLED_RUNTIME_BINDING_REPORT_CONTRACT
    assert report["prepared"] is True
    assert report["status"] == "prepared"
    assert report["binding_entry"] == RECOVERY_DISABLED_RUNTIME_BINDING_ENTRY
    assert report["binding_skeleton"] is True
    assert report["binding_enabled"] is False
    assert report["bound_to_runtime"] is False
    assert report["runtime_hook_registered"] is False
    assert report["runtime_binding_applied"] is False
    assert report["runtime_mainline_wiring_enabled"] is False
    assert report["recovery_enabled"] is False
    assert report["event_emitted"] is False
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_disabled_binding_blocks_invalid_approval():
    report = prepare_recovery_disabled_runtime_binding_report({"contract": "wrong"})
    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["status"] == "blocked"
    assert report["binding_approval_reference"] == {}
    assert "missing or incompatible" in report["reason"]


def test_disabled_binding_rejects_non_single_entry():
    report = prepare_recovery_disabled_runtime_binding_report(
        _approval(), requested_entry="scheduler"
    )
    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["binding_entry"] is None
    assert "runtime_recovery_single_entry" in report["reason"]


def test_disabled_binding_denied_status_remains_side_effect_free():
    report = prepare_recovery_disabled_runtime_binding_report(_approval(), requested_status="denied")
    assert report["denied"] is True
    assert report["status"] == "denied"
    assert report["binding_enabled"] is False
    assert report["runtime_binding_applied"] is False
    assert report["side_effects_performed"] is False
