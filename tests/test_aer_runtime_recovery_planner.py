import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_recovery_planner as planner_module
from core.runtime.aer_runtime_recovery_planner import build_recovery_plan
from core.runtime.aer_runtime_recovery_validation import (
    RECOVERY_ELIGIBILITY_CONTRACT,
    RECOVERY_EXECUTION_BOUNDARY_CONTRACT,
    RECOVERY_PLAN_CONTRACT,
    validate_recovery_plan,
)


MODULE = Path("core/runtime/aer_runtime_recovery_planner.py")
VALIDATION_MODULE = Path("core/runtime/aer_runtime_recovery_validation.py")
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


def _package_141_entry():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 141")
    end = text.find("## Package 142", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_recovery_planner_module_exists_and_public_api_is_fixed():
    assert MODULE.exists()
    assert planner_module.__all__ == [
        "build_recovery_plan",
    ]

    public_functions = {
        name
        for name, value in inspect.getmembers(planner_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {"build_recovery_plan"}


def test_builder_consumes_package_140_validation_only():
    text = MODULE.read_text(encoding="utf-8")
    assert "aer_runtime_recovery_validation" in text
    assert VALIDATION_MODULE.exists()
    for token in (
        "aer_runtime_resume_execution_builder",
        "aer_runtime_resume_plan",
        "runtime_recovery_executor",
        "runtime_recovery_orchestrator",
        "runtime_recovery_pipeline",
        "runtime_recovery_scheduler",
    ):
        assert token not in text


def test_valid_plan_creation_from_valid_eligibility():
    source = _eligibility()
    plan = build_recovery_plan(source)

    assert plan["contract"] == RECOVERY_PLAN_CONTRACT
    assert plan["recovery_token"].startswith("recovery-plan-v1-")
    assert plan["eligible"] is True
    assert plan["status"] == "planned"
    assert plan["reason"] is None
    assert plan["execution_summary"] == source["execution_summary"]
    assert plan["failure_classification"] == "scheduler_required"
    assert plan["plan_steps"] == ["describe recovery planning for scheduler_required"]
    assert plan["execution_boundary"] == {
        "contract": RECOVERY_EXECUTION_BOUNDARY_CONTRACT,
        "execution_allowed": False,
        "future_domain_only": True,
        "downstream_authorized": False,
        "reason": "recovery plan remains descriptive and future-domain only",
    }
    assert plan["metadata"] == {}
    assert plan["descriptive_only"] is True
    assert validate_recovery_plan(plan)["valid"] is True


def test_invalid_eligibility_input_is_rejected_as_descriptive_plan():
    invalid = _eligibility(contract="wrong")

    plan = build_recovery_plan(invalid)

    assert plan["contract"] == RECOVERY_PLAN_CONTRACT
    assert plan["eligible"] is False
    assert plan["status"] == "invalid_recovery_request"
    assert plan["reason"] == "invalid recovery eligibility contract"
    assert plan["execution_summary"] == {}
    assert plan["failure_classification"] == "invalid_recovery_request"
    assert plan["plan_steps"] == ["describe invalid recovery eligibility"]
    assert plan["execution_boundary"]["execution_allowed"] is False
    assert plan["execution_boundary"]["future_domain_only"] is True
    assert plan["execution_boundary"]["downstream_authorized"] is False
    assert validate_recovery_plan(plan)["valid"] is True


def test_blocked_and_unauthorized_eligibility_never_authorize_execution():
    blocked = build_recovery_plan(_eligibility(eligible=False, blocked=True, status="blocked"))
    unauthorized = build_recovery_plan(_eligibility(recovery_authorized=False))

    assert blocked["status"] == "blocked"
    assert blocked["reason"] == "recovery eligibility is blocked"
    assert blocked["execution_boundary"]["execution_allowed"] is False
    assert blocked["execution_boundary"]["downstream_authorized"] is False
    assert validate_recovery_plan(blocked)["valid"] is True

    assert unauthorized["status"] == "recovery_not_authorized"
    assert unauthorized["reason"] == "recovery is not authorized"
    assert unauthorized["execution_boundary"]["execution_allowed"] is False
    assert unauthorized["execution_boundary"]["downstream_authorized"] is False
    assert validate_recovery_plan(unauthorized)["valid"] is True


def test_explicit_token_and_metadata_are_plain_data_only():
    plan = build_recovery_plan(
        _eligibility(),
        recovery_token=" recovery-token-explicit ",
        metadata={"source": {"package": 141}, "tags": ("planner", "builder")},
    )

    assert plan["recovery_token"] == "recovery-token-explicit"
    assert plan["metadata"] == {"source": {"package": 141}, "tags": ["planner", "builder"]}
    assert validate_recovery_plan(plan)["valid"] is True


def test_builder_output_is_deterministic_and_does_not_mutate_input():
    source = _eligibility()
    before = copy.deepcopy(source)

    first = build_recovery_plan(source)
    second = build_recovery_plan(copy.deepcopy(source))

    assert first == second
    assert source == before


def test_builder_output_is_independent_plain_dict_data():
    source = _eligibility()
    plan = build_recovery_plan(source)

    source["execution_summary"]["status"] = "mutated"

    assert plan["execution_summary"]["status"] == "failed"
    assert type(plan) is dict
    assert type(plan["execution_boundary"]) is dict
    assert type(plan["plan_steps"]) is list


def test_no_execution_behavior_or_surfaces_exist():
    assert not hasattr(planner_module, "recover")
    assert not hasattr(planner_module, "execute_recovery")
    assert not hasattr(planner_module, "schedule")
    assert not hasattr(planner_module, "dispatch")
    assert not hasattr(planner_module, "persist")
    assert not hasattr(planner_module, "audit")
    assert not hasattr(planner_module, "journal")
    assert not hasattr(planner_module, "replay")


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


def test_package_sequence_includes_package_141_and_next_recommendation():
    entry = _package_141_entry()
    assert "## Package 141" in entry
    assert "Package 141: Runtime Recovery Planner / Builder" in entry
    assert "planner/builder-only" in entry
    assert "pure planner/builder layer" in entry
    assert "does not execute recovery" in entry
    assert "no runtime behavior changes" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 142: Runtime Recovery Consumer Boundary" in entry
