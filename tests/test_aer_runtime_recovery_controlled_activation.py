import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_recovery_controlled_activation as controlled_module
from core.runtime.aer_runtime_recovery_activation import prepare_recovery_runtime_activation
from core.runtime.aer_runtime_recovery_bridge import (
    RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
    RECOVERY_INTENT_RESPONSE_CONTRACT,
)
from core.runtime.aer_runtime_recovery_controlled_activation import (
    RECOVERY_CONTROLLED_ACTIVATION_ALLOWED_STATUSES,
    RECOVERY_CONTROLLED_ACTIVATION_DENIED_CAPABILITIES,
    RECOVERY_CONTROLLED_ACTIVATION_REPORT_CONTRACT,
    prepare_recovery_controlled_activation,
)
from core.runtime.aer_runtime_recovery_native_adapter import prepare_recovery_native_adapter_report
from core.runtime.aer_runtime_recovery_operator_adapter import prepare_recovery_operator_adapter_report
from core.runtime.aer_runtime_recovery_runtime_integration import coordinate_recovery_runtime_integration
from core.runtime.aer_runtime_recovery_scheduler_adapter import prepare_recovery_scheduler_adapter_report
from core.runtime.aer_runtime_recovery_supervisor_adapter import prepare_recovery_supervisor_adapter_report
from core.runtime.aer_runtime_recovery_wiring_gate import prepare_recovery_wiring_gate_report


MODULE = Path("core/runtime/aer_runtime_recovery_controlled_activation.py")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _authority():
    return {
        "contract": RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
        "authority_request_id": "authority-165",
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


def _intent(authority):
    return {
        "contract": RECOVERY_INTENT_RESPONSE_CONTRACT,
        "intent_request_id": "intent-165",
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


def _gate_report():
    authority = _authority()
    integration = coordinate_recovery_runtime_integration(authority, _intent(authority), integration_id="controlled-165")
    activation = prepare_recovery_runtime_activation(integration, activation_id="controlled-165")
    return prepare_recovery_wiring_gate_report(
        prepare_recovery_scheduler_adapter_report(activation),
        prepare_recovery_operator_adapter_report(activation),
        prepare_recovery_supervisor_adapter_report(activation),
        prepare_recovery_native_adapter_report(activation),
        gate_id="controlled-165",
    )


def _package_entry() -> str:
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 165")
    end = text.find("## Package 166", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_controlled_activation_module_exists_and_public_api_is_fixed():
    assert MODULE.exists()
    assert controlled_module.__all__ == [
        "RECOVERY_CONTROLLED_ACTIVATION_REPORT_CONTRACT",
        "RECOVERY_CONTROLLED_ACTIVATION_ALLOWED_STATUSES",
        "RECOVERY_CONTROLLED_ACTIVATION_DENIED_CAPABILITIES",
        "prepare_recovery_controlled_activation",
    ]
    public_functions = {
        name
        for name, value in inspect.getmembers(controlled_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {"prepare_recovery_controlled_activation"}


def test_controlled_activation_prepares_without_activating_recovery():
    report = prepare_recovery_controlled_activation(
        _gate_report(),
        preparation_id="controlled-165",
        metadata={"package": 165},
    )

    assert report["contract"] == RECOVERY_CONTROLLED_ACTIVATION_REPORT_CONTRACT
    assert report["prepared"] is True
    assert report["blocked"] is False
    assert report["denied"] is False
    assert report["status"] == "prepared"
    assert report["activation_gate_enabled"] is False
    assert report["activation_allowed"] is False
    assert report["runtime_mainline_wiring_allowed"] is False
    assert report["preparation_only"] is True
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_controlled_activation_preserves_gate_and_adapter_references():
    gate = _gate_report()
    report = prepare_recovery_controlled_activation(gate)

    assert report["wiring_gate_reference"] == gate
    assert report["scheduler_adapter_reference"] == gate["scheduler_adapter_reference"]
    assert report["operator_adapter_reference"] == gate["operator_adapter_reference"]
    assert report["supervisor_adapter_reference"] == gate["supervisor_adapter_reference"]
    assert report["native_adapter_reference"] == gate["native_adapter_reference"]


def test_controlled_activation_blocks_invalid_gate_and_denies_activation_request():
    gate = _gate_report()
    gate["prepared"] = False
    blocked = prepare_recovery_controlled_activation(gate)
    denied = prepare_recovery_controlled_activation(_gate_report(), request_activation=True)

    assert blocked["status"] == "blocked"
    assert blocked["blocked"] is True
    assert blocked["wiring_gate_reference"] == {}
    assert denied["status"] == "denied"
    assert denied["denied"] is True
    assert denied["activation_allowed"] is False
    assert denied["reason"] == "activation request is prohibited during controlled activation preparation"


def test_controlled_activation_statuses_capabilities_and_determinism():
    assert RECOVERY_CONTROLLED_ACTIVATION_ALLOWED_STATUSES == ("prepared", "blocked", "denied")
    for capability in (
        "activate_recovery",
        "runtime_mainline_wiring",
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
        assert capability in RECOVERY_CONTROLLED_ACTIVATION_DENIED_CAPABILITIES

    gate = _gate_report()
    before = copy.deepcopy(gate)
    first = prepare_recovery_controlled_activation(gate, preparation_id="controlled-165")
    second = prepare_recovery_controlled_activation(copy.deepcopy(gate), preparation_id="controlled-165")
    assert first == second
    assert gate == before


def test_controlled_activation_module_has_no_forbidden_runtime_behavior_tokens():
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


def test_package_sequence_includes_package_165():
    entry = _package_entry()
    assert "## Package 165" in entry
    assert "Controlled Activation Preparation" in entry
    assert "core/runtime/aer_runtime_recovery_controlled_activation.py" in entry
    assert "tests/test_aer_runtime_recovery_controlled_activation.py" in entry
    assert "python -m pytest tests/test_aer_runtime_recovery_controlled_activation.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 166" in entry
