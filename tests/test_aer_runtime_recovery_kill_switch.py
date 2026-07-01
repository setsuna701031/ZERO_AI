import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_recovery_kill_switch as kill_switch_module
from core.runtime.aer_runtime_recovery_activation import prepare_recovery_runtime_activation
from core.runtime.aer_runtime_recovery_bridge import (
    RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
    RECOVERY_INTENT_RESPONSE_CONTRACT,
)
from core.runtime.aer_runtime_recovery_controlled_activation import prepare_recovery_controlled_activation
from core.runtime.aer_runtime_recovery_kill_switch import (
    RECOVERY_KILL_SWITCH_ALLOWED_STATUSES,
    RECOVERY_KILL_SWITCH_DENIED_CAPABILITIES,
    RECOVERY_KILL_SWITCH_REPORT_CONTRACT,
    prepare_recovery_kill_switch_report,
)
from core.runtime.aer_runtime_recovery_native_adapter import prepare_recovery_native_adapter_report
from core.runtime.aer_runtime_recovery_operator_adapter import prepare_recovery_operator_adapter_report
from core.runtime.aer_runtime_recovery_runtime_integration import coordinate_recovery_runtime_integration
from core.runtime.aer_runtime_recovery_scheduler_adapter import prepare_recovery_scheduler_adapter_report
from core.runtime.aer_runtime_recovery_supervisor_adapter import prepare_recovery_supervisor_adapter_report
from core.runtime.aer_runtime_recovery_wiring_gate import prepare_recovery_wiring_gate_report


MODULE = Path("core/runtime/aer_runtime_recovery_kill_switch.py")
CONTRACT = Path("docs/contracts/runtime/recovery_kill_switch_v1.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _controlled_report():
    authority = {
        "contract": RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
        "authority_request_id": "authority-168",
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
        "intent_request_id": "intent-168",
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
    integration = coordinate_recovery_runtime_integration(authority, intent, integration_id="kill-168")
    activation = prepare_recovery_runtime_activation(integration, activation_id="kill-168")
    gate = prepare_recovery_wiring_gate_report(
        prepare_recovery_scheduler_adapter_report(activation),
        prepare_recovery_operator_adapter_report(activation),
        prepare_recovery_supervisor_adapter_report(activation),
        prepare_recovery_native_adapter_report(activation),
        gate_id="kill-168",
    )
    return prepare_recovery_controlled_activation(gate, preparation_id="kill-168")


def _package_entry() -> str:
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 168")
    end = text.find("## Package 169", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_kill_switch_contract_and_module_exist():
    assert CONTRACT.exists()
    assert MODULE.exists()


def test_kill_switch_public_api_is_fixed():
    assert kill_switch_module.__all__ == [
        "RECOVERY_KILL_SWITCH_REPORT_CONTRACT",
        "RECOVERY_KILL_SWITCH_ALLOWED_STATUSES",
        "RECOVERY_KILL_SWITCH_DENIED_CAPABILITIES",
        "prepare_recovery_kill_switch_report",
    ]
    public_functions = {
        name
        for name, value in inspect.getmembers(kill_switch_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {"prepare_recovery_kill_switch_report"}


def test_kill_switch_defaults_to_disabled_off_safe():
    controlled = _controlled_report()
    report = prepare_recovery_kill_switch_report(controlled, kill_switch_id="kill-168")

    assert report["contract"] == RECOVERY_KILL_SWITCH_REPORT_CONTRACT
    assert report["prepared"] is True
    assert report["blocked"] is False
    assert report["denied"] is False
    assert report["status"] == "prepared"
    assert report["kill_switch_enabled"] is False
    assert report["kill_switch_state"] == "off"
    assert report["safe_mode"] is True
    assert report["recovery_enabled"] is False
    assert report["controlled_activation_reference"] == controlled
    assert report["kill_switch_only"] is True
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_kill_switch_blocks_invalid_controlled_report_and_denies_enablement():
    controlled = _controlled_report()
    controlled["prepared"] = False
    blocked = prepare_recovery_kill_switch_report(controlled)
    denied = prepare_recovery_kill_switch_report(_controlled_report(), request_enablement=True)

    assert blocked["status"] == "blocked"
    assert blocked["controlled_activation_reference"] == {}
    assert denied["status"] == "denied"
    assert denied["kill_switch_enabled"] is False
    assert denied["recovery_enabled"] is False
    assert denied["reason"] == "Recovery enablement is prohibited by default kill-switch semantics"


def test_kill_switch_statuses_capabilities_and_determinism():
    assert RECOVERY_KILL_SWITCH_ALLOWED_STATUSES == ("prepared", "blocked", "denied")
    for capability in (
        "recovery_enablement",
        "recovery_execution",
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
        assert capability in RECOVERY_KILL_SWITCH_DENIED_CAPABILITIES

    controlled = _controlled_report()
    before = copy.deepcopy(controlled)
    first = prepare_recovery_kill_switch_report(controlled, kill_switch_id="kill-168")
    second = prepare_recovery_kill_switch_report(copy.deepcopy(controlled), kill_switch_id="kill-168")
    assert first == second
    assert controlled == before


def test_kill_switch_module_has_no_forbidden_runtime_behavior_tokens():
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


def test_package_sequence_includes_package_168():
    entry = _package_entry()
    assert "## Package 168" in entry
    assert "Runtime Recovery Kill Switch Contract" in entry
    assert "docs/contracts/runtime/recovery_kill_switch_v1.md" in entry
    assert "core/runtime/aer_runtime_recovery_kill_switch.py" in entry
    assert "tests/test_aer_runtime_recovery_kill_switch.py" in entry
    assert "python -m pytest tests/test_aer_runtime_recovery_kill_switch.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 169" in entry
