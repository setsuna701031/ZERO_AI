import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_recovery_bridge as bridge_module
from core.runtime.aer_runtime_recovery_bridge import (
    ALLOWED_RECOVERY_BRIDGE_CONSUMERS,
    RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
    RECOVERY_INTENT_RESPONSE_CONTRACT,
    RECOVERY_RUNTIME_BRIDGE_DENIED_CAPABILITIES,
    RECOVERY_RUNTIME_BRIDGE_RESPONSE_CONTRACT,
    RECOVERY_RUNTIME_BRIDGE_SCOPE,
    build_recovery_runtime_bridge_report,
)


MODULE = Path("core/runtime/aer_runtime_recovery_bridge.py")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _authority(**overrides):
    payload = {
        "contract": RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
        "authority_request_id": "authority-001",
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


def _intent(**overrides):
    payload = {
        "contract": RECOVERY_INTENT_RESPONSE_CONTRACT,
        "intent_request_id": "intent-001",
        "intent_owner": "runtime_recovery_execution_intent",
        "authority_reference": {"authority_request_id": "authority-001"},
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


def _package_149_entry():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 149")
    end = text.find("## Package 150", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_bridge_module_exists_and_public_api_is_fixed():
    assert MODULE.exists()
    assert bridge_module.__all__ == [
        "RECOVERY_RUNTIME_BRIDGE_RESPONSE_CONTRACT",
        "RECOVERY_AUTHORITY_RESPONSE_CONTRACT",
        "RECOVERY_INTENT_RESPONSE_CONTRACT",
        "ALLOWED_RECOVERY_BRIDGE_CONSUMERS",
        "RECOVERY_RUNTIME_BRIDGE_SCOPE",
        "RECOVERY_RUNTIME_BRIDGE_DENIED_CAPABILITIES",
        "build_recovery_runtime_bridge_report",
    ]

    public_functions = {
        name
        for name, value in inspect.getmembers(bridge_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {"build_recovery_runtime_bridge_report"}


def test_valid_authority_and_intent_are_accepted_for_allowed_consumer():
    report = build_recovery_runtime_bridge_report(
        _authority(),
        _intent(),
        bridge_consumer="runtime_recovery_runtime_bridge",
        bridge_request_id="bridge-001",
        metadata={"package": 149, "tags": ("bridge",)},
    )

    assert report == {
        "contract": RECOVERY_RUNTIME_BRIDGE_RESPONSE_CONTRACT,
        "bridge_request_id": "bridge-001",
        "bridge_consumer": "runtime_recovery_runtime_bridge",
        "accepted": True,
        "rejected": False,
        "status": "accepted_bridge_only",
        "authority_reference": _authority(),
        "intent_reference": _intent(),
        "bridge_scope": RECOVERY_RUNTIME_BRIDGE_SCOPE,
        "denied_capabilities": list(RECOVERY_RUNTIME_BRIDGE_DENIED_CAPABILITIES),
        "reason": None,
        "metadata": {"package": 149, "tags": ["bridge"]},
        "executes_recovery": False,
        "bridge_only": True,
    }


def test_invalid_authority_is_blocked():
    report = build_recovery_runtime_bridge_report(
        _authority(authorized=False, decision="denied_by_authority"),
        _intent(),
        bridge_consumer="runtime_recovery_runtime_bridge",
    )

    assert report["accepted"] is False
    assert report["rejected"] is True
    assert report["status"] == "blocked_missing_or_invalid_authority"
    assert report["authority_reference"] == {}
    assert report["intent_reference"] == _intent()
    assert report["bridge_scope"] is None
    assert report["reason"] == "missing or invalid recovery execution authority reference"
    assert report["executes_recovery"] is False


def test_invalid_intent_is_blocked():
    report = build_recovery_runtime_bridge_report(
        _authority(),
        _intent(accepted=False, status="forbidden_intent_action"),
        bridge_consumer="runtime_recovery_runtime_bridge",
    )

    assert report["accepted"] is False
    assert report["rejected"] is True
    assert report["status"] == "blocked_missing_or_invalid_intent"
    assert report["authority_reference"] == _authority()
    assert report["intent_reference"] == {}
    assert report["bridge_scope"] is None
    assert report["reason"] == "missing or invalid recovery execution intent reference"


def test_forbidden_consumer_is_denied():
    report = build_recovery_runtime_bridge_report(
        _authority(),
        _intent(),
        bridge_consumer="scheduler",
    )

    assert report["accepted"] is False
    assert report["rejected"] is True
    assert report["status"] == "denied_forbidden_bridge_consumer"
    assert report["bridge_scope"] is None
    assert report["reason"] == "forbidden recovery runtime bridge consumer"
    assert "scheduler_admission" in report["denied_capabilities"]


def test_allowed_consumer_and_denied_capability_vocabulary_is_fixed():
    assert ALLOWED_RECOVERY_BRIDGE_CONSUMERS == {
        "runtime_recovery_runtime_bridge",
        "runtime_recovery_executor_boundary",
        "runtime_recovery_bridge_review",
    }
    assert RECOVERY_RUNTIME_BRIDGE_DENIED_CAPABILITIES == (
        "recovery_execution",
        "scheduler_admission",
        "dispatcher_command",
        "operator_action",
        "runtime_supervision",
        "persistence_write",
        "audit_emission",
        "journal_event",
        "replay_action",
        "runtime_mutation",
        "file_mutation",
        "external_process_call",
    )


def test_bridge_output_is_deterministic_and_does_not_mutate_inputs():
    authority = _authority()
    intent = _intent()
    before_authority = copy.deepcopy(authority)
    before_intent = copy.deepcopy(intent)

    first = build_recovery_runtime_bridge_report(
        authority,
        intent,
        bridge_consumer="runtime_recovery_runtime_bridge",
    )
    second = build_recovery_runtime_bridge_report(
        copy.deepcopy(authority),
        copy.deepcopy(intent),
        bridge_consumer="runtime_recovery_runtime_bridge",
    )

    assert first == second
    assert authority == before_authority
    assert intent == before_intent


def test_bridge_output_is_independent_plain_dict_data():
    authority = _authority()
    intent = _intent()
    report = build_recovery_runtime_bridge_report(
        authority,
        intent,
        bridge_consumer="runtime_recovery_runtime_bridge",
    )

    authority["decision"] = "mutated"
    intent["intended_actions"].append("mutated")

    assert report["authority_reference"]["decision"] == "authorized_for_future_handoff"
    assert report["intent_reference"]["intended_actions"] == ["describe_recovery_execution_intent"]
    assert type(report) is dict
    assert type(report["authority_reference"]) is dict
    assert type(report["intent_reference"]) is dict


def test_no_execution_behavior_or_surfaces_exist():
    assert not hasattr(bridge_module, "recover")
    assert not hasattr(bridge_module, "execute_recovery")
    assert not hasattr(bridge_module, "schedule")
    assert not hasattr(bridge_module, "dispatch")
    assert not hasattr(bridge_module, "persist")
    assert not hasattr(bridge_module, "audit")
    assert not hasattr(bridge_module, "journal")
    assert not hasattr(bridge_module, "replay")


def test_forbidden_imports_and_behavior_tokens_are_absent():
    text = MODULE.read_text(encoding="utf-8")
    for token in (
        "import os",
        "import subprocess",
        "import pathlib",
        "from pathlib",
        "import scheduler",
        "import dispatcher",
        "import operator",
        "import persistence",
        "import audit",
        "import journal",
        "import replay",
        "from core.runtime.aer_runtime_recovery import",
        "import core.runtime.aer_runtime_recovery",
        "from core.runtime.runtime_recovery",
        "recover(",
        "execute_recovery(",
        "schedule(",
        "dispatch(",
        "operate(",
        "persist(",
        "audit(",
        "journal(",
        "replay(",
        "Popen",
        "run(",
        "open(",
        "write(",
    ):
        assert token not in text


def test_package_sequence_includes_package_149_and_next_recommendation():
    entry = _package_149_entry()
    assert "## Package 149" in entry
    assert "Package 149: Runtime Recovery Runtime Bridge" in entry
    assert "python -m pytest tests/test_aer_runtime_recovery_bridge.py -q" in entry
    assert "passive bridge helper" in entry
    assert "does not execute Recovery" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 150" in entry
