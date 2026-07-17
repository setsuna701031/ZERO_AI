import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_recovery_validation as validation_module
from core.runtime.aer_runtime_recovery_validation import (
    ALLOWED_ELIGIBILITY_STATUSES,
    ALLOWED_PLAN_STATUSES,
    ELIGIBILITY_REQUIRED_FIELDS,
    EXECUTION_BOUNDARY_REQUIRED_FIELDS,
    PLAN_REQUIRED_FIELDS,
    RECOVERY_ELIGIBILITY_CONTRACT,
    RECOVERY_EXECUTION_BOUNDARY_CONTRACT,
    RECOVERY_PLAN_CONTRACT,
    validate_recovery_eligibility,
    validate_recovery_execution_boundary,
    validate_recovery_plan,
)


MODULE = Path("core/runtime/aer_runtime_recovery_validation.py")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _execution_boundary(**overrides):
    payload = {
        "contract": RECOVERY_EXECUTION_BOUNDARY_CONTRACT,
        "execution_allowed": False,
        "future_domain_only": True,
        "downstream_authorized": False,
        "reason": "recovery validation cannot authorize execution",
    }
    payload.update(overrides)
    return payload


def _eligibility(**overrides):
    payload = {
        "contract": RECOVERY_ELIGIBILITY_CONTRACT,
        "eligible": True,
        "blocked": False,
        "status": "eligible",
        "reason": None,
        "execution_summary": {"status": "failed", "source": "resume_execution_consumer"},
        "failure_classification": "scheduler_required",
        "recovery_authorized": False,
        "descriptive_only": True,
    }
    payload.update(overrides)
    return payload


def _plan(**overrides):
    payload = {
        "contract": RECOVERY_PLAN_CONTRACT,
        "recovery_token": "recovery-token-001",
        "eligible": True,
        "status": "planned",
        "reason": None,
        "execution_summary": {"status": "failed", "source": "resume_execution_consumer"},
        "failure_classification": "scheduler_required",
        "plan_steps": ["describe scheduler handoff requirement"],
        "execution_boundary": _execution_boundary(),
        "metadata": {},
        "descriptive_only": True,
    }
    payload.update(overrides)
    return payload


def _package_140_entry():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    start = text.index("## Package 140")
    end = text.find("## Package 141", start + 1)
    if end == -1:
        return text[start:]
    return text[start:end]


def test_validation_module_exists_and_public_api_is_fixed():
    assert MODULE.exists()
    assert validation_module.__all__ == [
        "RECOVERY_ELIGIBILITY_CONTRACT",
        "RECOVERY_PLAN_CONTRACT",
        "RECOVERY_EXECUTION_BOUNDARY_CONTRACT",
        "ELIGIBILITY_REQUIRED_FIELDS",
        "PLAN_REQUIRED_FIELDS",
        "EXECUTION_BOUNDARY_REQUIRED_FIELDS",
        "ALLOWED_ELIGIBILITY_STATUSES",
        "ALLOWED_PLAN_STATUSES",
        "validate_recovery_eligibility",
        "validate_recovery_plan",
        "validate_recovery_execution_boundary",
    ]

    public_functions = {
        name
        for name, value in inspect.getmembers(validation_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {
        "validate_recovery_eligibility",
        "validate_recovery_plan",
        "validate_recovery_execution_boundary",
    }


def test_validation_constants_match_contracts_fields_and_statuses():
    assert RECOVERY_ELIGIBILITY_CONTRACT == "aer.runtime.recovery.eligibility.v1"
    assert RECOVERY_PLAN_CONTRACT == "aer.runtime.recovery.plan.v1"
    assert RECOVERY_EXECUTION_BOUNDARY_CONTRACT == "aer.runtime.recovery.execution_boundary.v1"
    assert ELIGIBILITY_REQUIRED_FIELDS == set(_eligibility())
    assert PLAN_REQUIRED_FIELDS == set(_plan())
    assert EXECUTION_BOUNDARY_REQUIRED_FIELDS == set(_execution_boundary())
    assert ALLOWED_ELIGIBILITY_STATUSES == {
        "eligible",
        "blocked",
        "invalid_execution_summary",
        "invalid_recovery_request",
        "recovery_not_authorized",
        "scheduler_required",
        "operator_required",
        "persistence_required",
        "audit_required",
        "journal_required",
    }
    assert ALLOWED_PLAN_STATUSES == {
        "planned",
        "blocked",
        "invalid_execution_summary",
        "invalid_recovery_request",
        "recovery_not_authorized",
        "scheduler_required",
        "operator_required",
        "persistence_required",
        "audit_required",
        "journal_required",
    }


def test_valid_eligibility_passes():
    assert validate_recovery_eligibility(_eligibility()) == {
        "valid": True,
        "category": None,
        "reason": None,
        "auto_repair_allowed": False,
        "descriptive_only": True,
    }


def test_missing_fields_fail():
    eligibility = _eligibility()
    eligibility.pop("execution_summary")
    plan = _plan()
    plan.pop("metadata")
    boundary = _execution_boundary()
    boundary.pop("reason")

    assert validate_recovery_eligibility(eligibility)["reason"] == "missing recovery eligibility fields"
    assert validate_recovery_plan(plan)["reason"] == "missing recovery plan fields"
    assert validate_recovery_execution_boundary(boundary)["reason"] == (
        "missing recovery execution boundary fields"
    )


def test_unknown_fields_fail():
    assert validate_recovery_eligibility(dict(_eligibility(), scheduler_queue=[]))["reason"] == (
        "unknown recovery eligibility fields"
    )
    assert validate_recovery_plan(dict(_plan(), dispatcher_call={}))["reason"] == (
        "unknown recovery plan fields"
    )
    assert validate_recovery_execution_boundary(dict(_execution_boundary(), audit_record={}))["reason"] == (
        "unknown recovery execution boundary fields"
    )


def test_invalid_contract_fails():
    assert validate_recovery_eligibility(_eligibility(contract="wrong"))["reason"] == (
        "invalid recovery eligibility contract"
    )
    assert validate_recovery_plan(_plan(contract="wrong"))["reason"] == "invalid recovery plan contract"
    assert validate_recovery_execution_boundary(_execution_boundary(contract="wrong"))["reason"] == (
        "invalid recovery execution boundary contract"
    )


def test_conflicting_eligible_blocked_fails():
    assert validate_recovery_eligibility(_eligibility(eligible=True, blocked=True)) == {
        "valid": False,
        "category": "Status Error",
        "reason": "eligible and blocked conflict",
        "auto_repair_allowed": False,
        "descriptive_only": True,
    }


def test_invalid_status_fails():
    assert validate_recovery_eligibility(_eligibility(status="running"))["reason"] == (
        "invalid recovery eligibility status"
    )
    assert validate_recovery_plan(_plan(status="running"))["reason"] == "invalid recovery plan status"


def test_invalid_execution_summary_fails():
    assert validate_recovery_eligibility(_eligibility(execution_summary=[]))["reason"] == (
        "invalid execution summary"
    )
    assert validate_recovery_plan(_plan(execution_summary=[]))["reason"] == "invalid execution summary"


def test_invalid_recovery_authorized_fails():
    assert validate_recovery_eligibility(_eligibility(recovery_authorized="yes"))["reason"] == (
        "invalid recovery authorization flag"
    )


def test_valid_plan_passes():
    assert validate_recovery_plan(_plan())["valid"] is True


def test_invalid_recovery_token_fails():
    assert validate_recovery_plan(_plan(recovery_token=""))["reason"] == "invalid recovery token"
    assert validate_recovery_plan(_plan(recovery_token=None))["category"] == "Identity Error"


def test_invalid_plan_steps_fail():
    assert validate_recovery_plan(_plan(plan_steps="describe"))["reason"] == "invalid plan steps"
    assert validate_recovery_plan(_plan(plan_steps=[]))["reason"] == "invalid plan steps"
    assert validate_recovery_plan(_plan(plan_steps=[""]))["reason"] == "invalid plan steps"


def test_invalid_execution_boundary_fails():
    assert validate_recovery_plan(_plan(execution_boundary={"contract": "wrong"}))["reason"] == (
        "invalid recovery execution boundary"
    )


def test_valid_execution_boundary_passes():
    assert validate_recovery_execution_boundary(_execution_boundary()) == {
        "valid": True,
        "category": None,
        "reason": None,
        "auto_repair_allowed": False,
        "descriptive_only": True,
    }


def test_execution_boundary_cannot_allow_execution_or_downstream():
    assert validate_recovery_execution_boundary(_execution_boundary(execution_allowed=True))["reason"] == (
        "recovery execution boundary cannot allow execution"
    )
    assert validate_recovery_execution_boundary(_execution_boundary(future_domain_only=False))["reason"] == (
        "recovery execution boundary must remain future-domain only"
    )
    assert validate_recovery_execution_boundary(_execution_boundary(downstream_authorized=True))["reason"] == (
        "recovery execution boundary cannot authorize downstream"
    )


def test_validation_reports_are_stable_and_inputs_are_not_mutated():
    eligibility = _eligibility()
    plan = _plan()
    boundary = _execution_boundary()
    before = (copy.deepcopy(eligibility), copy.deepcopy(plan), copy.deepcopy(boundary))

    validate_recovery_eligibility(eligibility)
    validate_recovery_plan(plan)
    validate_recovery_execution_boundary(boundary)

    assert (eligibility, plan, boundary) == before
    assert set(validate_recovery_plan(_plan())) == {
        "valid",
        "category",
        "reason",
        "auto_repair_allowed",
        "descriptive_only",
    }
    assert validate_recovery_plan(_plan()) == validate_recovery_plan(_plan())


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
        "from core.runtime.aer_runtime_recovery",
        "from core.runtime.runtime_recovery",
        "recover(",
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


def test_package_sequence_includes_package_140_and_141_next_package():
    entry = _package_140_entry()
    assert "## Package 140" in entry
    assert "Package 140: Runtime Recovery Validation" in entry
    assert "implements Runtime Recovery Validation" in entry
    assert "pure validation only" in entry
    assert "no recovery execution" in entry
    assert "no runtime behavior changes" in entry
    assert "Final decision: GO" in entry
    assert "Next package: Package 141: Runtime Recovery Planner / Builder" in entry


def test_no_recovery_execution_surface_exists_in_validation_module():
    assert not hasattr(validation_module, "recover")
    assert not hasattr(validation_module, "schedule")
    assert not hasattr(validation_module, "dispatch")
    assert not hasattr(validation_module, "operate")
    assert not hasattr(validation_module, "persist")
    assert not hasattr(validation_module, "audit")
    assert not hasattr(validation_module, "journal")
    assert not hasattr(validation_module, "replay")
