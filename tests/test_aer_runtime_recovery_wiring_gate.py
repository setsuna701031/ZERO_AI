import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_recovery_wiring_gate as gate_module
from core.runtime.aer_runtime_recovery_activation import prepare_recovery_runtime_activation
from core.runtime.aer_runtime_recovery_bridge import (
    RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
    RECOVERY_INTENT_RESPONSE_CONTRACT,
)
from core.runtime.aer_runtime_recovery_native_adapter import prepare_recovery_native_adapter_report
from core.runtime.aer_runtime_recovery_operator_adapter import prepare_recovery_operator_adapter_report
from core.runtime.aer_runtime_recovery_runtime_integration import coordinate_recovery_runtime_integration
from core.runtime.aer_runtime_recovery_scheduler_adapter import prepare_recovery_scheduler_adapter_report
from core.runtime.aer_runtime_recovery_supervisor_adapter import prepare_recovery_supervisor_adapter_report
from core.runtime.aer_runtime_recovery_wiring_gate import (
    RECOVERY_WIRING_GATE_ALLOWED_STATUSES,
    RECOVERY_WIRING_GATE_DENIED_CAPABILITIES,
    RECOVERY_WIRING_GATE_REPORT_CONTRACT,
    prepare_recovery_wiring_gate_report,
)


MODULE = Path("core/runtime/aer_runtime_recovery_wiring_gate.py")
CONTRACT = Path("docs/contracts/runtime/recovery_wiring_gate_v1.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _authority():
    return {
        "contract": RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
        "authority_request_id": "authority-164",
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
        "intent_request_id": "intent-164",
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


def _activation():
    authority = _authority()
    integration = coordinate_recovery_runtime_integration(authority, _intent(authority), integration_id="gate-164")
    return prepare_recovery_runtime_activation(integration, activation_id="gate-164")


def _adapters():
    activation = _activation()
    return (
        prepare_recovery_scheduler_adapter_report(activation),
        prepare_recovery_operator_adapter_report(activation),
        prepare_recovery_supervisor_adapter_report(activation),
        prepare_recovery_native_adapter_report(activation),
    )


def _package_entry() -> str:
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 164")
    end = text.find("## Package 165", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_wiring_gate_contract_doc_and_module_exist():
    assert CONTRACT.exists()
    assert MODULE.exists()


def test_wiring_gate_public_api_is_fixed():
    assert gate_module.__all__ == [
        "RECOVERY_WIRING_GATE_REPORT_CONTRACT",
        "RECOVERY_WIRING_GATE_ALLOWED_STATUSES",
        "RECOVERY_WIRING_GATE_DENIED_CAPABILITIES",
        "prepare_recovery_wiring_gate_report",
    ]
    public_functions = {
        name
        for name, value in inspect.getmembers(gate_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {"prepare_recovery_wiring_gate_report"}


def test_wiring_gate_prepares_report_with_gate_off_by_default():
    report = prepare_recovery_wiring_gate_report(*_adapters(), gate_id="gate-164")

    assert report["contract"] == RECOVERY_WIRING_GATE_REPORT_CONTRACT
    assert report["prepared"] is True
    assert report["blocked"] is False
    assert report["denied"] is False
    assert report["status"] == "prepared"
    assert report["activation_gate_enabled"] is False
    assert report["activation_allowed"] is False
    assert report["wiring_allowed"] is False
    assert report["gate_only"] is True
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_wiring_gate_preserves_adapter_references():
    adapters = _adapters()
    report = prepare_recovery_wiring_gate_report(*adapters)

    assert report["scheduler_adapter_reference"] == adapters[0]
    assert report["operator_adapter_reference"] == adapters[1]
    assert report["supervisor_adapter_reference"] == adapters[2]
    assert report["native_adapter_reference"] == adapters[3]


def test_wiring_gate_blocks_invalid_adapter_and_denies_gate_enablement():
    adapters = list(_adapters())
    adapters[0]["prepared"] = False
    blocked = prepare_recovery_wiring_gate_report(*adapters)
    denied = prepare_recovery_wiring_gate_report(*_adapters(), enable_activation_gate=True)

    assert blocked["status"] == "blocked"
    assert blocked["blocked"] is True
    assert blocked["scheduler_adapter_reference"] == {}
    assert denied["status"] == "denied"
    assert denied["denied"] is True
    assert denied["activation_gate_enabled"] is False
    assert denied["reason"] == "activation gate enablement is prohibited in passive wiring gate"


def test_wiring_gate_statuses_capabilities_and_determinism():
    assert RECOVERY_WIRING_GATE_ALLOWED_STATUSES == ("prepared", "blocked", "denied")
    for capability in (
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
        assert capability in RECOVERY_WIRING_GATE_DENIED_CAPABILITIES

    adapters = _adapters()
    before = copy.deepcopy(adapters)
    first = prepare_recovery_wiring_gate_report(*adapters, gate_id="gate-164")
    second = prepare_recovery_wiring_gate_report(*copy.deepcopy(adapters), gate_id="gate-164")
    assert first == second
    assert adapters == before


def test_wiring_gate_module_has_no_forbidden_runtime_behavior_tokens():
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


def test_package_sequence_includes_package_164():
    entry = _package_entry()
    assert "## Package 164" in entry
    assert "Recovery Wiring Gate Contract" in entry
    assert "docs/contracts/runtime/recovery_wiring_gate_v1.md" in entry
    assert "core/runtime/aer_runtime_recovery_wiring_gate.py" in entry
    assert "tests/test_aer_runtime_recovery_wiring_gate.py" in entry
    assert "python -m pytest tests/test_aer_runtime_recovery_wiring_gate.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 165" in entry
