import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_recovery_executor as executor_module
from core.runtime.aer_runtime_recovery_bridge import (
    RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
    RECOVERY_INTENT_RESPONSE_CONTRACT,
    build_recovery_runtime_bridge_report,
)
from core.runtime.aer_runtime_recovery_executor import (
    RECOVERY_EXECUTOR_ALLOWED_STATUS,
    RECOVERY_EXECUTOR_BOUNDARY_INPUT_CONTRACT,
    RECOVERY_EXECUTOR_DENIED_CAPABILITIES,
    RECOVERY_EXECUTOR_REPORT_CONTRACT,
    build_recovery_executor_report,
)


MODULE = Path("core/runtime/aer_runtime_recovery_executor.py")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _authority(**overrides):
    payload = {
        "contract": RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
        "authority_request_id": "authority-151",
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
        "intent_request_id": "intent-151",
        "intent_owner": "runtime_recovery_execution_intent",
        "authority_reference": {"authority_request_id": "authority-151"},
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


def _bridge():
    return build_recovery_runtime_bridge_report(
        _authority(),
        _intent(),
        bridge_consumer="runtime_recovery_runtime_bridge",
        bridge_request_id="bridge-151",
    )


def _boundary(bridge):
    return {
        "contract": RECOVERY_EXECUTOR_BOUNDARY_INPUT_CONTRACT,
        "executor_boundary_id": "boundary-151",
        "bridge_reference": bridge,
        "authority_reference": bridge["authority_reference"],
        "intent_reference": bridge["intent_reference"],
        "requested_executor_scope": "executor_boundary_review_only",
        "metadata": {},
        "boundary_only": True,
    }


def _package_151_entry():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 151")
    end = text.find("## Package 152", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_executor_module_exists_and_public_api_is_fixed():
    assert MODULE.exists()
    assert executor_module.__all__ == [
        "RECOVERY_EXECUTOR_REPORT_CONTRACT",
        "RECOVERY_EXECUTOR_BOUNDARY_INPUT_CONTRACT",
        "RECOVERY_EXECUTOR_ALLOWED_STATUS",
        "RECOVERY_EXECUTOR_DENIED_CAPABILITIES",
        "build_recovery_executor_report",
    ]

    public_functions = {
        name
        for name, value in inspect.getmembers(executor_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {"build_recovery_executor_report"}


def test_authorized_bridge_and_boundary_produce_deterministic_report():
    bridge = _bridge()
    boundary = _boundary(bridge)

    report = build_recovery_executor_report(
        bridge,
        boundary,
        executor_id="executor-151",
        metadata={"package": 151, "tags": ("executor",)},
    )

    assert report == {
        "contract": RECOVERY_EXECUTOR_REPORT_CONTRACT,
        "executor_id": "executor-151",
        "accepted": True,
        "rejected": False,
        "status": RECOVERY_EXECUTOR_ALLOWED_STATUS,
        "bridge_reference": bridge,
        "authority_reference": bridge["authority_reference"],
        "intent_reference": bridge["intent_reference"],
        "executor_boundary_reference": boundary,
        "execution_report": {
            "prepared": True,
            "performed_side_effects": False,
            "scheduled": False,
            "dispatched": False,
            "persisted": False,
            "replayed": False,
            "audited": False,
            "journaled": False,
        },
        "denied_capabilities": list(RECOVERY_EXECUTOR_DENIED_CAPABILITIES),
        "reason": None,
        "metadata": {"package": 151, "tags": ["executor"]},
        "side_effects_performed": False,
        "executes_recovery": False,
        "plain_dict_only": True,
    }


def test_invalid_bridge_is_blocked():
    bridge = _bridge()
    bridge["accepted"] = False
    boundary = _boundary(bridge)

    report = build_recovery_executor_report(bridge, boundary)

    assert report["accepted"] is False
    assert report["status"] == "blocked_invalid_bridge"
    assert report["bridge_reference"] == {}
    assert report["execution_report"]["prepared"] is False
    assert report["reason"] == "invalid recovery runtime bridge payload"


def test_invalid_authority_reference_is_blocked():
    bridge = _bridge()
    bridge["authority_reference"]["authorized"] = False
    boundary = _boundary(bridge)

    report = build_recovery_executor_report(bridge, boundary)

    assert report["accepted"] is False
    assert report["status"] == "blocked_invalid_authority"
    assert report["authority_reference"] == {}
    assert report["reason"] == "invalid recovery execution authority reference"


def test_invalid_intent_reference_is_blocked():
    bridge = _bridge()
    bridge["intent_reference"]["accepted"] = False
    boundary = _boundary(bridge)

    report = build_recovery_executor_report(bridge, boundary)

    assert report["accepted"] is False
    assert report["status"] == "blocked_invalid_intent"
    assert report["intent_reference"] == {}
    assert report["reason"] == "invalid recovery execution intent reference"


def test_invalid_executor_boundary_is_blocked():
    bridge = _bridge()
    boundary = _boundary(bridge)
    boundary["boundary_only"] = False

    report = build_recovery_executor_report(bridge, boundary)

    assert report["accepted"] is False
    assert report["status"] == "blocked_invalid_executor_boundary"
    assert report["executor_boundary_reference"] == {}
    assert report["reason"] == "invalid recovery executor boundary requirements"


def test_output_is_deterministic_and_does_not_mutate_inputs():
    bridge = _bridge()
    boundary = _boundary(bridge)
    before_bridge = copy.deepcopy(bridge)
    before_boundary = copy.deepcopy(boundary)

    first = build_recovery_executor_report(bridge, boundary)
    second = build_recovery_executor_report(copy.deepcopy(bridge), copy.deepcopy(boundary))

    assert first == second
    assert bridge == before_bridge
    assert boundary == before_boundary


def test_denied_capabilities_keep_runtime_side_effects_off():
    assert RECOVERY_EXECUTOR_DENIED_CAPABILITIES == (
        "scheduler_admission",
        "dispatcher_command",
        "operator_action",
        "runtime_supervision",
        "subprocess_call",
        "repository_mutation",
        "persistence_write",
        "replay_action",
        "audit_emission",
        "journal_event",
        "runtime_mutation",
    )

    report = build_recovery_executor_report(_bridge(), _boundary(_bridge()))
    assert report["side_effects_performed"] is False
    assert report["executes_recovery"] is False


def test_no_forbidden_runtime_surfaces_exist():
    for name in (
        "schedule",
        "dispatch",
        "spawn",
        "persist",
        "replay",
        "audit",
        "journal",
        "mutate_repository",
    ):
        assert not hasattr(executor_module, name)


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
        "schedule(",
        "dispatch(",
        "Popen",
        "run(",
        "open(",
        "write(",
    ):
        assert token not in text


def test_package_sequence_includes_package_151_and_next_recommendation():
    entry = _package_151_entry()
    assert "## Package 151" in entry
    assert "Runtime Recovery Executor" in entry
    assert "core/runtime/aer_runtime_recovery_executor.py" in entry
    assert "python -m pytest tests/test_aer_runtime_recovery_executor.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 152" in entry
