import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_recovery_event_route as route_module
from core.runtime.aer_runtime_recovery_activation import prepare_recovery_runtime_activation
from core.runtime.aer_runtime_recovery_bridge import (
    RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
    RECOVERY_INTENT_RESPONSE_CONTRACT,
)
from core.runtime.aer_runtime_recovery_controlled_activation import prepare_recovery_controlled_activation
from core.runtime.aer_runtime_recovery_event_route import (
    RECOVERY_CANONICAL_EVENT_CONTRACT,
    RECOVERY_EVENT_ROUTE_ALLOWED_STATUSES,
    RECOVERY_EVENT_ROUTE_DENIED_CAPABILITIES,
    RECOVERY_EVENT_ROUTE_REPORT_CONTRACT,
    prepare_recovery_event_route_report,
)
from core.runtime.aer_runtime_recovery_kill_switch import prepare_recovery_kill_switch_report
from core.runtime.aer_runtime_recovery_native_adapter import prepare_recovery_native_adapter_report
from core.runtime.aer_runtime_recovery_operator_adapter import prepare_recovery_operator_adapter_report
from core.runtime.aer_runtime_recovery_runtime_integration import coordinate_recovery_runtime_integration
from core.runtime.aer_runtime_recovery_scheduler_adapter import prepare_recovery_scheduler_adapter_report
from core.runtime.aer_runtime_recovery_supervisor_adapter import prepare_recovery_supervisor_adapter_report
from core.runtime.aer_runtime_recovery_wiring_gate import prepare_recovery_wiring_gate_report


MODULE = Path("core/runtime/aer_runtime_recovery_event_route.py")
CONTRACT = Path("docs/contracts/runtime/recovery_event_route_v1.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _controlled_report():
    authority = {
        "contract": RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
        "authority_request_id": "authority-169",
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
        "intent_request_id": "intent-169",
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
    integration = coordinate_recovery_runtime_integration(authority, intent, integration_id="route-169")
    activation = prepare_recovery_runtime_activation(integration, activation_id="route-169")
    gate = prepare_recovery_wiring_gate_report(
        prepare_recovery_scheduler_adapter_report(activation),
        prepare_recovery_operator_adapter_report(activation),
        prepare_recovery_supervisor_adapter_report(activation),
        prepare_recovery_native_adapter_report(activation),
        gate_id="route-169",
    )
    return prepare_recovery_controlled_activation(gate, preparation_id="route-169")


def _route_inputs():
    controlled = _controlled_report()
    return controlled, prepare_recovery_kill_switch_report(controlled, kill_switch_id="route-169")


def _package_entry() -> str:
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 169")
    end = text.find("## Package 170", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_event_route_contract_and_module_exist():
    assert CONTRACT.exists()
    assert MODULE.exists()


def test_event_route_public_api_is_fixed():
    assert route_module.__all__ == [
        "RECOVERY_EVENT_ROUTE_REPORT_CONTRACT",
        "RECOVERY_CANONICAL_EVENT_CONTRACT",
        "RECOVERY_EVENT_ROUTE_ALLOWED_STATUSES",
        "RECOVERY_EVENT_ROUTE_DENIED_CAPABILITIES",
        "prepare_recovery_event_route_report",
    ]
    public_functions = {
        name
        for name, value in inspect.getmembers(route_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {"prepare_recovery_event_route_report"}


def test_event_route_prepares_single_entry_report_without_emitting_event():
    controlled, kill_switch = _route_inputs()
    report = prepare_recovery_event_route_report(
        controlled,
        kill_switch,
        route_id="route-169",
        source_surface="scheduler",
    )

    assert report["contract"] == RECOVERY_EVENT_ROUTE_REPORT_CONTRACT
    assert report["prepared"] is True
    assert report["status"] == "prepared"
    assert report["route_entry"] == "runtime_recovery_single_entry"
    assert report["single_entry_only"] is True
    assert report["route_count"] == 1
    assert report["route_enabled"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["route_only"] is True
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False


def test_event_route_preserves_canonical_event_source_information():
    controlled, kill_switch = _route_inputs()
    report = prepare_recovery_event_route_report(
        controlled,
        kill_switch,
        route_id="route-169",
        source_surface="operator",
    )
    event = report["canonical_event"]

    assert event == {
        "contract": RECOVERY_CANONICAL_EVENT_CONTRACT,
        "source_surface": "operator",
        "entry_id": "runtime_recovery_single_entry",
        "route_id": "route-169",
        "gate_state": "prepared",
        "event_emitted": False,
    }


def test_event_route_blocks_multi_entry_and_invalid_kill_switch():
    controlled, kill_switch = _route_inputs()
    multi = prepare_recovery_event_route_report(controlled, kill_switch, requested_entry="native_runtime")
    kill_switch["prepared"] = False
    blocked = prepare_recovery_event_route_report(controlled, kill_switch)

    assert multi["status"] == "blocked"
    assert multi["route_count"] == 0
    assert multi["reason"] == "event route preparation allows only runtime_recovery_single_entry"
    assert blocked["status"] == "blocked"
    assert blocked["kill_switch_reference"] == {}


def test_event_route_statuses_capabilities_and_determinism():
    assert RECOVERY_EVENT_ROUTE_ALLOWED_STATUSES == ("prepared", "blocked", "denied")
    for capability in (
        "event_emission",
        "recovery_execution",
        "recovery_enablement",
        "runtime_mainline_wiring",
        "multi_entry_wiring",
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
        assert capability in RECOVERY_EVENT_ROUTE_DENIED_CAPABILITIES

    controlled, kill_switch = _route_inputs()
    before = (copy.deepcopy(controlled), copy.deepcopy(kill_switch))
    first = prepare_recovery_event_route_report(controlled, kill_switch, route_id="route-169")
    second = prepare_recovery_event_route_report(copy.deepcopy(controlled), copy.deepcopy(kill_switch), route_id="route-169")
    assert first == second
    assert (controlled, kill_switch) == before


def test_event_route_module_has_no_forbidden_runtime_behavior_tokens():
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


def test_package_sequence_includes_package_169():
    entry = _package_entry()
    assert "## Package 169" in entry
    assert "Runtime Recovery Event Route Preparation" in entry
    assert "docs/contracts/runtime/recovery_event_route_v1.md" in entry
    assert "core/runtime/aer_runtime_recovery_event_route.py" in entry
    assert "tests/test_aer_runtime_recovery_event_route.py" in entry
    assert "python -m pytest tests/test_aer_runtime_recovery_event_route.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 170" in entry
