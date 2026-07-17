import copy
from pathlib import Path

from core.runtime.aer_runtime_recovery_bridge import (
    RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
    RECOVERY_INTENT_RESPONSE_CONTRACT,
)
from core.runtime.aer_runtime_recovery_consumer_boundary import describe_recovery_plan_consumption
from core.runtime.aer_runtime_recovery_planner import build_recovery_plan
from core.runtime.aer_runtime_recovery_runtime_integration import coordinate_recovery_runtime_integration
from core.runtime.aer_runtime_recovery_validation import RECOVERY_ELIGIBILITY_CONTRACT, validate_recovery_plan


PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _eligibility():
    return {
        "contract": RECOVERY_ELIGIBILITY_CONTRACT,
        "eligible": True,
        "blocked": False,
        "status": "eligible",
        "reason": None,
        "execution_summary": {
            "status": "failed",
            "source": "resume_execution_consumer",
            "request_id": "execution-request-154",
        },
        "failure_classification": "scheduler_required",
        "recovery_authorized": True,
        "descriptive_only": True,
    }


def _authority(recovery_token):
    return {
        "contract": RECOVERY_AUTHORITY_RESPONSE_CONTRACT,
        "authority_request_id": "authority-154",
        "authority_owner": "runtime_recovery_execution_authority",
        "authorized": True,
        "decision": "authorized_for_future_handoff",
        "state": "authorized",
        "reason": None,
        "authorized_scope": "future_handoff",
        "downstream_requirements": ["runtime_recovery_execution_intent"],
        "denied_capabilities": ["recovery_execution"],
        "recovery_token": recovery_token,
        "executes_recovery": False,
        "authority_only": True,
    }


def _intent(authority):
    return {
        "contract": RECOVERY_INTENT_RESPONSE_CONTRACT,
        "intent_request_id": "intent-154",
        "intent_owner": "runtime_recovery_execution_intent",
        "authority_reference": authority,
        "accepted": True,
        "status": "accepted_intent_only",
        "state": "described",
        "intended_actions": [
            "describe_recovery_execution_intent",
            "describe_recovery_plan_handoff_intent",
        ],
        "denied_actions": [],
        "denied_capabilities": ["recovery_execution"],
        "reason": None,
        "executes_recovery": False,
        "intent_only": True,
    }


def _package_154_entry():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 154")
    end = text.find("## Package 155", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_complete_recovery_chain_is_deterministic_and_passive():
    eligibility = _eligibility()
    plan = build_recovery_plan(eligibility)
    boundary = describe_recovery_plan_consumption(
        plan,
        consumer_type="runtime_recovery_consumer_boundary",
    )
    authority = _authority(plan["recovery_token"])
    intent = _intent(authority)

    first = coordinate_recovery_runtime_integration(authority, intent, integration_id="integration-154")
    second = coordinate_recovery_runtime_integration(
        copy.deepcopy(authority),
        copy.deepcopy(intent),
        integration_id="integration-154",
    )

    assert validate_recovery_plan(plan)["valid"] is True
    assert boundary["accepted"] is True
    assert first == second
    assert first["accepted"] is True
    assert first["executes_recovery"] is False
    assert first["side_effects_performed"] is False
    assert first["external_runtime_invoked"] is False


def test_ownership_authority_bridge_and_executor_boundary_are_preserved():
    plan = build_recovery_plan(_eligibility())
    authority = _authority(plan["recovery_token"])
    intent = _intent(authority)
    report = coordinate_recovery_runtime_integration(authority, intent, integration_id="integration-154")

    assert report["authority_reference"] == authority
    assert report["intent_reference"] == intent
    assert report["bridge_report"]["authority_reference"] == authority
    assert report["bridge_report"]["intent_reference"] == intent
    assert report["executor_boundary"]["bridge_reference"] == report["bridge_report"]
    assert report["executor_boundary"]["authority_reference"] == authority
    assert report["executor_boundary"]["intent_reference"] == intent
    assert report["executor_report"]["bridge_reference"] == report["bridge_report"]
    assert report["executor_report"]["executor_boundary_reference"] == report["executor_boundary"]


def test_complete_chain_reports_denied_runtime_effects():
    plan = build_recovery_plan(_eligibility())
    report = coordinate_recovery_runtime_integration(
        _authority(plan["recovery_token"]),
        _intent(_authority(plan["recovery_token"])),
    )

    executor = report["executor_report"]
    execution_report = executor["execution_report"]

    assert execution_report == {
        "prepared": True,
        "performed_side_effects": False,
        "scheduled": False,
        "dispatched": False,
        "persisted": False,
        "replayed": False,
        "audited": False,
        "journaled": False,
    }
    assert "scheduler_admission" in executor["denied_capabilities"]
    assert "dispatcher_command" in executor["denied_capabilities"]
    assert "persistence_write" in executor["denied_capabilities"]


def test_package_sequence_includes_package_154_and_next_recommendation():
    entry = _package_154_entry()
    assert "## Package 154" in entry
    assert "Recovery Runtime End-to-End Contract Validation" in entry
    assert "tests/test_runtime_recovery_end_to_end_contract.py" in entry
    assert "python -m pytest tests/test_runtime_recovery_end_to_end_contract.py -q" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 155" in entry
