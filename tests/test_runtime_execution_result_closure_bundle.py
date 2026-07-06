from pathlib import Path

from core.runtime.runtime_execution_result_intake_gate import evaluate_execution_result_intake
from core.runtime.runtime_result_validation_authority import evaluate_result_validation
from core.runtime.runtime_result_progress_apply_adapter import build_progress_apply_candidate
from core.runtime.runtime_execution_result_closure import evaluate_execution_result_closure


def valid_run_bridge_record(**overrides):
    record = {
        "controlled_run_authorized": True,
        "run_bridge_id": "run-bridge-1",
        "run_work_id": "work-1",
        "run_status": "finished",
        "run_result": {"message": "done"},
        "execution_started": True,
        "runtime_state_mutated": False,
    }
    record.update(overrides)
    return record


def test_execution_result_intake_accepts_valid_controlled_run_output():
    record = evaluate_execution_result_intake(valid_run_bridge_record())

    assert record.result_intake_authorized is True
    assert record.source_run_bridge_id == "run-bridge-1"
    assert record.result_work_id == "work-1"
    assert record.result_status == "finished"
    assert record.result_payload == {"message": "done"}
    assert record.progress_memory_mutated is False
    assert record.cursor_advanced is False
    assert record.scheduler_wake_requested is False
    assert record.runtime_state_mutated is False


def test_result_validation_accepts_authorized_intake():
    intake = evaluate_execution_result_intake(valid_run_bridge_record())
    record = evaluate_result_validation(intake)

    assert record.result_validation_authorized is True
    assert record.validated_work_id == "work-1"
    assert record.validated_status == "finished"
    assert record.progress_memory_mutated is False
    assert record.cursor_advanced is False
    assert record.scheduler_wake_requested is False
    assert record.runtime_state_mutated is False


def test_progress_apply_adapter_creates_candidate_without_mutation():
    intake = evaluate_execution_result_intake(valid_run_bridge_record())
    validation = evaluate_result_validation(intake)
    candidate = build_progress_apply_candidate(validation)

    assert candidate.progress_apply_candidate_created is True
    assert candidate.progress_work_id == "work-1"
    assert candidate.progress_status == "finished"
    assert candidate.progress_memory_mutated is False
    assert candidate.cursor_advanced is False
    assert candidate.scheduler_wake_requested is False
    assert candidate.runtime_state_mutated is False


def test_full_result_closure_happy_path_creates_loop_candidate_only():
    record = evaluate_execution_result_closure(valid_run_bridge_record())

    assert record.loop_closure_candidate_created is True
    assert record.result_intake_authorized is True
    assert record.result_validation_authorized is True
    assert record.progress_apply_candidate_created is True
    assert record.closure_work_id == "work-1"
    assert record.closure_status == "finished"
    assert record.progress_memory_mutated is False
    assert record.cursor_advanced is False
    assert record.scheduler_wake_requested is False
    assert record.runtime_state_mutated is False


def test_missing_run_bridge_record_denies_deterministically():
    record = evaluate_execution_result_closure(None)

    assert record.loop_closure_candidate_created is False
    assert record.denial_reason == "missing_run_bridge_record"
    assert record.progress_memory_mutated is False
    assert record.cursor_advanced is False
    assert record.scheduler_wake_requested is False


def test_rejected_run_bridge_denies_deterministically():
    record = evaluate_execution_result_closure(valid_run_bridge_record(controlled_run_authorized=False))

    assert record.loop_closure_candidate_created is False
    assert record.denial_reason == "run_bridge_not_authorized"


def test_missing_work_id_denies_deterministically():
    record = evaluate_execution_result_closure(valid_run_bridge_record(run_work_id=""))

    assert record.loop_closure_candidate_created is False
    assert record.denial_reason == "missing_result_work_id"


def test_unsupported_result_status_denies_deterministically():
    record = evaluate_execution_result_closure(valid_run_bridge_record(run_status="running"))

    assert record.loop_closure_candidate_created is False
    assert record.denial_reason == "unsupported_result_status"


def test_result_payload_must_be_mapping():
    record = evaluate_execution_result_closure(valid_run_bridge_record(run_result=["bad"]))

    assert record.loop_closure_candidate_created is False
    assert record.denial_reason == "result_payload_not_mapping"


def test_source_boundary_has_no_forbidden_imports_or_direct_runtime_calls():
    paths = [
        Path("core/runtime/runtime_execution_result_intake_gate.py"),
        Path("core/runtime/runtime_result_validation_authority.py"),
        Path("core/runtime/runtime_result_progress_apply_adapter.py"),
        Path("core/runtime/runtime_execution_result_closure.py"),
    ]
    forbidden = [
        "import scheduler",
        "from scheduler",
        "import executor",
        "from executor",
        "task_runner",
        "agent_loop",
        "work_package_operator",
        "run_one_step",
        ".run(",
    ]
    for path in paths:
        source = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in source, f"{token!r} found in {path}"
