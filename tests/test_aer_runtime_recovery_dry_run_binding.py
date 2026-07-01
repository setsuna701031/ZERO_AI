import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_recovery_dry_run_binding as binding_module
from core.runtime.aer_runtime_recovery_activation import prepare_recovery_runtime_activation
from core.runtime.aer_runtime_recovery_bridge import (
    RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
    RECOVERY_INTENT_RESPONSE_CONTRACT,
)
from core.runtime.aer_runtime_recovery_controlled_activation import prepare_recovery_controlled_activation
from core.runtime.aer_runtime_recovery_dry_run_binding import (
    RECOVERY_DRY_RUN_BINDING_ALLOWED_STATUSES,
    RECOVERY_DRY_RUN_BINDING_DENIED_CAPABILITIES,
    RECOVERY_DRY_RUN_BINDING_ENTRY,
    RECOVERY_DRY_RUN_BINDING_REPORT_CONTRACT,
    prepare_recovery_dry_run_binding_report,
)
from core.runtime.aer_runtime_recovery_event_route import prepare_recovery_event_route_report
from core.runtime.aer_runtime_recovery_kill_switch import prepare_recovery_kill_switch_report
from core.runtime.aer_runtime_recovery_native_adapter import prepare_recovery_native_adapter_report
from core.runtime.aer_runtime_recovery_operator_adapter import prepare_recovery_operator_adapter_report
from core.runtime.aer_runtime_recovery_runtime_integration import coordinate_recovery_runtime_integration
from core.runtime.aer_runtime_recovery_scheduler_adapter import prepare_recovery_scheduler_adapter_report
from core.runtime.aer_runtime_recovery_supervisor_adapter import prepare_recovery_supervisor_adapter_report
from core.runtime.aer_runtime_recovery_wiring_gate import prepare_recovery_wiring_gate_report


MODULE = Path("core/runtime/aer_runtime_recovery_dry_run_binding.py")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _controlled_report():
    authority = {
        "contract": RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
        "authority_request_id": "authority-172",
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
        "intent_request_id": "intent-172",
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
    integration = coordinate_recovery_runtime_integration(authority, intent, integration_id="binding-172")
    activation = prepare_recovery_runtime_activation(integration, activation_id="binding-172")
    gate = prepare_recovery_wiring_gate_report(
        prepare_recovery_scheduler_adapter_report(activation),
        prepare_recovery_operator_adapter_report(activation),
        prepare_recovery_supervisor_adapter_report(activation),
        prepare_recovery_native_adapter_report(activation),
        gate_id="binding-172",
    )
    return prepare_recovery_controlled_activation(gate, preparation_id="binding-172")


def _binding_inputs():
    controlled = _controlled_report()
    kill_switch = prepare_recovery_kill_switch_report(controlled, kill_switch_id="binding-172")
    route = prepare_recovery_event_route_report(
        controlled,
        kill_switch,
        route_id="binding-172",
        source_surface="runtime_recovery_single_entry",
    )
    return route, kill_switch


def _package_entry() -> str:
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 172")
    end = text.find("## Package 173", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_dry_run_binding_module_exists_and_public_api_is_fixed():
    assert MODULE.exists()
    assert binding_module.__all__ == [
        "RECOVERY_DRY_RUN_BINDING_REPORT_CONTRACT",
        "RECOVERY_DRY_RUN_BINDING_ALLOWED_STATUSES",
        "RECOVERY_DRY_RUN_BINDING_ENTRY",
        "RECOVERY_DRY_RUN_BINDING_DENIED_CAPABILITIES",
        "prepare_recovery_dry_run_binding_report",
    ]
    public_functions = {
        name
        for name, value in inspect.getmembers(binding_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {"prepare_recovery_dry_run_binding_report"}


def test_dry_run_binding_prepares_single_entry_without_runtime_binding():
    route, kill_switch = _binding_inputs()
    report = prepare_recovery_dry_run_binding_report(route, kill_switch, binding_id="binding-172")

    assert report["contract"] == RECOVERY_DRY_RUN_BINDING_REPORT_CONTRACT
    assert report["prepared"] is True
    assert report["status"] == "prepared"
    assert report["dry_run"] is True
    assert report["binding_entry"] == RECOVERY_DRY_RUN_BINDING_ENTRY
    assert report["bound_to_runtime"] is False
    assert report["binding_enabled"] is False
    assert report["route_enabled"] is False
    assert report["event_emitted"] is False
    assert report["recovery_enabled"] is False
    assert report["event_route_reference"] == route
    assert report["kill_switch_reference"] == kill_switch
    assert report["canonical_event"] == route["canonical_event"]
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False


def test_dry_run_binding_blocks_multi_entry_and_denies_enablement():
    route, kill_switch = _binding_inputs()
    multi = prepare_recovery_dry_run_binding_report(route, kill_switch, requested_entry="scheduler")
    denied = prepare_recovery_dry_run_binding_report(route, kill_switch, request_enablement=True)

    assert multi["status"] == "blocked"
    assert multi["binding_entry"] is None
    assert multi["reason"] == "dry-run binding allows only runtime_recovery_single_entry"
    assert denied["status"] == "denied"
    assert denied["recovery_enabled"] is False
    assert denied["reason"] == "Recovery enablement is prohibited during dry-run binding"


def test_dry_run_binding_statuses_capabilities_and_determinism():
    assert RECOVERY_DRY_RUN_BINDING_ALLOWED_STATUSES == ("prepared", "blocked", "denied")
    for capability in (
        "recovery_execution",
        "recovery_enablement",
        "runtime_mainline_wiring",
        "multi_entry_binding",
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
        "real_runtime_event_emission",
        "subprocess_call",
        "file_io",
    ):
        assert capability in RECOVERY_DRY_RUN_BINDING_DENIED_CAPABILITIES

    route, kill_switch = _binding_inputs()
    before = (copy.deepcopy(route), copy.deepcopy(kill_switch))
    first = prepare_recovery_dry_run_binding_report(route, kill_switch, binding_id="binding-172")
    second = prepare_recovery_dry_run_binding_report(
        copy.deepcopy(route),
        copy.deepcopy(kill_switch),
        binding_id="binding-172",
    )
    assert first == second
    assert (route, kill_switch) == before


def test_dry_run_binding_module_has_no_forbidden_runtime_behavior_tokens():
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


def test_package_sequence_includes_package_172():
    entry = _package_entry()
    assert "## Package 172" in entry
    assert "Runtime Recovery Dry-Run Binding Helper" in entry
    assert "core/runtime/aer_runtime_recovery_dry_run_binding.py" in entry
    assert "tests/test_aer_runtime_recovery_dry_run_binding.py" in entry
    assert "python -m pytest tests/test_aer_runtime_recovery_dry_run_binding.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 173" in entry
