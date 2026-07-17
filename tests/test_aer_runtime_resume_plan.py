import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_resume_plan as resume_module
from core.runtime.aer_runtime_resume_plan import (
    ELIGIBILITY_CONTRACT,
    EXECUTION_BOUNDARY_CONTRACT,
    PLAN_CONTRACT,
    build_resume_plan,
    check_resume_eligibility,
    resume_eligibility_to_summary,
    resume_plan_to_summary,
    validate_resume_eligibility,
    validate_resume_plan,
)
from core.runtime.aer_runtime_snapshot import build_snapshot_from_resume_summary
from core.runtime.aer_runtime_snapshot_consumer import consume_snapshot


RESUME_MODULE = Path("core/runtime/aer_runtime_resume_plan.py")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence_package128.md")


def _resume_summary(**overrides):
    summary = {
        "contract": "aer.runtime.resume_summary.v1",
        "valid": True,
        "outcome": "continue",
        "status": "valid",
        "reason": None,
    }
    summary.update(overrides)
    return summary


def _consumer_result(**overrides):
    snapshot = build_snapshot_from_resume_summary(_resume_summary())
    result = consume_snapshot(snapshot)
    result.update(overrides)
    return result


def test_runtime_resume_plan_module_exists_and_public_api_is_separate():
    assert RESUME_MODULE.exists()

    assert resume_module.__all__ == [
        "ELIGIBILITY_CONTRACT",
        "PLAN_CONTRACT",
        "EXECUTION_BOUNDARY_CONTRACT",
        "check_resume_eligibility",
        "validate_resume_eligibility",
        "build_resume_plan",
        "validate_resume_plan",
        "resume_eligibility_to_summary",
        "resume_plan_to_summary",
    ]

    public_functions = {
        name
        for name, value in inspect.getmembers(resume_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {
        "check_resume_eligibility",
        "validate_resume_eligibility",
        "build_resume_plan",
        "validate_resume_plan",
        "resume_eligibility_to_summary",
        "resume_plan_to_summary",
    }


def test_eligible_consumer_result_builds_descriptive_eligibility():
    result = _consumer_result()

    eligibility = check_resume_eligibility(result)

    assert eligibility == {
        "contract": ELIGIBILITY_CONTRACT,
        "eligible": True,
        "blocked": False,
        "status": "eligible",
        "reason": None,
        "snapshot_id": result["snapshot_id"],
        "lineage": result["lineage"],
        "consumer_status": "accepted",
        "validation": result["validation"],
        "descriptive_only": True,
    }
    assert validate_resume_eligibility(eligibility)["valid"] is True


def test_eligibility_blocks_invalid_consumer_contract():
    eligibility = check_resume_eligibility({"contract": "not.consumer"})

    assert eligibility["eligible"] is False
    assert eligibility["blocked"] is True
    assert eligibility["status"] == "invalid_consumer_result"
    assert validate_resume_eligibility(eligibility)["valid"] is True


def test_eligibility_blocks_invalid_snapshot_reported_by_consumer():
    result = _consumer_result()
    result["accepted"] = False
    result["rejected"] = True
    result["status"] = "rejected"
    result["reason"] = "Identity Error"
    result["validation"] = {"valid": False, "reason": "Identity Error"}

    eligibility = check_resume_eligibility(result)

    assert eligibility["eligible"] is False
    assert eligibility["status"] == "invalid_snapshot"
    assert eligibility["reason"] == "Identity Error"


def test_eligibility_blocks_missing_identity_and_lineage_mismatch():
    missing_identity = check_resume_eligibility(_consumer_result(snapshot_id=None))
    lineage_mismatch = check_resume_eligibility(_consumer_result(lineage={}))

    assert missing_identity["status"] == "missing_identity"
    assert missing_identity["eligible"] is False
    assert lineage_mismatch["status"] == "lineage_mismatch"
    assert lineage_mismatch["eligible"] is False


def test_eligibility_blocks_unsupported_and_recovery_required_states():
    unsupported = check_resume_eligibility(_consumer_result(status="paused"))
    recovery_required = check_resume_eligibility(
        _consumer_result(
            lineage={
                "source_valid": True,
                "source_outcome": "recovery_required",
                "source_status": "valid",
            }
        )
    )

    assert unsupported["status"] == "unsupported_status"
    assert recovery_required["status"] == "recovery_required"


def test_resume_plan_is_built_from_eligible_consumer_result():
    result = _consumer_result()
    eligibility = check_resume_eligibility(result)

    plan = build_resume_plan(eligibility, result)

    assert plan["contract"] == PLAN_CONTRACT
    assert plan["resume_token"].startswith("resume-plan-v1-")
    assert plan["eligible"] is True
    assert plan["status"] == "planned"
    assert plan["reason"] is None
    assert plan["snapshot_id"] == result["snapshot_id"]
    assert plan["lineage"] == result["lineage"]
    assert plan["consumer_status"] == "accepted"
    assert plan["plan_steps"] == ["verify_identity", "prepare_resume_handoff"]
    assert plan["metadata"] == {}
    assert plan["descriptive_only"] is True
    assert plan["execution_boundary"] == {
        "contract": EXECUTION_BOUNDARY_CONTRACT,
        "execution_allowed": False,
        "future_domain_only": True,
        "reason": "runtime resume execution is outside Package 127",
    }
    assert validate_resume_plan(plan)["valid"] is True


def test_blocked_planning_remains_descriptive_and_does_not_execute():
    result = _consumer_result(snapshot_id=None)
    eligibility = check_resume_eligibility(result)

    plan = build_resume_plan(eligibility, result)

    assert plan["eligible"] is False
    assert plan["status"] == "missing_identity"
    assert plan["reason"] == "missing snapshot identity"
    assert plan["blocked_reason"] == "missing snapshot identity"
    assert plan["plan_steps"] == ["record_blocked_resume"]
    assert plan["execution_boundary"]["execution_allowed"] is False
    assert validate_resume_plan(plan)["valid"] is True


def test_schema_version_fields_are_enforced_by_validators():
    result = _consumer_result()
    eligibility = check_resume_eligibility(result)
    plan = build_resume_plan(eligibility, result)

    bad_eligibility = dict(eligibility, contract="aer.runtime.resume.eligibility.v2")
    bad_plan = dict(plan, contract="aer.runtime.resume.plan.v2")

    assert validate_resume_eligibility(bad_eligibility) == {
        "valid": False,
        "category": "Compatibility Error",
        "reason": "invalid eligibility contract",
        "auto_repair_allowed": False,
        "descriptive_only": True,
    }
    assert validate_resume_plan(bad_plan)["category"] == "Compatibility Error"


def test_resume_plan_output_is_deterministic_for_equivalent_inputs():
    result = _consumer_result()
    eligibility = check_resume_eligibility(result)

    assert check_resume_eligibility(result) == check_resume_eligibility(copy.deepcopy(result))
    assert build_resume_plan(eligibility, result) == build_resume_plan(
        copy.deepcopy(eligibility), copy.deepcopy(result)
    )


def test_resume_plan_does_not_mutate_inputs():
    result = _consumer_result()
    eligibility = check_resume_eligibility(result)
    before_result = copy.deepcopy(result)
    before_eligibility = copy.deepcopy(eligibility)

    build_resume_plan(eligibility, result)

    assert result == before_result
    assert eligibility == before_eligibility


def test_eligibility_and_plan_summaries_are_stable_projections():
    result = _consumer_result()
    eligibility = check_resume_eligibility(result)
    plan = build_resume_plan(eligibility, result)

    assert resume_eligibility_to_summary(eligibility) == {
        "contract": ELIGIBILITY_CONTRACT,
        "eligible": True,
        "blocked": False,
        "status": "eligible",
        "reason": None,
        "snapshot_id": result["snapshot_id"],
        "lineage": result["lineage"],
    }
    assert resume_plan_to_summary(plan) == {
        "contract": PLAN_CONTRACT,
        "resume_token": plan["resume_token"],
        "eligible": True,
        "status": "planned",
        "reason": None,
        "snapshot_id": result["snapshot_id"],
        "lineage": result["lineage"],
        "consumer_status": "accepted",
        "execution_boundary": plan["execution_boundary"],
    }


def test_forbidden_imports_and_execution_tokens_are_absent():
    text = RESUME_MODULE.read_text(encoding="utf-8")

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
        "import recovery",
        "from core.runtime.aer_runtime_scheduler",
        "from core.runtime.aer_runtime_dispatcher",
        "from core.runtime.aer_runtime_operator",
        "from core.runtime.aer_runtime_recovery",
        "consume_snapshot",
        "build_snapshot",
        "validate_snapshot",
        "resume(",
        "execute_resume(",
        "recover(",
        "schedule(",
        "dispatch(",
        "operate(",
        "Popen",
        "run(",
        "open(",
        "write(",
    ):
        assert token not in text


def test_execution_boundary_is_data_only_not_behavior():
    assert not hasattr(resume_module, "resume")
    assert not hasattr(resume_module, "execute_resume")

    result = _consumer_result()
    plan = build_resume_plan(check_resume_eligibility(result), result)

    assert plan["execution_boundary"]["contract"] == EXECUTION_BOUNDARY_CONTRACT
    assert plan["execution_boundary"]["execution_allowed"] is False
    assert plan["execution_boundary"]["future_domain_only"] is True


def test_package_sequence_contains_package_127_entry():
    assert PACKAGE_SEQUENCE.exists()

    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")

    for token in (
        "Package 127: Runtime Resume Plan Implementation",
        "core/runtime/aer_runtime_resume_plan.py",
        "tests/test_aer_runtime_resume_plan.py",
        "Eligibility and Planning only",
        "does not implement Runtime Resume Execution",
        "does not connect to Recovery, Scheduler, Dispatcher, Operator, Persistence, Audit, or Journal",
        "Package 128: Runtime Resume Consumer Contract",
        "Final decision: GO",
    ):
        assert token in text
