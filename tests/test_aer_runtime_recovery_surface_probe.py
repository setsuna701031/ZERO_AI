import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_recovery_surface_probe as probe_module
from core.runtime.aer_runtime_recovery_activation import prepare_recovery_runtime_activation
from core.runtime.aer_runtime_recovery_bridge import (
    RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
    RECOVERY_INTENT_RESPONSE_CONTRACT,
)
from core.runtime.aer_runtime_recovery_controlled_activation import prepare_recovery_controlled_activation
from core.runtime.aer_runtime_recovery_dry_run_binding import prepare_recovery_dry_run_binding_report
from core.runtime.aer_runtime_recovery_dry_run_route import prepare_recovery_dry_run_route_report
from core.runtime.aer_runtime_recovery_event_route import prepare_recovery_event_route_report
from core.runtime.aer_runtime_recovery_kill_switch import prepare_recovery_kill_switch_report
from core.runtime.aer_runtime_recovery_native_adapter import prepare_recovery_native_adapter_report
from core.runtime.aer_runtime_recovery_operator_adapter import prepare_recovery_operator_adapter_report
from core.runtime.aer_runtime_recovery_runtime_integration import coordinate_recovery_runtime_integration
from core.runtime.aer_runtime_recovery_scheduler_adapter import prepare_recovery_scheduler_adapter_report
from core.runtime.aer_runtime_recovery_supervisor_adapter import prepare_recovery_supervisor_adapter_report
from core.runtime.aer_runtime_recovery_surface_probe import (
    RECOVERY_SURFACE_PROBE_ALLOWED_STATUSES,
    RECOVERY_SURFACE_PROBE_DENIED_CAPABILITIES,
    RECOVERY_SURFACE_PROBE_REPORT_CONTRACT,
    prepare_recovery_surface_probe_report,
)
from core.runtime.aer_runtime_recovery_wiring_gate import prepare_recovery_wiring_gate_report


MODULE = Path("core/runtime/aer_runtime_recovery_surface_probe.py")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _dry_run_route_report():
    authority = {
        "contract": RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
        "authority_request_id": "authority-176",
        "authority_owner": "runtime_recovery_execution_authority",
        "authorized": True,
        "decision": "authorized_for_future_handoff",
        "state": "authorized",
        "reason": None,
        "authorized_scope": "future_handoff",
        "downstream_requirements": ["runtime_recovery_execution_intent"],
        "denied_capabilities": ["recovery_execution"],
        "executes_recovery": False,
        "authority_only": True,
    }
    intent = {
        "contract": RECOVERY_INTENT_RESPONSE_CONTRACT,
        "intent_request_id": "intent-176",
        "intent_owner": "runtime_recovery_execution_intent",
        "authority_reference": authority,
        "accepted": True,
        "status": "accepted_intent_only",
        "state": "described",
        "intended_actions": ["describe_recovery_execution_intent"],
        "denied_actions": [],
        "denied_capabilities": ["recovery_execution"],
        "reason": None,
        "executes_recovery": False,
        "intent_only": True,
    }
    integration = coordinate_recovery_runtime_integration(authority, intent, integration_id="probe-176")
    activation = prepare_recovery_runtime_activation(integration, activation_id="probe-176")
    gate = prepare_recovery_wiring_gate_report(
        prepare_recovery_scheduler_adapter_report(activation),
        prepare_recovery_operator_adapter_report(activation),
        prepare_recovery_supervisor_adapter_report(activation),
        prepare_recovery_native_adapter_report(activation),
        gate_id="probe-176",
    )
    controlled = prepare_recovery_controlled_activation(gate, preparation_id="probe-176")
    kill_switch = prepare_recovery_kill_switch_report(controlled, kill_switch_id="probe-176")
    route = prepare_recovery_event_route_report(
        controlled,
        kill_switch,
        route_id="probe-176",
        source_surface="runtime_recovery_single_entry",
    )
    binding = prepare_recovery_dry_run_binding_report(route, kill_switch, binding_id="probe-176")
    return prepare_recovery_dry_run_route_report(binding, route, dry_run_route_id="probe-176")


def _package_entry() -> str:
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 176")
    end = text.find("## Package 177", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_surface_probe_module_exists_and_public_api_is_fixed():
    assert MODULE.exists()
    assert probe_module.__all__ == [
        "RECOVERY_SURFACE_PROBE_REPORT_CONTRACT",
        "RECOVERY_SURFACE_PROBE_ALLOWED_STATUSES",
        "RECOVERY_SURFACE_PROBE_DENIED_CAPABILITIES",
        "prepare_recovery_surface_probe_report",
    ]
    public_functions = {
        name
        for name, value in inspect.getmembers(probe_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {"prepare_recovery_surface_probe_report"}


def test_surface_probe_observes_without_touching_runtime_surface():
    route = _dry_run_route_report()
    report = prepare_recovery_surface_probe_report(route, probe_id="probe-176")

    assert report["contract"] == RECOVERY_SURFACE_PROBE_REPORT_CONTRACT
    assert report["prepared"] is True
    assert report["status"] == "prepared"
    assert report["observe_only"] is True
    assert report["dry_run"] is True
    assert report["observation_entry"] == "runtime_recovery_single_entry"
    assert report["surface_probe_allowed"] is True
    assert report["surface_probe_executed"] is False
    assert report["runtime_surface_touched"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["canonical_event"] == route["canonical_event"]
    assert report["dry_run_route_reference"] == route
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False


def test_surface_probe_blocks_multi_entry_and_invalid_route():
    route = _dry_run_route_report()
    multi = prepare_recovery_surface_probe_report(route, requested_entry="scheduler")
    invalid = copy.deepcopy(route)
    invalid["prepared"] = False
    blocked = prepare_recovery_surface_probe_report(invalid)

    assert multi["status"] == "blocked"
    assert multi["observation_entry"] is None
    assert multi["reason"] == "surface probe allows only runtime_recovery_single_entry"
    assert blocked["status"] == "blocked"
    assert blocked["dry_run_route_reference"] == {}


def test_surface_probe_statuses_capabilities_and_determinism():
    assert RECOVERY_SURFACE_PROBE_ALLOWED_STATUSES == ("prepared", "blocked", "denied")
    for capability in (
        "recovery_execution",
        "recovery_enablement",
        "runtime_mainline_wiring",
        "route_activation",
        "event_emission",
        "scheduler_call",
        "operator_call",
        "dispatcher_call",
        "supervisor_call",
        "native_runtime_call",
        "runtime_mutation",
        "persistence_write",
        "replay_action",
        "audit_emission",
        "journal_event",
        "subprocess_call",
        "file_io",
    ):
        assert capability in RECOVERY_SURFACE_PROBE_DENIED_CAPABILITIES

    route = _dry_run_route_report()
    before = copy.deepcopy(route)
    first = prepare_recovery_surface_probe_report(route, probe_id="probe-176")
    second = prepare_recovery_surface_probe_report(copy.deepcopy(route), probe_id="probe-176")
    assert first == second
    assert route == before


def test_surface_probe_module_has_no_forbidden_runtime_behavior_tokens():
    text = MODULE.read_text(encoding="utf-8")
    for token in (
        "import os",
        "import subprocess",
        "import pathlib",
        "from pathlib",
        "scheduler.",
        "dispatcher.",
        "operator.",
        "supervisor.",
        "native_runtime.",
        "Popen",
        "run(",
        "open(",
        "write(",
        "Path(",
    ):
        assert token not in text


def test_package_sequence_includes_package_176():
    entry = _package_entry()
    assert "## Package 176" in entry
    assert "Runtime Recovery Surface Probe Helper" in entry
    assert "core/runtime/aer_runtime_recovery_surface_probe.py" in entry
    assert "tests/test_aer_runtime_recovery_surface_probe.py" in entry
    assert "python -m pytest tests/test_aer_runtime_recovery_surface_probe.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 177" in entry
