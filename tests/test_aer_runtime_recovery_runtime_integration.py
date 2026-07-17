import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_recovery_runtime_integration as integration_module
from core.runtime.aer_runtime_recovery_bridge import (
    RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
    RECOVERY_INTENT_RESPONSE_CONTRACT,
)
from core.runtime.aer_runtime_recovery_runtime_integration import (
    RECOVERY_RUNTIME_INTEGRATION_REPORT_CONTRACT,
    coordinate_recovery_runtime_integration,
)


MODULE = Path("core/runtime/aer_runtime_recovery_runtime_integration.py")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _authority(**overrides):
    payload = {
        "contract": RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
        "authority_request_id": "authority-152",
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
        "intent_request_id": "intent-152",
        "intent_owner": "runtime_recovery_execution_intent",
        "authority_reference": {"authority_request_id": "authority-152"},
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


def _package_152_entry():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 152")
    end = text.find("## Package 153", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_runtime_integration_module_exists_and_public_api_is_fixed():
    assert MODULE.exists()
    assert integration_module.__all__ == [
        "RECOVERY_RUNTIME_INTEGRATION_REPORT_CONTRACT",
        "coordinate_recovery_runtime_integration",
    ]

    public_functions = {
        name
        for name, value in inspect.getmembers(integration_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {"coordinate_recovery_runtime_integration"}


def test_valid_authority_and_intent_coordinate_through_bridge_and_executor():
    report = coordinate_recovery_runtime_integration(
        _authority(),
        _intent(),
        integration_id="integration-152",
        metadata={"package": 152},
    )

    assert report["contract"] == RECOVERY_RUNTIME_INTEGRATION_REPORT_CONTRACT
    assert report["integration_id"] == "integration-152"
    assert report["accepted"] is True
    assert report["status"] == "integrated_no_side_effects"
    assert report["bridge_report"]["accepted"] is True
    assert report["bridge_report"]["status"] == "accepted_bridge_only"
    assert report["executor_boundary"]["boundary_only"] is True
    assert report["executor_report"]["accepted"] is True
    assert report["executor_report"]["status"] == "prepared_no_side_effects"
    assert report["external_runtime_invoked"] is False
    assert report["side_effects_performed"] is False
    assert report["executes_recovery"] is False
    assert report["plain_dict_only"] is True


def test_invalid_authority_blocks_pipeline_without_external_runtime():
    report = coordinate_recovery_runtime_integration(
        _authority(authorized=False, decision="denied_by_authority"),
        _intent(),
        integration_id="integration-152",
    )

    assert report["accepted"] is False
    assert report["status"] == "blocked_runtime_integration"
    assert report["bridge_report"]["status"] == "blocked_missing_or_invalid_authority"
    assert report["executor_report"]["status"] == "blocked_invalid_bridge"
    assert report["external_runtime_invoked"] is False
    assert report["executes_recovery"] is False


def test_invalid_intent_blocks_pipeline_without_external_runtime():
    report = coordinate_recovery_runtime_integration(
        _authority(),
        _intent(accepted=False, status="forbidden_intent_action"),
        integration_id="integration-152",
    )

    assert report["accepted"] is False
    assert report["status"] == "blocked_runtime_integration"
    assert report["bridge_report"]["status"] == "blocked_missing_or_invalid_intent"
    assert report["executor_report"]["status"] == "blocked_invalid_bridge"
    assert report["external_runtime_invoked"] is False


def test_references_are_preserved_through_pipeline():
    authority = _authority()
    intent = _intent()
    report = coordinate_recovery_runtime_integration(authority, intent)

    assert report["authority_reference"] == authority
    assert report["intent_reference"] == intent
    assert report["bridge_report"]["authority_reference"] == authority
    assert report["bridge_report"]["intent_reference"] == intent
    assert report["executor_boundary"]["authority_reference"] == authority
    assert report["executor_boundary"]["intent_reference"] == intent
    assert report["executor_report"]["authority_reference"] == authority
    assert report["executor_report"]["intent_reference"] == intent


def test_output_is_deterministic_and_does_not_mutate_inputs():
    authority = _authority()
    intent = _intent()
    before_authority = copy.deepcopy(authority)
    before_intent = copy.deepcopy(intent)

    first = coordinate_recovery_runtime_integration(authority, intent)
    second = coordinate_recovery_runtime_integration(copy.deepcopy(authority), copy.deepcopy(intent))

    assert first == second
    assert authority == before_authority
    assert intent == before_intent


def test_forbidden_runtime_component_imports_are_absent():
    text = MODULE.read_text(encoding="utf-8")
    assert "aer_runtime_recovery_bridge" in text
    assert "aer_runtime_recovery_executor" in text
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


def test_package_sequence_includes_package_152_and_next_recommendation():
    entry = _package_152_entry()
    assert "## Package 152" in entry
    assert "Recovery Runtime Integration" in entry
    assert "core/runtime/aer_runtime_recovery_runtime_integration.py" in entry
    assert "python -m pytest tests/test_aer_runtime_recovery_runtime_integration.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 153" in entry
