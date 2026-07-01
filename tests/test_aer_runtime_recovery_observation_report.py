import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_recovery_observation_report as observation_module
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
from core.runtime.aer_runtime_recovery_observation_report import (
    RECOVERY_OBSERVATION_ALLOWED_STATUSES,
    RECOVERY_OBSERVATION_DENIED_CAPABILITIES,
    RECOVERY_OBSERVATION_REPORT_CONTRACT,
    prepare_recovery_observation_report,
)
from core.runtime.aer_runtime_recovery_operator_adapter import prepare_recovery_operator_adapter_report
from core.runtime.aer_runtime_recovery_runtime_integration import coordinate_recovery_runtime_integration
from core.runtime.aer_runtime_recovery_scheduler_adapter import prepare_recovery_scheduler_adapter_report
from core.runtime.aer_runtime_recovery_supervisor_adapter import prepare_recovery_supervisor_adapter_report
from core.runtime.aer_runtime_recovery_surface_probe import prepare_recovery_surface_probe_report
from core.runtime.aer_runtime_recovery_wiring_gate import prepare_recovery_wiring_gate_report


MODULE = Path("core/runtime/aer_runtime_recovery_observation_report.py")
CONTRACT = Path("docs/contracts/runtime/recovery_observation_report_v1.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _observation_inputs():
    authority = {
        "contract": RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
        "authority_request_id": "authority-177",
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
        "intent_request_id": "intent-177",
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
    integration = coordinate_recovery_runtime_integration(authority, intent, integration_id="observe-177")
    activation = prepare_recovery_runtime_activation(integration, activation_id="observe-177")
    gate = prepare_recovery_wiring_gate_report(
        prepare_recovery_scheduler_adapter_report(activation),
        prepare_recovery_operator_adapter_report(activation),
        prepare_recovery_supervisor_adapter_report(activation),
        prepare_recovery_native_adapter_report(activation),
        gate_id="observe-177",
    )
    controlled = prepare_recovery_controlled_activation(gate, preparation_id="observe-177")
    kill_switch = prepare_recovery_kill_switch_report(controlled, kill_switch_id="observe-177")
    event_route = prepare_recovery_event_route_report(
        controlled,
        kill_switch,
        route_id="observe-177",
        source_surface="runtime_recovery_single_entry",
    )
    binding = prepare_recovery_dry_run_binding_report(event_route, kill_switch, binding_id="observe-177")
    dry_run_route = prepare_recovery_dry_run_route_report(binding, event_route, dry_run_route_id="observe-177")
    probe = prepare_recovery_surface_probe_report(dry_run_route, probe_id="observe-177")
    return probe, dry_run_route


def _package_entry() -> str:
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 177")
    end = text.find("## Package 178", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_observation_report_contract_and_module_exist():
    assert CONTRACT.exists()
    assert MODULE.exists()


def test_observation_report_public_api_is_fixed():
    assert observation_module.__all__ == [
        "RECOVERY_OBSERVATION_REPORT_CONTRACT",
        "RECOVERY_OBSERVATION_ALLOWED_STATUSES",
        "RECOVERY_OBSERVATION_DENIED_CAPABILITIES",
        "prepare_recovery_observation_report",
    ]
    public_functions = {
        name
        for name, value in inspect.getmembers(observation_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {"prepare_recovery_observation_report"}


def test_observation_report_preserves_probe_without_runtime_observation():
    probe, route = _observation_inputs()
    report = prepare_recovery_observation_report(probe, route, observation_id="observe-177")

    assert report["contract"] == RECOVERY_OBSERVATION_REPORT_CONTRACT
    assert report["prepared"] is True
    assert report["status"] == "prepared"
    assert report["observe_only"] is True
    assert report["dry_run"] is True
    assert report["observation_complete"] is True
    assert report["observation_entry"] == "runtime_recovery_single_entry"
    assert report["runtime_surface_touched"] is False
    assert report["surface_probe_executed"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["canonical_event"] == route["canonical_event"]
    assert report["surface_probe_reference"] == probe
    assert report["dry_run_route_reference"] == route
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False


def test_observation_report_blocks_mismatched_references_and_denied_status():
    probe, route = _observation_inputs()
    mismatched = copy.deepcopy(probe)
    mismatched["dry_run_route_reference"] = {}
    blocked = prepare_recovery_observation_report(mismatched, route)
    denied = prepare_recovery_observation_report(probe, route, requested_status="denied")

    assert blocked["status"] == "blocked"
    assert blocked["observation_entry"] is None
    assert blocked["reason"] == "missing or incompatible passive Recovery observation references"
    assert denied["status"] == "denied"
    assert denied["event_emitted"] is False
    assert denied["recovery_enabled"] is False


def test_observation_report_statuses_capabilities_and_determinism():
    assert RECOVERY_OBSERVATION_ALLOWED_STATUSES == ("prepared", "blocked", "denied")
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
        assert capability in RECOVERY_OBSERVATION_DENIED_CAPABILITIES

    probe, route = _observation_inputs()
    before = (copy.deepcopy(probe), copy.deepcopy(route))
    first = prepare_recovery_observation_report(probe, route, observation_id="observe-177")
    second = prepare_recovery_observation_report(
        copy.deepcopy(probe),
        copy.deepcopy(route),
        observation_id="observe-177",
    )
    assert first == second
    assert (probe, route) == before


def test_observation_report_module_has_no_forbidden_runtime_behavior_tokens():
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


def test_package_sequence_includes_package_177():
    entry = _package_entry()
    assert "## Package 177" in entry
    assert "Runtime Recovery Observation Report" in entry
    assert "docs/contracts/runtime/recovery_observation_report_v1.md" in entry
    assert "core/runtime/aer_runtime_recovery_observation_report.py" in entry
    assert "tests/test_aer_runtime_recovery_observation_report.py" in entry
    assert "python -m pytest tests/test_aer_runtime_recovery_observation_report.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 178" in entry
