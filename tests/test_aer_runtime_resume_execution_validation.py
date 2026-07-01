import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_resume_execution_validation as validation_module
from core.runtime.aer_runtime_resume_execution_validation import (
    ALLOWED_FAILURE_CATEGORIES,
    ALLOWED_FAILURE_CODES,
    ALLOWED_FAILURE_OWNERS,
    ALLOWED_HANDOFF_TYPES,
    ALLOWED_REQUESTED_ACTIONS,
    ALLOWED_RESULT_STATUSES,
    EXECUTION_FAILURE_CONTRACT,
    EXECUTION_REQUEST_CONTRACT,
    EXECUTION_RESULT_CONTRACT,
    FAILURE_REQUIRED_FIELDS,
    REQUEST_REQUIRED_FIELDS,
    RESUME_CONSUMER_OUTPUT_CONTRACT,
    RESULT_REQUIRED_FIELDS,
    execution_failure_to_summary,
    execution_request_to_summary,
    execution_result_to_summary,
    validate_execution_failure,
    validate_execution_request,
    validate_execution_result,
)

MODULE = Path("core/runtime/aer_runtime_resume_execution_validation.py")
CONTRACT = Path("docs/contracts/runtime/resume_execution_v1.md")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _request(**overrides):
    payload = {
        "contract": EXECUTION_REQUEST_CONTRACT,
        "execution_request_id": "execution-request-001",
        "resume_token": "resume-plan-v1-token",
        "snapshot_id": "snapshot-001",
        "lineage": {"source_valid": True, "source_outcome": "continue"},
        "source_contract": RESUME_CONSUMER_OUTPUT_CONTRACT,
        "source_status": "accepted_for_future_domain",
        "source_reason": None,
        "execution_allowed": False,
        "requested_action": "validate_only",
        "preconditions": {"consumer_output_valid": True},
        "failure_policy": {"on_failure": "describe_only"},
        "metadata": {},
        "descriptive_only": True,
    }
    payload.update(overrides)
    return payload


def _failure(**overrides):
    payload = {
        "contract": EXECUTION_FAILURE_CONTRACT,
        "failure_code": "execution_not_authorized",
        "category": "Execution Boundary Error",
        "owner": "Runtime Resume Execution",
        "reason": "execution remains validation-only",
        "recoverable": False,
        "downstream_owner": None,
        "metadata": {},
        "descriptive_only": True,
    }
    payload.update(overrides)
    return payload


def _result(**overrides):
    payload = {
        "contract": EXECUTION_RESULT_CONTRACT,
        "execution_request_id": "execution-request-001",
        "resume_token": "resume-plan-v1-token",
        "snapshot_id": "snapshot-001",
        "lineage": {"source_valid": True, "source_outcome": "continue"},
        "status": "validated",
        "reason": None,
        "completed": False,
        "failed": False,
        "failure": None,
        "downstream_handoff_required": False,
        "downstream_handoff_type": None,
        "metadata": {},
        "descriptive_only": True,
    }
    payload.update(overrides)
    return payload


def test_resume_execution_validation_module_exists_and_public_api_is_separate():
    assert MODULE.exists()
    assert validation_module.__all__ == [
        "EXECUTION_REQUEST_CONTRACT",
        "EXECUTION_RESULT_CONTRACT",
        "EXECUTION_FAILURE_CONTRACT",
        "RESUME_CONSUMER_OUTPUT_CONTRACT",
        "REQUEST_REQUIRED_FIELDS",
        "RESULT_REQUIRED_FIELDS",
        "FAILURE_REQUIRED_FIELDS",
        "ALLOWED_REQUESTED_ACTIONS",
        "ALLOWED_RESULT_STATUSES",
        "ALLOWED_HANDOFF_TYPES",
        "ALLOWED_FAILURE_CODES",
        "ALLOWED_FAILURE_CATEGORIES",
        "ALLOWED_FAILURE_OWNERS",
        "validate_execution_request",
        "validate_execution_result",
        "validate_execution_failure",
        "execution_request_to_summary",
        "execution_result_to_summary",
        "execution_failure_to_summary",
    ]

    public_functions = {
        name
        for name, value in inspect.getmembers(validation_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {
        "validate_execution_request",
        "validate_execution_result",
        "validate_execution_failure",
        "execution_request_to_summary",
        "execution_result_to_summary",
        "execution_failure_to_summary",
    }


def test_contract_document_remains_authoritative_for_validation_package():
    text = CONTRACT.read_text(encoding="utf-8")
    for token in (
        "Ready for Package 132: Runtime Resume Execution Validation",
        "validate_execution_request(...)" ,
        "validate_execution_result(...)" ,
        "validate_execution_failure(...)" ,
        "Package 132 may implement validation helpers",
    ):
        assert token in text


def test_validation_constants_match_contract_vocabularies():
    assert EXECUTION_REQUEST_CONTRACT == "aer.runtime.resume.execution_request.v1"
    assert EXECUTION_RESULT_CONTRACT == "aer.runtime.resume.execution_result.v1"
    assert EXECUTION_FAILURE_CONTRACT == "aer.runtime.resume.execution_failure.v1"
    assert RESUME_CONSUMER_OUTPUT_CONTRACT == "aer.runtime.resume.consumer_output.v1"
    assert REQUEST_REQUIRED_FIELDS == set(_request())
    assert RESULT_REQUIRED_FIELDS == set(_result())
    assert FAILURE_REQUIRED_FIELDS == set(_failure())
    assert ALLOWED_REQUESTED_ACTIONS == {"resume_runtime", "validate_only", "blocked"}
    assert ALLOWED_RESULT_STATUSES == {
        "not_started",
        "blocked",
        "validated",
        "completed",
        "failed",
        "handoff_required",
    }
    assert ALLOWED_HANDOFF_TYPES == {
        "recovery",
        "scheduler",
        "dispatcher",
        "operator",
        "persistence",
        "audit",
        "journal",
        "replay",
    }
    assert "execution_not_authorized" in ALLOWED_FAILURE_CODES
    assert "Ownership Violation" in ALLOWED_FAILURE_CATEGORIES
    assert "Future Scheduler" in ALLOWED_FAILURE_OWNERS


def test_validate_execution_request_accepts_valid_descriptive_request():
    assert validate_execution_request(_request()) == {
        "valid": True,
        "category": None,
        "reason": None,
        "auto_repair_allowed": False,
        "descriptive_only": True,
    }


def test_validate_execution_request_rejects_schema_missing_unknown_and_types():
    assert validate_execution_request({"contract": "wrong"})["category"] == "Compatibility Error"

    missing = _request()
    missing.pop("resume_token")
    assert validate_execution_request(missing) == {
        "valid": False,
        "category": "Compatibility Error",
        "reason": "missing execution request fields",
        "auto_repair_allowed": False,
        "descriptive_only": True,
    }

    unknown = dict(_request(), scheduler_queue="not allowed")
    assert validate_execution_request(unknown)["reason"] == "unknown execution request fields"
    assert validate_execution_request(_request(execution_request_id=""))["category"] == "Identity Error"
    assert validate_execution_request(_request(resume_token=None))["category"] == "Identity Error"
    assert validate_execution_request(_request(snapshot_id=object()))["category"] == "Identity Error"
    assert validate_execution_request(_request(lineage=[]))["category"] == "Lineage Error"
    assert validate_execution_request(_request(source_status=None))["category"] == "Status Error"
    assert validate_execution_request(_request(source_reason=3))["category"] == "Consumer Boundary Error"
    assert validate_execution_request(_request(requested_action="execute_now"))["category"] == "Status Error"
    assert validate_execution_request(_request(preconditions=[]))["category"] == "Precondition Error"
    assert validate_execution_request(_request(failure_policy=[]))["category"] == "Compatibility Error"
    assert validate_execution_request(_request(metadata=[]))["category"] == "Compatibility Error"


def test_validate_execution_request_rejects_execution_authorization_and_callables():
    assert validate_execution_request(_request(execution_allowed=True)) == {
        "valid": False,
        "category": "Execution Boundary Error",
        "reason": "execution must not be authorized by validation",
        "auto_repair_allowed": False,
        "descriptive_only": True,
    }
    assert validate_execution_request(_request(descriptive_only=False))["reason"] == (
        "execution request must be descriptive only"
    )
    assert validate_execution_request(_request(metadata={"callback": lambda: None}))["reason"] == (
        "execution request contains executable value"
    )


def test_validate_execution_failure_accepts_valid_failure():
    assert validate_execution_failure(_failure())["valid"] is True


def test_validate_execution_failure_rejects_invalid_vocabularies_and_ownership():
    assert validate_execution_failure(_failure(contract="wrong"))["reason"] == (
        "invalid execution failure contract"
    )
    assert validate_execution_failure(_failure(failure_code="bad"))["reason"] == "invalid failure code"
    assert validate_execution_failure(_failure(category="Bad Category"))["reason"] == (
        "invalid failure category"
    )
    assert validate_execution_failure(_failure(owner="Scheduler"))["category"] == "Ownership Violation"
    assert validate_execution_failure(_failure(reason=None))["category"] == "Runtime Execution Error"
    assert validate_execution_failure(_failure(recoverable="no"))["category"] == "Runtime Execution Error"
    assert validate_execution_failure(_failure(downstream_owner="Scheduler"))["category"] == (
        "Ownership Violation"
    )
    assert validate_execution_failure(_failure(metadata=[]))["category"] == "Compatibility Error"
    assert validate_execution_failure(_failure(descriptive_only=False))["category"] == (
        "Execution Boundary Error"
    )
    assert validate_execution_failure(dict(_failure(), extra="field"))["reason"] == (
        "unknown execution failure fields"
    )
    assert validate_execution_failure(_failure(metadata={"handler": lambda: None}))["reason"] == (
        "execution failure contains executable value"
    )


def test_validate_execution_result_accepts_valid_result_and_nested_failure():
    assert validate_execution_result(_result())["valid"] is True
    failed = _result(status="failed", failed=True, failure=_failure())
    assert validate_execution_result(failed)["valid"] is True


def test_validate_execution_result_rejects_invalid_status_flags_and_handoff():
    assert validate_execution_result(_result(contract="wrong"))["category"] == "Compatibility Error"
    assert validate_execution_result(_result(status="running"))["category"] == "Status Error"
    assert validate_execution_result(_result(reason=7))["category"] == "Status Error"
    assert validate_execution_result(_result(completed=True, failed=True))["reason"] == (
        "completion flags conflict"
    )
    assert validate_execution_result(_result(completed="yes"))["reason"] == "invalid completion flags"
    assert validate_execution_result(_result(failure={"contract": "bad"}))["reason"] == (
        "invalid execution failure"
    )
    assert validate_execution_result(_result(downstream_handoff_required="yes"))["category"] == (
        "Future Domain Required"
    )
    assert validate_execution_result(_result(downstream_handoff_type="database"))["reason"] == (
        "invalid downstream handoff type"
    )
    assert validate_execution_result(_result(metadata=[]))["category"] == "Compatibility Error"
    assert validate_execution_result(_result(descriptive_only=False))["category"] == (
        "Execution Boundary Error"
    )
    assert validate_execution_result(dict(_result(), dispatcher_call="forbidden"))["reason"] == (
        "unknown execution result fields"
    )


def test_validation_does_not_mutate_inputs():
    request = _request()
    result = _result(failure=_failure())
    failure = _failure()
    before = (copy.deepcopy(request), copy.deepcopy(result), copy.deepcopy(failure))

    validate_execution_request(request)
    validate_execution_result(result)
    validate_execution_failure(failure)

    assert (request, result, failure) == before


def test_summaries_are_stable_public_projections():
    request = _request()
    result = _result(status="handoff_required", downstream_handoff_required=True, downstream_handoff_type="recovery")
    failure = _failure(failure_code="future_domain_required", category="Future Domain Required")

    assert execution_request_to_summary(request) == {
        "contract": EXECUTION_REQUEST_CONTRACT,
        "valid": True,
        "execution_request_id": "execution-request-001",
        "resume_token": "resume-plan-v1-token",
        "snapshot_id": "snapshot-001",
        "source_contract": RESUME_CONSUMER_OUTPUT_CONTRACT,
        "source_status": "accepted_for_future_domain",
        "execution_allowed": False,
        "requested_action": "validate_only",
    }
    assert execution_result_to_summary(result) == {
        "contract": EXECUTION_RESULT_CONTRACT,
        "valid": True,
        "execution_request_id": "execution-request-001",
        "resume_token": "resume-plan-v1-token",
        "snapshot_id": "snapshot-001",
        "status": "handoff_required",
        "reason": None,
        "completed": False,
        "failed": False,
        "downstream_handoff_required": True,
        "downstream_handoff_type": "recovery",
    }
    assert execution_failure_to_summary(failure) == {
        "contract": EXECUTION_FAILURE_CONTRACT,
        "valid": True,
        "failure_code": "future_domain_required",
        "category": "Future Domain Required",
        "owner": "Runtime Resume Execution",
        "reason": "execution remains validation-only",
        "recoverable": False,
        "downstream_owner": None,
    }


def test_forbidden_imports_calls_and_execution_tokens_are_absent():
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
        "import recovery",
        "import replay",
        "from core.runtime.aer_runtime_scheduler",
        "from core.runtime.aer_runtime_dispatcher",
        "from core.runtime.aer_runtime_operator",
        "from core.runtime.aer_runtime_recovery",
        "from core.runtime.aer_runtime_snapshot",
        "from core.runtime.aer_runtime_resume_plan",
        "consume_snapshot",
        "build_snapshot",
        "validate_snapshot",
        "create_execution_request",
        "create_execution_result",
        "create_execution_failure",
        "resume(",
        "execute_resume(",
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


def test_package_sequence_contains_package_132_entry():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "## Package 132" in text
    assert "Runtime Resume Execution Validation" in text
    assert "Package 132 owns:" in text
    assert "validate_execution_request" in text
    assert "validate_execution_result" in text
    assert "validate_execution_failure" in text
    assert "Package 132 must not:" in text
    assert "Final decision: GO" in text
    assert "Ready for Package 133: Runtime Resume Execution Request Builder" in text


def test_no_execution_surface_exists_in_validation_module():
    assert not hasattr(validation_module, "resume")
    assert not hasattr(validation_module, "execute_resume")
    assert not hasattr(validation_module, "create_execution_request")
    assert not hasattr(validation_module, "create_execution_result")
    assert not hasattr(validation_module, "create_execution_failure")
