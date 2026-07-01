import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_recovery_scheduler_adapter as adapter_module
from core.runtime.aer_runtime_recovery_activation import prepare_recovery_runtime_activation
from core.runtime.aer_runtime_recovery_bridge import (
    RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
    RECOVERY_INTENT_RESPONSE_CONTRACT,
)
from core.runtime.aer_runtime_recovery_runtime_integration import coordinate_recovery_runtime_integration
from core.runtime.aer_runtime_recovery_scheduler_adapter import (
    RECOVERY_SCHEDULER_ADAPTER_ALLOWED_STATUSES,
    RECOVERY_SCHEDULER_ADAPTER_DENIED_CAPABILITIES,
    RECOVERY_SCHEDULER_ADAPTER_REPORT_CONTRACT,
    prepare_recovery_scheduler_adapter_report,
)


MODULE = Path("core/runtime/aer_runtime_recovery_scheduler_adapter.py")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _authority():
    return {
        "contract": RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
        "authority_request_id": "authority-159",
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
        "intent_request_id": "intent-159",
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


def _activation_report():
    authority = _authority()
    integration = coordinate_recovery_runtime_integration(authority, _intent(authority), integration_id="adapter-159")
    return prepare_recovery_runtime_activation(integration, activation_id="adapter-159")


def _package_entry() -> str:
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 159")
    end = text.find("## Package 160", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_scheduler_adapter_module_exists_and_public_api_is_fixed():
    assert MODULE.exists()
    assert adapter_module.__all__ == [
        "RECOVERY_SCHEDULER_ADAPTER_REPORT_CONTRACT",
        "RECOVERY_SCHEDULER_ADAPTER_ALLOWED_STATUSES",
        "RECOVERY_SCHEDULER_ADAPTER_DENIED_CAPABILITIES",
        "prepare_recovery_scheduler_adapter_report",
    ]
    public_functions = {
        name
        for name, value in inspect.getmembers(adapter_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {"prepare_recovery_scheduler_adapter_report"}


def test_scheduler_adapter_prepares_report_without_runtime_effects():
    report = prepare_recovery_scheduler_adapter_report(
        _activation_report(),
        adapter_id="scheduler-159",
        metadata={"package": 159},
    )

    assert report["contract"] == RECOVERY_SCHEDULER_ADAPTER_REPORT_CONTRACT
    assert report["adapter_id"] == "scheduler-159"
    assert report["adapter_target"] == "scheduler"
    assert report["prepared"] is True
    assert report["blocked"] is False
    assert report["denied"] is False
    assert report["status"] == "prepared"
    assert report["adapter_only"] is True
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_scheduler_adapter_preserves_required_references():
    activation = _activation_report()
    report = prepare_recovery_scheduler_adapter_report(activation)

    assert report["activation_reference"] == activation
    assert report["authority_reference"] == activation["authority_reference"]
    assert report["intent_reference"] == activation["intent_reference"]
    assert report["bridge_reference"] == activation["bridge_reference"]
    assert report["executor_report_reference"] == activation["executor_report_reference"]


def test_scheduler_adapter_blocks_invalid_activation_and_denies_on_request():
    activation = _activation_report()
    activation["prepared"] = False
    blocked = prepare_recovery_scheduler_adapter_report(activation)
    denied = prepare_recovery_scheduler_adapter_report(_activation_report(), requested_status="denied")

    assert blocked["status"] == "blocked"
    assert blocked["blocked"] is True
    assert blocked["activation_reference"] == {}
    assert blocked["reason"] == "missing or incompatible passive Recovery activation references"
    assert denied["status"] == "denied"
    assert denied["denied"] is True


def test_scheduler_adapter_allowed_statuses_and_denied_capabilities_are_fixed():
    assert RECOVERY_SCHEDULER_ADAPTER_ALLOWED_STATUSES == ("prepared", "blocked", "denied")
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
        assert capability in RECOVERY_SCHEDULER_ADAPTER_DENIED_CAPABILITIES


def test_scheduler_adapter_is_deterministic_and_does_not_mutate_input():
    activation = _activation_report()
    before = copy.deepcopy(activation)

    first = prepare_recovery_scheduler_adapter_report(activation, adapter_id="scheduler-159")
    second = prepare_recovery_scheduler_adapter_report(copy.deepcopy(activation), adapter_id="scheduler-159")

    assert first == second
    assert activation == before


def test_scheduler_adapter_has_no_forbidden_runtime_behavior_tokens():
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


def test_package_sequence_includes_package_159():
    entry = _package_entry()
    assert "## Package 159" in entry
    assert "Scheduler Passive Adapter" in entry
    assert "core/runtime/aer_runtime_recovery_scheduler_adapter.py" in entry
    assert "tests/test_aer_runtime_recovery_scheduler_adapter.py" in entry
    assert "python -m pytest tests/test_aer_runtime_recovery_scheduler_adapter.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 160" in entry
