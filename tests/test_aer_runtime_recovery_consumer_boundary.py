import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_recovery_consumer_boundary as boundary_module
from core.runtime.aer_runtime_recovery_consumer_boundary import (
    ALLOWED_RECOVERY_PLAN_CONSUMERS,
    RECOVERY_CONSUMER_ALLOWED_BOUNDARY,
    RECOVERY_CONSUMER_BOUNDARY_CONTRACT,
    RECOVERY_CONSUMER_DENIED_CAPABILITIES,
    describe_recovery_plan_consumption,
)
from core.runtime.aer_runtime_recovery_planner import build_recovery_plan
from core.runtime.aer_runtime_recovery_validation import RECOVERY_ELIGIBILITY_CONTRACT


MODULE = Path("core/runtime/aer_runtime_recovery_consumer_boundary.py")
VALIDATION_MODULE = Path("core/runtime/aer_runtime_recovery_validation.py")
PLANNER_MODULE = Path("core/runtime/aer_runtime_recovery_planner.py")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _eligibility(**overrides):
    payload = {
        "contract": RECOVERY_ELIGIBILITY_CONTRACT,
        "eligible": True,
        "blocked": False,
        "status": "eligible",
        "reason": None,
        "execution_summary": {
            "status": "failed",
            "source": "resume_execution_consumer",
            "request_id": "execution-request-001",
        },
        "failure_classification": "scheduler_required",
        "recovery_authorized": True,
        "descriptive_only": True,
    }
    payload.update(overrides)
    return payload


def _valid_plan(**overrides):
    payload = build_recovery_plan(_eligibility())
    payload.update(overrides)
    return payload


def _package_142_entry():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 142")
    end = text.find("## Package 143", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_consumer_boundary_module_exists_and_public_api_is_fixed():
    assert MODULE.exists()
    assert boundary_module.__all__ == [
        "RECOVERY_CONSUMER_BOUNDARY_CONTRACT",
        "ALLOWED_RECOVERY_PLAN_CONSUMERS",
        "RECOVERY_CONSUMER_ALLOWED_BOUNDARY",
        "RECOVERY_CONSUMER_DENIED_CAPABILITIES",
        "describe_recovery_plan_consumption",
    ]

    public_functions = {
        name
        for name, value in inspect.getmembers(boundary_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {"describe_recovery_plan_consumption"}


def test_boundary_consumes_validation_and_not_planner_or_downstream_domains():
    text = MODULE.read_text(encoding="utf-8")
    assert "aer_runtime_recovery_validation" in text
    assert VALIDATION_MODULE.exists()
    assert PLANNER_MODULE.exists()
    for token in (
        "aer_runtime_recovery_planner",
        "aer_runtime_resume_execution_builder",
        "runtime_recovery_executor",
        "runtime_recovery_orchestrator",
        "runtime_recovery_pipeline",
        "runtime_recovery_scheduler",
    ):
        assert token not in text


def test_valid_plan_is_accepted_for_allowed_consumer():
    report = describe_recovery_plan_consumption(
        _valid_plan(),
        consumer_type="runtime_recovery_consumer_boundary",
    )

    assert report == {
        "contract": RECOVERY_CONSUMER_BOUNDARY_CONTRACT,
        "accepted": True,
        "rejected": False,
        "consumer_type": "runtime_recovery_consumer_boundary",
        "allowed_boundary": RECOVERY_CONSUMER_ALLOWED_BOUNDARY,
        "denied_capabilities": list(RECOVERY_CONSUMER_DENIED_CAPABILITIES),
        "reason": None,
        "plan_valid": True,
        "descriptive_only": True,
    }


def test_invalid_plan_is_rejected_with_reason():
    plan = _valid_plan(recovery_token="")

    report = describe_recovery_plan_consumption(
        plan,
        consumer_type="runtime_recovery_consumer_boundary",
    )

    assert report["accepted"] is False
    assert report["rejected"] is True
    assert report["allowed_boundary"] is None
    assert report["reason"] == "invalid recovery token"
    assert report["plan_valid"] is False
    assert report["denied_capabilities"] == list(RECOVERY_CONSUMER_DENIED_CAPABILITIES)


def test_unknown_consumer_is_rejected_or_denied():
    report = describe_recovery_plan_consumption(
        _valid_plan(),
        consumer_type="future_scheduler",
    )

    assert report["accepted"] is False
    assert report["rejected"] is True
    assert report["consumer_type"] == "future_scheduler"
    assert report["allowed_boundary"] is None
    assert report["reason"] == "unknown recovery plan consumer"
    assert report["plan_valid"] is True
    assert "scheduler_admission" in report["denied_capabilities"]


def test_allowed_consumer_vocabulary_is_boundary_only():
    assert ALLOWED_RECOVERY_PLAN_CONSUMERS == {
        "runtime_recovery_consumer_boundary",
        "runtime_recovery_closure_review",
        "runtime_recovery_integration_blueprint",
    }
    assert RECOVERY_CONSUMER_ALLOWED_BOUNDARY == "descriptive_recovery_plan_only"
    assert RECOVERY_CONSUMER_DENIED_CAPABILITIES == (
        "recovery_execution",
        "scheduler_admission",
        "dispatcher_command",
        "operator_action",
        "persistence_write",
        "audit_emission",
        "journal_event",
        "replay_action",
        "runtime_mutation",
        "file_mutation",
        "external_process_call",
    )


def test_boundary_output_is_deterministic_and_does_not_mutate_input():
    plan = _valid_plan()
    before = copy.deepcopy(plan)

    first = describe_recovery_plan_consumption(
        plan,
        consumer_type="runtime_recovery_consumer_boundary",
    )
    second = describe_recovery_plan_consumption(
        copy.deepcopy(plan),
        consumer_type="runtime_recovery_consumer_boundary",
    )

    assert first == second
    assert plan == before


def test_boundary_output_is_independent_plain_dict_data():
    plan = _valid_plan()
    report = describe_recovery_plan_consumption(
        plan,
        consumer_type="runtime_recovery_consumer_boundary",
    )

    plan["recovery_token"] = "mutated"

    assert type(report) is dict
    assert type(report["denied_capabilities"]) is list
    assert report["accepted"] is True


def test_no_execution_behavior_or_surfaces_exist():
    assert not hasattr(boundary_module, "recover")
    assert not hasattr(boundary_module, "execute_recovery")
    assert not hasattr(boundary_module, "schedule")
    assert not hasattr(boundary_module, "dispatch")
    assert not hasattr(boundary_module, "persist")
    assert not hasattr(boundary_module, "audit")
    assert not hasattr(boundary_module, "journal")
    assert not hasattr(boundary_module, "replay")


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


def test_package_sequence_includes_package_142_and_next_recommendation():
    entry = _package_142_entry()
    assert "## Package 142" in entry
    assert "Package 142: Runtime Recovery Consumer Boundary" in entry
    assert "consumer-boundary-only" in entry
    assert "pure consumer-boundary layer" in entry
    assert "does not execute recovery" in entry
    assert "no runtime behavior changes" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 143: Runtime Recovery Closure Review" in entry
