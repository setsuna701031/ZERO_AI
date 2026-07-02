from core.runtime.aer_runtime_recovery_binding_admission_report import (
    RECOVERY_BINDING_ADMISSION_REPORT_CONTRACT,
)
from core.runtime.aer_runtime_recovery_binding_endpoint import (
    RECOVERY_BINDING_ENDPOINT_NAME,
    RECOVERY_BINDING_ENDPOINT_REPORT_CONTRACT,
    prepare_recovery_binding_endpoint_report,
)


def _admission_report() -> dict[str, object]:
    return {
        "contract": RECOVERY_BINDING_ADMISSION_REPORT_CONTRACT,
        "prepared": True,
        "blocked": False,
        "denied": False,
        "status": "prepared",
        "admission_granted": False,
        "runtime_binding_accepted": False,
        "binding_applied": False,
        "runtime_hook_registered": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def test_endpoint_report_is_prepared_but_disabled() -> None:
    report = prepare_recovery_binding_endpoint_report(_admission_report(), endpoint_id="endpoint-1")

    assert report["contract"] == RECOVERY_BINDING_ENDPOINT_REPORT_CONTRACT
    assert report["endpoint_id"] == "endpoint-1"
    assert report["endpoint_name"] == RECOVERY_BINDING_ENDPOINT_NAME
    assert report["prepared"] is True
    assert report["blocked"] is False
    assert report["denied"] is False
    assert report["status"] == "prepared"
    assert report["endpoint_declared"] is True
    assert report["endpoint_enabled"] is False
    assert report["endpoint_invokable"] is False
    assert report["binding_disabled"] is True
    assert report["binding_applied"] is False
    assert report["runtime_hook_registered"] is False
    assert report["runtime_mainline_wiring_enabled"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["admission_granted"] is False
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_endpoint_report_blocks_invalid_admission() -> None:
    report = prepare_recovery_binding_endpoint_report({"contract": "wrong"})
    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["denied"] is False
    assert report["binding_admission_reference"] == {}


def test_endpoint_report_denies_activation_request() -> None:
    report = prepare_recovery_binding_endpoint_report(_admission_report(), request_activation=True)
    assert report["prepared"] is False
    assert report["blocked"] is False
    assert report["denied"] is True
    assert report["endpoint_enabled"] is False
    assert "prohibited" in str(report["reason"])


def test_endpoint_report_rejects_non_single_endpoint() -> None:
    report = prepare_recovery_binding_endpoint_report(_admission_report(), requested_endpoint="other")
    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["endpoint_name"] is None
    assert "allows only" in str(report["reason"])
