from __future__ import annotations

import inspect

from core.runtime.aer_runtime_recovery_dry_run_binding import RECOVERY_DRY_RUN_BINDING_ENTRY
from core.runtime.aer_runtime_recovery_event_route import RECOVERY_CANONICAL_EVENT_CONTRACT
from core.runtime.aer_runtime_recovery_observation_report import RECOVERY_OBSERVATION_REPORT_CONTRACT
from core.runtime.aer_runtime_recovery_preflight_eligibility import (
    RECOVERY_PREFLIGHT_ELIGIBILITY_REPORT_CONTRACT,
    prepare_recovery_preflight_eligibility_report,
)
from core.runtime.aer_runtime_recovery_preflight_report import (
    RECOVERY_PREFLIGHT_DENIED_CAPABILITIES,
    RECOVERY_PREFLIGHT_REPORT_CONTRACT,
    prepare_recovery_preflight_report,
)


def _eligibility_report() -> dict[str, object]:
    event = {
        "contract": RECOVERY_CANONICAL_EVENT_CONTRACT,
        "source_surface": "runtime_recovery_single_entry",
        "entry_id": RECOVERY_DRY_RUN_BINDING_ENTRY,
        "route_id": "route-1",
        "gate_state": "off",
        "event_emitted": False,
    }
    observation = {
        "contract": RECOVERY_OBSERVATION_REPORT_CONTRACT,
        "prepared": True,
        "blocked": False,
        "denied": False,
        "status": "prepared",
        "observe_only": True,
        "dry_run": True,
        "observation_complete": True,
        "single_entry_only": True,
        "observation_entry": RECOVERY_DRY_RUN_BINDING_ENTRY,
        "runtime_surface_touched": False,
        "surface_probe_executed": False,
        "event_emitted": False,
        "recovery_enabled": False,
        "canonical_event": event,
        "observation_report_only": True,
        "executes_recovery": False,
        "side_effects_performed": False,
        "plain_dict_only": True,
    }
    return prepare_recovery_preflight_eligibility_report(observation)


def test_prepare_preflight_report_preserves_denied_runtime_boundary() -> None:
    report = prepare_recovery_preflight_report(_eligibility_report(), report_id="report-1")

    assert report["contract"] == RECOVERY_PREFLIGHT_REPORT_CONTRACT
    assert report["report_id"] == "report-1"
    assert report["prepared"] is True
    assert report["status"] == "prepared"
    assert report["preflight_only"] is True
    assert report["preflight_complete"] is True
    assert report["preflight_result"] == "eligible_for_next_non_executing_phase"
    assert report["single_entry_only"] is True
    assert report["preflight_entry"] == RECOVERY_DRY_RUN_BINDING_ENTRY
    assert report["runtime_binding_allowed"] is False
    assert report["runtime_mainline_wiring_allowed"] is False
    assert report["recovery_execution_allowed"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["runtime_surface_touched"] is False
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_preflight_report_preserves_eligibility_and_canonical_event_by_value() -> None:
    eligibility = _eligibility_report()
    report = prepare_recovery_preflight_report(eligibility)

    assert report["preflight_eligibility_reference"] == eligibility
    assert report["preflight_eligibility_reference"] is not eligibility
    assert report["canonical_event"] == eligibility["canonical_event"]
    assert report["canonical_event"] is not eligibility["canonical_event"]


def test_preflight_report_summary_points_only_to_non_executing_next_phase() -> None:
    report = prepare_recovery_preflight_report(_eligibility_report())

    assert report["preflight_summary"] == {
        "preflight_valid": True,
        "preflight_complete": True,
        "single_entry_only": True,
        "canonical_event_contract": RECOVERY_CANONICAL_EVENT_CONTRACT,
        "event_emitted": False,
        "runtime_binding_allowed": False,
        "recovery_execution_allowed": False,
        "next_phase": "controlled_non_executing_binding",
    }


def test_preflight_report_blocks_invalid_eligibility() -> None:
    eligibility = _eligibility_report()
    eligibility["contract"] = RECOVERY_PREFLIGHT_ELIGIBILITY_REPORT_CONTRACT + ".broken"

    report = prepare_recovery_preflight_report(eligibility)

    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["status"] == "blocked"
    assert report["preflight_eligibility_reference"] == {}
    assert report["canonical_event"] == {}
    assert report["reason"] == "missing or incompatible passive Recovery preflight eligibility report"


def test_preflight_report_denied_status_is_passive() -> None:
    report = prepare_recovery_preflight_report(_eligibility_report(), requested_status="denied")

    assert report["prepared"] is False
    assert report["denied"] is True
    assert report["status"] == "denied"
    assert report["runtime_binding_allowed"] is False
    assert report["recovery_execution_allowed"] is False
    assert report["reason"] == "caller requested passive denied preflight report status"


def test_preflight_report_source_avoids_runtime_effect_surfaces() -> None:
    source = inspect.getsource(prepare_recovery_preflight_report)
    forbidden_tokens = (
        "subprocess",
        "Path(",
        "open(",
        "write(",
        "emit(",
        "dispatch(",
        "execute(",
        "scheduler.",
        "operator.",
        "supervisor.",
        "native.",
    )

    assert all(token not in source for token in forbidden_tokens)
    assert "runtime_binding" in RECOVERY_PREFLIGHT_DENIED_CAPABILITIES
