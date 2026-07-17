import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_resume_execution_builder as builder_module
from core.runtime.aer_runtime_resume_execution_builder import (
    CONSUMER_BOUNDARY_CONTRACT,
    EXECUTION_BOUNDARY_CONTRACT,
    build_execution_failure,
    build_execution_request,
    build_execution_result,
    execution_failure_to_summary,
    execution_request_to_summary,
    execution_result_to_summary,
)
from core.runtime.aer_runtime_resume_execution_validation import (
    EXECUTION_FAILURE_CONTRACT,
    EXECUTION_REQUEST_CONTRACT,
    EXECUTION_RESULT_CONTRACT,
    RESUME_CONSUMER_OUTPUT_CONTRACT,
    validate_execution_failure,
    validate_execution_request,
    validate_execution_result,
)

MODULE = Path("core/runtime/aer_runtime_resume_execution_builder.py")
VALIDATION_MODULE = Path("core/runtime/aer_runtime_resume_execution_validation.py")
PACKAGE_SEQUENCE = Path("docs/aer_evolution_v2_package_sequence.md")


def _consumer_output(**overrides):
    payload = {
        "contract": RESUME_CONSUMER_OUTPUT_CONTRACT,
        "accepted_for_future_domain": True,
        "blocked": False,
        "status": "accepted_for_future_domain",
        "reason": None,
        "resume_token": "resume-plan-v1-token",
        "snapshot_id": "snapshot-001",
        "lineage": {"source_valid": True, "source_outcome": "continue"},
        "execution_boundary": {
            "contract": EXECUTION_BOUNDARY_CONTRACT,
            "execution_allowed": False,
            "future_domain_only": True,
            "reason": "execution remains future-domain only",
        },
        "consumer_boundary": {
            "contract": CONSUMER_BOUNDARY_CONTRACT,
            "future_domain_only": True,
            "execution_allowed": False,
            "downstream_authorized": False,
            "allowed_future_domains": ["Runtime Resume Execution"],
            "reason": "downstream consumption requires future domain contracts",
        },
        "descriptive_only": True,
    }
    payload.update(overrides)
    return payload


def test_resume_execution_builder_module_exists_and_public_api_is_separate():
    assert MODULE.exists()
    assert builder_module.__all__ == [
        "CONSUMER_BOUNDARY_CONTRACT",
        "EXECUTION_BOUNDARY_CONTRACT",
        "build_execution_request",
        "build_execution_result",
        "build_execution_failure",
        "execution_request_to_summary",
        "execution_result_to_summary",
        "execution_failure_to_summary",
    ]

    public_functions = {
        name
        for name, value in inspect.getmembers(builder_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {
        "build_execution_request",
        "build_execution_result",
        "build_execution_failure",
        "execution_request_to_summary",
        "execution_result_to_summary",
        "execution_failure_to_summary",
    }


def test_builder_consumes_validation_contracts_but_not_downstream_domains():
    text = MODULE.read_text(encoding="utf-8")
    assert "from core.runtime.aer_runtime_resume_execution_validation import" in text
    for token in (
        "import os",
        "import subprocess",
        "from pathlib",
        "import scheduler",
        "import recovery",
        "import dispatcher",
        "import operator",
        "import persistence",
        "import audit",
        "import journal",
        "import replay",
        "consume_snapshot",
        "build_snapshot",
        "validate_snapshot",
    ):
        assert token not in text


def test_build_execution_request_from_accepted_consumer_output_is_valid_and_data_only():
    source = _consumer_output()
    request = build_execution_request(source)

    assert request["contract"] == EXECUTION_REQUEST_CONTRACT
    assert request["execution_request_id"].startswith("resume-execution-request-v1-")
    assert request["resume_token"] == source["resume_token"]
    assert request["snapshot_id"] == source["snapshot_id"]
    assert request["lineage"] == source["lineage"]
    assert request["source_contract"] == RESUME_CONSUMER_OUTPUT_CONTRACT
    assert request["source_status"] == "accepted_for_future_domain"
    assert request["source_reason"] is None
    assert request["execution_allowed"] is False
    assert request["requested_action"] == "validate_only"
    assert request["preconditions"] == {
        "consumer_output_contract_valid": True,
        "accepted_for_future_domain": True,
        "execution_boundary_present": True,
        "execution_boundary_allows_execution": False,
        "consumer_boundary_present": True,
        "downstream_authorized": False,
    }
    assert request["failure_policy"] == {
        "on_failure": "describe_only",
        "auto_repair_allowed": False,
        "downstream_handoff_allowed": False,
    }
    assert request["metadata"] == {}
    assert request["descriptive_only"] is True
    assert validate_execution_request(request)["valid"] is True


def test_build_execution_request_blocks_blocked_consumer_output():
    source = _consumer_output(
        accepted_for_future_domain=False,
        blocked=True,
        status="blocked",
        reason="consumer output blocked",
    )

    request = build_execution_request(source)

    assert request["requested_action"] == "blocked"
    assert request["source_status"] == "blocked"
    assert request["source_reason"] == "consumer output blocked"
    assert request["preconditions"]["accepted_for_future_domain"] is False
    assert validate_execution_request(request)["valid"] is True


def test_build_execution_request_never_authorizes_execution_even_if_source_claims_it():
    source = _consumer_output(
        execution_boundary={
            "contract": EXECUTION_BOUNDARY_CONTRACT,
            "execution_allowed": True,
            "future_domain_only": False,
            "reason": "bad source",
        },
        consumer_boundary={
            "contract": CONSUMER_BOUNDARY_CONTRACT,
            "future_domain_only": False,
            "execution_allowed": True,
            "downstream_authorized": True,
            "allowed_future_domains": ["Runtime Resume Execution"],
            "reason": "bad source",
        },
    )

    request = build_execution_request(source)

    assert request["execution_allowed"] is False
    assert request["preconditions"]["execution_boundary_allows_execution"] is True
    assert request["preconditions"]["downstream_authorized"] is True
    assert request["failure_policy"]["downstream_handoff_allowed"] is False
    assert validate_execution_request(request)["valid"] is True


def test_build_execution_request_is_deterministic_and_does_not_mutate_source():
    source = _consumer_output()
    before = copy.deepcopy(source)

    first = build_execution_request(source)
    second = build_execution_request(copy.deepcopy(source))

    assert first == second
    assert source == before


def test_build_execution_failure_creates_valid_failure_descriptor():
    failure = build_execution_failure(
        failure_code="execution_not_authorized",
        category="Execution Boundary Error",
        owner="Runtime Resume Execution",
        reason="execution remains validation-only",
        recoverable=False,
    )

    assert failure == {
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
    assert validate_execution_failure(failure)["valid"] is True


def test_build_execution_result_from_valid_request_is_validation_only():
    request = build_execution_request(_consumer_output())
    result = build_execution_result(request)

    assert result == {
        "contract": EXECUTION_RESULT_CONTRACT,
        "execution_request_id": request["execution_request_id"],
        "resume_token": request["resume_token"],
        "snapshot_id": request["snapshot_id"],
        "lineage": request["lineage"],
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
    assert validate_execution_result(result)["valid"] is True


def test_build_execution_result_from_invalid_request_creates_descriptive_failure():
    request = build_execution_request(_consumer_output())
    request["resume_token"] = None

    result = build_execution_result(request)

    assert result["status"] == "failed"
    assert result["completed"] is False
    assert result["failed"] is True
    assert result["failure"]["failure_code"] == "invalid_execution_request"
    assert result["failure"]["owner"] == "Runtime Resume Execution"
    assert validate_execution_failure(result["failure"])["valid"] is True
    assert validate_execution_result(result)["valid"] is False


def test_build_execution_result_with_handoff_required_remains_descriptive():
    request = build_execution_request(_consumer_output())
    result = build_execution_result(
        request,
        status="handoff_required",
        downstream_handoff_type="recovery",
    )

    assert result["status"] == "handoff_required"
    assert result["reason"] == "future downstream handoff required"
    assert result["downstream_handoff_required"] is True
    assert result["downstream_handoff_type"] == "recovery"
    assert result["completed"] is False
    assert validate_execution_result(result)["valid"] is True


def test_summary_projections_are_stable_and_consumer_safe():
    request = build_execution_request(_consumer_output())
    failure = build_execution_failure(
        failure_code="execution_not_authorized",
        category="Execution Boundary Error",
        owner="Runtime Resume Execution",
        reason="execution remains validation-only",
    )
    result = build_execution_result(request, failure=failure)

    assert execution_request_to_summary(request) == {
        "contract": EXECUTION_REQUEST_CONTRACT,
        "valid": True,
        "execution_request_id": request["execution_request_id"],
        "resume_token": request["resume_token"],
        "snapshot_id": request["snapshot_id"],
        "source_contract": request["source_contract"],
        "source_status": request["source_status"],
        "execution_allowed": False,
        "requested_action": "validate_only",
    }
    assert execution_failure_to_summary(failure) == {
        "contract": EXECUTION_FAILURE_CONTRACT,
        "valid": True,
        "failure_code": "execution_not_authorized",
        "category": "Execution Boundary Error",
        "owner": "Runtime Resume Execution",
        "reason": "execution remains validation-only",
        "recoverable": False,
        "downstream_owner": None,
    }
    result_summary = execution_result_to_summary(result)
    assert set(result_summary) == {
        "contract",
        "valid",
        "execution_request_id",
        "resume_token",
        "snapshot_id",
        "status",
        "reason",
        "completed",
        "failed",
        "downstream_handoff_required",
        "downstream_handoff_type",
    }


def test_builder_outputs_do_not_mutate_inputs():
    source = _consumer_output()
    request = build_execution_request(source)
    failure = build_execution_failure(
        failure_code="execution_not_authorized",
        category="Execution Boundary Error",
        owner="Runtime Resume Execution",
        reason="execution remains validation-only",
    )
    before_source = copy.deepcopy(source)
    before_request = copy.deepcopy(request)
    before_failure = copy.deepcopy(failure)

    build_execution_request(source)
    build_execution_result(request, failure=failure)

    assert source == before_source
    assert request == before_request
    assert failure == before_failure


def test_forbidden_execution_tokens_are_absent_from_builder_source():
    text = MODULE.read_text(encoding="utf-8")
    for token in (
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
        "open(",
        "write(",
        "Popen",
        "subprocess",
    ):
        assert token not in text


def test_builder_does_not_define_runtime_execution_surface():
    assert not hasattr(builder_module, "resume")
    assert not hasattr(builder_module, "execute_resume")
    assert not hasattr(builder_module, "recover")
    assert not hasattr(builder_module, "schedule")
    assert not hasattr(builder_module, "dispatch")


def test_package_sequence_contains_package_133_go_entry():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "## Package 133" in text
    assert "Package 133: Runtime Resume Execution Request Builder" in text
    assert "Final decision: GO" in text
    assert "Ready for Package 134: Runtime Resume Execution Consumer Boundary" in text
