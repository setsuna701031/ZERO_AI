from core.runtime.aer_runtime_recovery_binding_registry import (
    RECOVERY_BINDING_REGISTRY_ENTRY,
    RECOVERY_BINDING_REGISTRY_REPORT_CONTRACT,
    prepare_recovery_binding_registry_report,
)
from core.runtime.aer_runtime_recovery_preflight import RECOVERY_PREFLIGHT_ELIGIBILITY_CONTRACT


def _preflight() -> dict:
    return {
        "contract": RECOVERY_PREFLIGHT_ELIGIBILITY_CONTRACT,
        "prepared": True,
        "blocked": False,
        "denied": False,
        "status": "prepared",
        "preflight_only": True,
        "eligible": True,
        "runtime_binding_allowed": False,
        "runtime_mainline_wiring_allowed": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "canonical_event": {"event_emitted": False, "entry_id": RECOVERY_BINDING_REGISTRY_ENTRY},
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }


def test_binding_registry_prepared_report_is_passive() -> None:
    report = prepare_recovery_binding_registry_report(_preflight(), registry_id="reg-1")

    assert report["contract"] == RECOVERY_BINDING_REGISTRY_REPORT_CONTRACT
    assert report["registry_id"] == "reg-1"
    assert report["prepared"] is True
    assert report["blocked"] is False
    assert report["denied"] is False
    assert report["status"] == "prepared"
    assert report["registry_entry"] == RECOVERY_BINDING_REGISTRY_ENTRY
    assert report["binding_registry_only"] is True
    assert report["runtime_binding_registered"] is False
    assert report["runtime_binding_active"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_binding_registry_blocks_invalid_preflight() -> None:
    report = prepare_recovery_binding_registry_report({"contract": "wrong"})

    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["status"] == "blocked"
    assert report["preflight_reference"] == {}


def test_binding_registry_denies_activation_request() -> None:
    report = prepare_recovery_binding_registry_report(_preflight(), request_activation=True)

    assert report["prepared"] is False
    assert report["denied"] is True
    assert report["status"] == "denied"
    assert report["runtime_binding_active"] is False
    assert "runtime binding activation is prohibited" in report["reason"]


def test_binding_registry_rejects_non_single_entry() -> None:
    report = prepare_recovery_binding_registry_report(_preflight(), requested_entry="scheduler")

    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["registry_entry"] is None
    assert "runtime_recovery_single_entry" in report["reason"]


def test_binding_registry_public_surface_is_sealed() -> None:
    import core.runtime.aer_runtime_recovery_binding_registry as module

    assert module.__all__ == [
        "RECOVERY_BINDING_REGISTRY_REPORT_CONTRACT",
        "RECOVERY_BINDING_REGISTRY_ENTRY",
        "RECOVERY_BINDING_REGISTRY_ALLOWED_STATUSES",
        "RECOVERY_BINDING_REGISTRY_DENIED_CAPABILITIES",
        "prepare_recovery_binding_registry_report",
    ]
