import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_recovery_activation as activation_module
from core.runtime.aer_runtime_recovery_activation import (
    RECOVERY_ACTIVATION_ALLOWED_STATES,
    RECOVERY_ACTIVATION_DENIED_RUNTIME_HOOKS,
    RECOVERY_ACTIVATION_FORBIDDEN_STATES,
    RECOVERY_ACTIVATION_REQUEST_CONTRACT,
    RECOVERY_ACTIVATION_RESPONSE_CONTRACT,
    prepare_recovery_runtime_activation,
)
from core.runtime.aer_runtime_recovery_bridge import (
    RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
    RECOVERY_INTENT_RESPONSE_CONTRACT,
)
from core.runtime.aer_runtime_recovery_runtime_integration import coordinate_recovery_runtime_integration


MODULE = Path("core/runtime/aer_runtime_recovery_activation.py")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _authority(**overrides):
    payload = {
        "contract": RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
        "authority_request_id": "authority-157",
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
    payload.update(overrides)
    return payload


def _intent(authority, **overrides):
    payload = {
        "contract": RECOVERY_INTENT_RESPONSE_CONTRACT,
        "intent_request_id": "intent-157",
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
    payload.update(overrides)
    return payload


def _integration_report():
    authority = _authority()
    return coordinate_recovery_runtime_integration(
        authority,
        _intent(authority),
        integration_id="activation-157",
    )


def _package_157_entry() -> str:
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 157")
    end = text.find("## Package 158", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_activation_module_exists_and_public_api_is_fixed():
    assert MODULE.exists()
    assert activation_module.__all__ == [
        "RECOVERY_ACTIVATION_REQUEST_CONTRACT",
        "RECOVERY_ACTIVATION_RESPONSE_CONTRACT",
        "RECOVERY_ACTIVATION_ALLOWED_STATES",
        "RECOVERY_ACTIVATION_FORBIDDEN_STATES",
        "RECOVERY_ACTIVATION_DENIED_RUNTIME_HOOKS",
        "prepare_recovery_runtime_activation",
    ]

    public_functions = {
        name
        for name, value in inspect.getmembers(activation_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {"prepare_recovery_runtime_activation"}


def test_valid_integration_report_prepares_activation_without_side_effects():
    integration = _integration_report()
    report = prepare_recovery_runtime_activation(
        integration,
        activation_id="activation-157",
        metadata={"package": 157},
    )

    assert report["contract"] == RECOVERY_ACTIVATION_RESPONSE_CONTRACT
    assert report["activation_request"]["contract"] == RECOVERY_ACTIVATION_REQUEST_CONTRACT
    assert report["activation_id"] == "activation-157"
    assert report["prepared"] is True
    assert report["blocked"] is False
    assert report["denied"] is False
    assert report["activation_state"] == "prepared"
    assert report["activation_only"] is True
    assert report["executes_recovery"] is False
    assert report["side_effects_performed"] is False
    assert report["plain_dict_only"] is True


def test_activation_preserves_required_references():
    integration = _integration_report()
    report = prepare_recovery_runtime_activation(integration)

    assert report["integration_report_reference"] == integration
    assert report["authority_reference"] == integration["authority_reference"]
    assert report["intent_reference"] == integration["intent_reference"]
    assert report["bridge_reference"] == integration["bridge_report"]
    assert report["executor_report_reference"] == integration["executor_report"]
    assert report["activation_request"]["authority_reference"] == integration["authority_reference"]
    assert report["activation_request"]["intent_reference"] == integration["intent_reference"]
    assert report["activation_request"]["bridge_reference"] == integration["bridge_report"]
    assert report["activation_request"]["executor_report_reference"] == integration["executor_report"]


def test_invalid_integration_blocks_activation_without_runtime_hooks():
    integration = _integration_report()
    integration["accepted"] = False

    report = prepare_recovery_runtime_activation(integration)

    assert report["prepared"] is False
    assert report["blocked"] is True
    assert report["denied"] is False
    assert report["activation_state"] == "blocked"
    assert report["integration_report_reference"] == {}
    assert report["reason"] == "missing or incompatible passive Recovery activation references"
    assert report["executes_recovery"] is False
    assert "scheduler_admission" in report["denied_runtime_hooks"]


def test_forbidden_activation_state_is_denied():
    report = prepare_recovery_runtime_activation(_integration_report(), requested_state="scheduled")

    assert report["prepared"] is False
    assert report["blocked"] is False
    assert report["denied"] is True
    assert report["activation_state"] == "denied"
    assert report["reason"] == "forbidden activation state: scheduled"
    assert "scheduled" in RECOVERY_ACTIVATION_FORBIDDEN_STATES


def test_allowed_states_and_denied_runtime_hooks_are_fixed():
    assert RECOVERY_ACTIVATION_ALLOWED_STATES == ("prepared", "blocked", "denied")
    assert "activated" in RECOVERY_ACTIVATION_FORBIDDEN_STATES
    assert "executed" in RECOVERY_ACTIVATION_FORBIDDEN_STATES
    for hook in (
        "scheduler_admission",
        "dispatcher_command",
        "operator_runtime_action",
        "runtime_supervisor",
        "native_runtime_execution",
        "persistence_write",
        "replay_action",
        "audit_emission",
        "journal_event",
        "subprocess_call",
        "file_io",
        "runtime_mutation",
    ):
        assert hook in RECOVERY_ACTIVATION_DENIED_RUNTIME_HOOKS


def test_output_is_deterministic_and_does_not_mutate_input():
    integration = _integration_report()
    before = copy.deepcopy(integration)

    first = prepare_recovery_runtime_activation(integration, activation_id="activation-157")
    second = prepare_recovery_runtime_activation(copy.deepcopy(integration), activation_id="activation-157")

    assert first == second
    assert integration == before


def test_activation_helper_has_no_forbidden_runtime_behavior_tokens():
    text = MODULE.read_text(encoding="utf-8")
    for token in (
        "import os",
        "import subprocess",
        "import pathlib",
        "from pathlib",
        "import scheduler",
        "import dispatcher",
        "import operator",
        "scheduler.",
        "dispatcher.",
        "operator.",
        "Popen",
        "run(",
        "open(",
        "write(",
        "Path(",
    ):
        assert token not in text


def test_package_sequence_includes_package_157_and_next_recommendation():
    entry = _package_157_entry()
    assert "## Package 157" in entry
    assert "Recovery Runtime Activation Helper" in entry
    assert "core/runtime/aer_runtime_recovery_activation.py" in entry
    assert "tests/test_aer_runtime_recovery_activation.py" in entry
    assert "python -m pytest tests/test_aer_runtime_recovery_activation.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 158" in entry
