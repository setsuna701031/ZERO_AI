from __future__ import annotations

import copy
import inspect

from core.runtime.aer_runtime_recovery_dry_run_binding import RECOVERY_DRY_RUN_BINDING_ENTRY
from core.runtime.aer_runtime_recovery_event_route import RECOVERY_CANONICAL_EVENT_CONTRACT
from core.runtime.aer_runtime_recovery_observation_report import RECOVERY_OBSERVATION_REPORT_CONTRACT
from core.runtime.aer_runtime_recovery_preflight_eligibility import (
    RECOVERY_PREFLIGHT_ELIGIBILITY_DENIED_CAPABILITIES,
    RECOVERY_PREFLIGHT_ELIGIBILITY_REPORT_CONTRACT,
    prepare_recovery_preflight_eligibility_report,
)


def _observation_report() -> dict[str, object]:
    event = {
        "contract": RECOVERY_CANONICAL_EVENT_CONTRACT,
        "source_surface": "runtime_recovery_single_entry",
        "entry_id": RECOVERY_DRY_RUN_BINDING_ENTRY,
        "route_id": "route-1",
        "gate_state": "off",
        "event_emitted": False,
    }
    return {
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


def test_prepare_preflight_eligibility_report_preserves_non_executing_boundary() -> None:
    report = prepare_recovery_preflight_eligibility_report(
        _observation_report(),
        preflight_id="preflight-1",
        metadata={"owner": "test"},
    )

    assert report["contract"] == RECOVERY_PREFLIGHT_ELIGIBILITY_REPORT_CONTRACT
    assert report["preflight_id"] == "preflight-1"
    assert report["prepared"] is True
    assert report["blocked"] is False
    assert report["denied"] is False
    assert report["status"] == "prepared"
    assert report["preflight_only"] is True
    assert report["eligibility_checked"] is True
    assert report["eligibility_level"] == "non_executing_preflight"
    assert report["single_entry_only"] is True
    assert report["preflight_entry"] == RECOVERY_DRY_RUN_BINDING_ENTRY
    assert report["eligible_for_next_non_executing_phase"] is True
    assert report["eligible_for_runtime_binding"] is False
    assert report["eligible_for_recovery_execution"] is False
    assert report["runtime_binding_allowed"] is False
    assert report["recovery_execution_allowed"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["runtime_surface_touched"] is False
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_preflight_eligibility_preserves_canonical_event_and_reference_by_value() -> None:
    observation = _observation_report()
    report = prepare_recovery_preflight_eligibility_report(observation)

    assert report["canonical_event"] == observation["canonical_event"]
    assert report["canonical_event"] is not observation["canonical_event"]
    assert report["observation_reference"] == observation
    assert report["observation_reference"] is not observation


def test_preflight_eligibility_requirements_are_explicit() -> None:
    report = prepare_recovery_preflight_eligibility_report(_observation_report())
    requirements = report["preflight_requirements"]

    assert requirements == {
        "observation_report_valid": True,
        "single_entry_preserved": True,
        "canonical_event_preserved": True,
        "event_not_emitted": True,
        "runtime_surface_not_touched": True,
        "recovery_disabled": True,
        "execution_denied": True,
        "plain_dict_preserved": True,
    }


def test_preflight_eligibility_blocks_invalid_observation() -> None:
    observation = _observation_report()
    observation["event_emitted"] = True

    report = prepare_recovery_preflight_eligibility_report(observation)

    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["status"] == "blocked"
    assert report["canonical_event"] == {}
    assert report["observation_reference"] == {}
    assert report["reason"] == "missing or incompatible passive Recovery observation report"


def test_preflight_eligibility_denied_status_never_allows_runtime_binding() -> None:
    report = prepare_recovery_preflight_eligibility_report(
        _observation_report(),
        requested_status="denied",
    )

    assert report["prepared"] is False
    assert report["denied"] is True
    assert report["status"] == "denied"
    assert report["runtime_binding_allowed"] is False
    assert report["recovery_execution_allowed"] is False
    assert report["reason"] == "caller requested passive denied preflight eligibility status"


def test_preflight_eligibility_metadata_is_plain_and_mutation_independent() -> None:
    metadata = {"nested": {"items": ("a", "b")}}
    report = prepare_recovery_preflight_eligibility_report(_observation_report(), metadata=metadata)

    metadata["nested"]["items"] = ("changed",)

    assert report["metadata"] == {"nested": {"items": ["a", "b"]}}


def test_preflight_eligibility_source_avoids_runtime_effect_surfaces() -> None:
    source = inspect.getsource(prepare_recovery_preflight_eligibility_report)
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
    assert "runtime_binding" in RECOVERY_PREFLIGHT_ELIGIBILITY_DENIED_CAPABILITIES
