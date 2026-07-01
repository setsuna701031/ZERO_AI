from core.runtime.aer_runtime_recovery_binding_planner import (
    RECOVERY_BINDING_PLAN_REPORT_CONTRACT,
    prepare_recovery_binding_plan_report,
)
from core.runtime.aer_runtime_recovery_binding_registry import (
    RECOVERY_BINDING_REGISTRY_ENTRY,
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


def _registry(preflight: dict) -> dict:
    return prepare_recovery_binding_registry_report(preflight)


def test_binding_plan_prepared_report_is_passive() -> None:
    preflight = _preflight()
    registry = _registry(preflight)

    report = prepare_recovery_binding_plan_report(registry, preflight, plan_id="plan-1")

    assert report["contract"] == RECOVERY_BINDING_PLAN_REPORT_CONTRACT
    assert report["plan_id"] == "plan-1"
    assert report["prepared"] is True
    assert report["blocked"] is False
    assert report["denied"] is False
    assert report["status"] == "prepared"
    assert report["binding_entry"] == RECOVERY_BINDING_REGISTRY_ENTRY
    assert report["binding_plan_only"] is True
    assert report["binding_planned"] is True
    assert report["binding_applied"] is False
    assert report["runtime_binding_registered"] is False
    assert report["runtime_binding_active"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_binding_plan_blocks_mismatched_preflight_reference() -> None:
    preflight = _preflight()
    registry = _registry(preflight)
    changed = dict(preflight)
    changed["preflight_only"] = False

    report = prepare_recovery_binding_plan_report(registry, changed)

    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["binding_planned"] is False
    assert report["binding_applied"] is False


def test_binding_plan_denies_activation_request() -> None:
    preflight = _preflight()
    registry = _registry(preflight)

    report = prepare_recovery_binding_plan_report(registry, preflight, request_binding_activation=True)

    assert report["prepared"] is False
    assert report["denied"] is True
    assert report["status"] == "denied"
    assert report["binding_applied"] is False
    assert "runtime binding activation is prohibited" in report["reason"]


def test_binding_plan_public_surface_is_sealed() -> None:
    import core.runtime.aer_runtime_recovery_binding_planner as module

    assert module.__all__ == [
        "RECOVERY_BINDING_PLAN_REPORT_CONTRACT",
        "RECOVERY_BINDING_PLAN_ALLOWED_STATUSES",
        "RECOVERY_BINDING_PLAN_DENIED_CAPABILITIES",
        "prepare_recovery_binding_plan_report",
    ]
