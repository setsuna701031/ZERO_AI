import copy
import inspect
from pathlib import Path

import core.runtime.aer_runtime_resume_execution_consumer as consumer_module
from core.runtime.aer_runtime_resume_execution_builder import (
    build_execution_failure,
    build_execution_request,
    build_execution_result,
    execution_failure_to_summary,
    execution_request_to_summary,
    execution_result_to_summary,
)
from core.runtime.aer_runtime_resume_execution_consumer import (
    EXECUTION_CONSUMER_BOUNDARY_CONTRACT,
    EXECUTION_CONSUMER_INPUT_CONTRACT,
    EXECUTION_CONSUMER_OUTPUT_CONTRACT,
    build_execution_consumer_input,
    build_execution_consumer_output,
    execution_consumer_input_to_summary,
    execution_consumer_output_to_summary,
    validate_execution_consumer_input,
    validate_execution_consumer_output,
)
from core.runtime.aer_runtime_resume_execution_validation import (
    EXECUTION_FAILURE_CONTRACT,
    EXECUTION_REQUEST_CONTRACT,
    EXECUTION_RESULT_CONTRACT,
    RESUME_CONSUMER_OUTPUT_CONTRACT,
)

MODULE = Path("core/runtime/aer_runtime_resume_execution_consumer.py")
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
            "contract": "aer.runtime.resume.execution_boundary.v1",
            "execution_allowed": False,
            "future_domain_only": True,
            "reason": "execution remains future-domain only",
        },
        "consumer_boundary": {
            "contract": "aer.runtime.resume.consumer_boundary.v1",
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


def _execution_result_summary(**overrides):
    request = build_execution_request(_consumer_output())
    result = build_execution_result(request)
    summary = execution_result_to_summary(result)
    summary.update(overrides)
    return summary


def test_execution_consumer_module_exists_and_public_api_is_separate():
    assert MODULE.exists()
    assert consumer_module.__all__ == [
        "EXECUTION_CONSUMER_INPUT_CONTRACT",
        "EXECUTION_CONSUMER_OUTPUT_CONTRACT",
        "EXECUTION_CONSUMER_BOUNDARY_CONTRACT",
        "build_execution_consumer_input",
        "validate_execution_consumer_input",
        "build_execution_consumer_output",
        "validate_execution_consumer_output",
        "execution_consumer_input_to_summary",
        "execution_consumer_output_to_summary",
    ]

    public_functions = {
        name
        for name, value in inspect.getmembers(consumer_module, inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_functions == {
        "build_execution_consumer_input",
        "validate_execution_consumer_input",
        "build_execution_consumer_output",
        "validate_execution_consumer_output",
        "execution_consumer_input_to_summary",
        "execution_consumer_output_to_summary",
    }


def test_consumer_imports_only_execution_validation_not_downstream_domains():
    text = MODULE.read_text(encoding="utf-8")
    assert "aer_runtime_resume_execution_validation" in text
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
        "build_execution_request(",
        "build_execution_result(",
        "build_execution_failure(",
    ):
        assert token not in text


def test_build_consumer_input_from_execution_result_summary_is_valid_and_data_only():
    source = _execution_result_summary()
    consumer_input = build_execution_consumer_input(source)

    assert consumer_input == {
        "contract": EXECUTION_CONSUMER_INPUT_CONTRACT,
        "source_contract": EXECUTION_RESULT_CONTRACT,
        "source_valid": True,
        "source_kind": "execution_result",
        "execution_request_id": source["execution_request_id"],
        "resume_token": source["resume_token"],
        "snapshot_id": source["snapshot_id"],
        "status": "validated",
        "reason": None,
        "completed": False,
        "failed": False,
        "downstream_handoff_required": False,
        "downstream_handoff_type": None,
        "consumer_boundary": {
            "contract": EXECUTION_CONSUMER_BOUNDARY_CONTRACT,
            "future_domain_only": True,
            "execution_allowed": False,
            "downstream_authorized": False,
            "allowed_future_domains": [
                "Future Runtime Resume Execution",
                "Future Recovery",
                "Future Scheduler",
                "Future Dispatcher",
                "Future Operator",
            ],
            "reason": "downstream consumption requires future domain contracts",
        },
        "descriptive_only": True,
    }
    assert validate_execution_consumer_input(consumer_input)["valid"] is True


def test_build_consumer_input_accepts_request_and_failure_summaries():
    request_summary = execution_request_to_summary(build_execution_request(_consumer_output()))
    failure_summary = execution_failure_to_summary(
        build_execution_failure(
            failure_code="future_domain_required",
            category="Future Domain Required",
            owner="Runtime Resume Execution",
            reason="future domain required",
        )
    )

    request_input = build_execution_consumer_input(request_summary)
    failure_input = build_execution_consumer_input(failure_summary)

    assert request_input["source_contract"] == EXECUTION_REQUEST_CONTRACT
    assert request_input["source_kind"] == "execution_request"
    assert validate_execution_consumer_input(request_input)["valid"] is True
    assert failure_input["source_contract"] == EXECUTION_FAILURE_CONTRACT
    assert failure_input["source_kind"] == "execution_failure"
    assert validate_execution_consumer_input(failure_input)["valid"] is True


def test_consumer_input_blocks_invalid_source_contract():
    consumer_input = build_execution_consumer_input({"contract": "not.execution.summary"})

    assert consumer_input["source_kind"] == "invalid"
    assert validate_execution_consumer_input(consumer_input) == {
        "valid": False,
        "category": "Compatibility Error",
        "reason": "invalid execution source contract",
        "auto_repair_allowed": False,
        "descriptive_only": True,
    }


def test_build_consumer_output_accepts_valid_result_summary_for_future_domain_only():
    consumer_input = build_execution_consumer_input(_execution_result_summary())
    output = build_execution_consumer_output(consumer_input)

    assert output["contract"] == EXECUTION_CONSUMER_OUTPUT_CONTRACT
    assert output["accepted_for_future_domain"] is True
    assert output["blocked"] is False
    assert output["status"] == "accepted_for_future_domain"
    assert output["reason"] is None
    assert output["execution_request_id"] == consumer_input["execution_request_id"]
    assert output["resume_token"] == consumer_input["resume_token"]
    assert output["snapshot_id"] == consumer_input["snapshot_id"]
    assert output["source_kind"] == "execution_result"
    assert output["downstream_handoff_required"] is False
    assert output["downstream_handoff_type"] is None
    assert output["consumer_boundary"]["execution_allowed"] is False
    assert output["consumer_boundary"]["downstream_authorized"] is False
    assert output["descriptive_only"] is True
    assert validate_execution_consumer_output(output)["valid"] is True


def test_consumer_output_blocks_invalid_input():
    bad_input = build_execution_consumer_input({"contract": "not.execution.summary"})
    output = build_execution_consumer_output(bad_input)

    assert output["accepted_for_future_domain"] is False
    assert output["blocked"] is True
    assert output["status"] == "invalid_consumer_input"
    assert output["reason"] == "invalid execution consumer input"
    assert validate_execution_consumer_output(output)["valid"] is True


def test_consumer_output_blocks_invalid_source_summary():
    consumer_input = build_execution_consumer_input(_execution_result_summary(valid=False))
    output = build_execution_consumer_output(consumer_input)

    assert validate_execution_consumer_input(consumer_input)["valid"] is True
    assert output["accepted_for_future_domain"] is False
    assert output["blocked"] is True
    assert output["status"] == "invalid_execution_summary"
    assert output["reason"] == "invalid execution summary"


def test_consumer_output_blocks_downstream_handoff_required_until_future_contract():
    consumer_input = build_execution_consumer_input(
        _execution_result_summary(
            status="handoff_required",
            downstream_handoff_required=True,
            downstream_handoff_type="recovery",
        )
    )
    output = build_execution_consumer_output(consumer_input)

    assert validate_execution_consumer_input(consumer_input)["valid"] is True
    assert output["accepted_for_future_domain"] is False
    assert output["blocked"] is True
    assert output["status"] == "future_domain_required"
    assert output["reason"] == "downstream handoff requires future domain contract"
    assert output["downstream_handoff_required"] is True
    assert output["downstream_handoff_type"] == "recovery"


def test_consumer_input_and_output_reject_unknown_fields_and_callable_values():
    consumer_input = build_execution_consumer_input(_execution_result_summary())
    output = build_execution_consumer_output(consumer_input)

    assert validate_execution_consumer_input(dict(consumer_input, extra="x"))["reason"] == "unknown consumer input fields"
    assert validate_execution_consumer_output(dict(output, extra="x"))["reason"] == "unknown consumer output fields"
    bad_input = copy.deepcopy(consumer_input)
    bad_input["consumer_boundary"]["callable"] = lambda: None
    assert validate_execution_consumer_input(bad_input)["category"] == "Execution Boundary Error"
    bad_output = copy.deepcopy(output)
    bad_output["consumer_boundary"]["callable"] = lambda: None
    assert validate_execution_consumer_output(bad_output)["category"] == "Execution Boundary Error"


def test_consumer_boundary_cannot_authorize_execution_or_downstream():
    consumer_input = build_execution_consumer_input(_execution_result_summary())
    output = build_execution_consumer_output(consumer_input)

    for payload, validator in (
        (consumer_input, validate_execution_consumer_input),
        (output, validate_execution_consumer_output),
    ):
        bad = copy.deepcopy(payload)
        bad["consumer_boundary"]["execution_allowed"] = True
        assert validator(bad)["reason"] == "invalid execution consumer boundary"
        bad = copy.deepcopy(payload)
        bad["consumer_boundary"]["downstream_authorized"] = True
        assert validator(bad)["reason"] == "invalid execution consumer boundary"


def test_consumer_summaries_are_stable_projection_only():
    consumer_input = build_execution_consumer_input(_execution_result_summary())
    output = build_execution_consumer_output(consumer_input)

    assert execution_consumer_input_to_summary(consumer_input) == {
        "contract": EXECUTION_CONSUMER_INPUT_CONTRACT,
        "valid": True,
        "source_contract": EXECUTION_RESULT_CONTRACT,
        "source_valid": True,
        "source_kind": "execution_result",
        "execution_request_id": consumer_input["execution_request_id"],
        "resume_token": consumer_input["resume_token"],
        "snapshot_id": consumer_input["snapshot_id"],
        "status": "validated",
        "downstream_handoff_required": False,
        "downstream_handoff_type": None,
    }
    assert execution_consumer_output_to_summary(output) == {
        "contract": EXECUTION_CONSUMER_OUTPUT_CONTRACT,
        "valid": True,
        "accepted_for_future_domain": True,
        "blocked": False,
        "status": "accepted_for_future_domain",
        "reason": None,
        "execution_request_id": output["execution_request_id"],
        "resume_token": output["resume_token"],
        "snapshot_id": output["snapshot_id"],
        "source_kind": "execution_result",
        "downstream_handoff_required": False,
        "downstream_handoff_type": None,
    }


def test_consumer_output_is_deterministic_and_does_not_mutate_inputs():
    source = _execution_result_summary()
    consumer_input = build_execution_consumer_input(source)
    before_source = copy.deepcopy(source)
    before_input = copy.deepcopy(consumer_input)

    assert build_execution_consumer_input(source) == build_execution_consumer_input(copy.deepcopy(source))
    assert build_execution_consumer_output(consumer_input) == build_execution_consumer_output(copy.deepcopy(consumer_input))
    assert source == before_source
    assert consumer_input == before_input


def test_no_execution_behavior_or_downstream_api_is_exposed():
    for name in (
        "resume",
        "execute_resume",
        "recover",
        "schedule",
        "dispatch",
        "operate",
        "persist",
        "audit",
        "journal",
        "replay",
    ):
        assert not hasattr(consumer_module, name)

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
        "Popen",
        "run(",
        "open(",
        "write(",
    ):
        assert token not in text


def test_package_sequence_contains_package_134_entry():
    text = PACKAGE_SEQUENCE.read_text(encoding="utf-8")
    assert "## Package 134" in text
    assert "Runtime Resume Execution Consumer Boundary" in text
    assert "core/runtime/aer_runtime_resume_execution_consumer.py" in text
    assert "Final decision: GO" in text
    assert "Ready for Package 135: Runtime Resume Execution Closure Review" in text
