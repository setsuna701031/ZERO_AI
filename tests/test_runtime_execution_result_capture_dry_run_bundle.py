from pathlib import Path

from core.runtime.runtime_autonomous_cycle_binding import bind_worker_pickup_to_cycle
from core.runtime.runtime_autonomous_cycle_execution_bridge import (
    bridge_cycle_binding_to_execution_request,
)
from core.runtime.runtime_controlled_action_authorization import (
    authorize_controlled_action,
)
from core.runtime.runtime_controlled_action_commit import commit_controlled_action
from core.runtime.runtime_controlled_action_proposal import propose_controlled_action
from core.runtime.runtime_controlled_loop_activation import (
    activate_controlled_loop_tick,
)
from core.runtime.runtime_controlled_tick_decision import decide_controlled_tick
from core.runtime.runtime_execution_admission_gate import admit_runtime_execution
from core.runtime.runtime_execution_permit import permit_runtime_execution
from core.runtime.runtime_execution_result_capture import (
    ZERO_RUNTIME_EXECUTION_RESULT_CAPTURE_SCHEMA,
    capture_runtime_execution_result_dry_run,
    summarize_runtime_execution_result_capture,
)
from core.runtime.runtime_execution_session_start import (
    start_runtime_execution_session_dry_run,
)
from core.runtime.runtime_executor_adapter_attachment import (
    attach_runtime_executor_adapter,
)
from core.runtime.runtime_executor_adapter_binding import bind_runtime_executor_adapter
from core.runtime.runtime_executor_envelope import prepare_runtime_executor_envelope
from core.runtime.runtime_executor_invocation_approval import (
    evaluate_executor_invocation_approval,
)
from core.runtime.runtime_executor_invocation_dispatch import (
    bind_executor_invocation_dispatch,
)
from core.runtime.runtime_executor_invocation_gate import (
    evaluate_executor_invocation_gate,
)
from core.runtime.runtime_executor_invocation_preparation import (
    evaluate_executor_invocation_preparation,
)
from core.runtime.runtime_executor_invocation_record import (
    evaluate_executor_invocation_record,
)
from core.runtime.runtime_goal_queue_admission import submit_goal_session_to_queue
from core.runtime.runtime_goal_session_launcher import launch_goal_session
from core.runtime.runtime_operator_service import RuntimeOperatorService
from core.runtime.runtime_queue_worker_pickup import (
    submit_queue_entry_for_worker_pickup,
)


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "result-capture-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _session(tmp_path: Path) -> dict[str, object]:
    launch = launch_goal_session("execution result capture", _config(tmp_path))
    queued = submit_goal_session_to_queue(launch)
    pickup = submit_queue_entry_for_worker_pickup(queued["queue_entry"])
    cycle = bind_worker_pickup_to_cycle(pickup["worker_pickup_record"])
    bridge = bridge_cycle_binding_to_execution_request(cycle["cycle_binding"])
    loop = activate_controlled_loop_tick(bridge["execution_request"])
    decision = decide_controlled_tick(loop["controlled_loop_tick"])
    proposal = propose_controlled_action(decision["controlled_tick_decision"])
    authorization = authorize_controlled_action(proposal["action_proposal"])
    commit = commit_controlled_action(authorization["action_authorization"])
    admission = admit_runtime_execution(commit["action_commit"])
    permit = permit_runtime_execution(admission["execution_admission"])
    envelope = prepare_runtime_executor_envelope(permit["execution_permit"])
    binding = bind_runtime_executor_adapter(envelope["executor_envelope"])
    attachment = attach_runtime_executor_adapter(binding["executor_adapter_binding"])
    preparation = evaluate_executor_invocation_preparation(
        attachment["executor_adapter_attachment"]
    )
    approval = evaluate_executor_invocation_approval(preparation)
    gate = evaluate_executor_invocation_gate(approval)
    record = evaluate_executor_invocation_record(gate)
    dispatch = bind_executor_invocation_dispatch(record)
    return start_runtime_execution_session_dry_run(dispatch)


def test_result_capture_consumes_session_start_result(tmp_path: Path) -> None:
    session = _session(tmp_path)
    result = capture_runtime_execution_result_dry_run(session)

    assert result["schema"] == ZERO_RUNTIME_EXECUTION_RESULT_CAPTURE_SCHEMA
    assert result["result_status"] == "dry_run_completed"
    assert result["result_reason"] == "dry_run_result_recorded_no_executor_output"
    assert result["execution_session_id"] == session["execution_session_id"]
    assert result["dispatch_id"] == session["dispatch_id"]
    assert result["invocation_id"] == session["invocation_id"]
    assert result["gate_id"] == session["gate_id"]
    assert result["execution_started"] is True
    assert result["execution_completed"] is True
    assert result["result_recorded"] is True
    assert result["dry_run"] is True
    assert result["mutation_allowed"] is False
    assert result["output_summary"]["executor_output_present"] is False
    assert result["error_summary"]["error_present"] is False


def test_rejects_missing_or_not_started_session(tmp_path: Path) -> None:
    missing = capture_runtime_execution_result_dry_run(None)
    assert missing["result_status"] == "rejected"
    assert missing["result_reason"] == "missing_execution_session"

    session = _session(tmp_path)
    session["execution_started"] = False
    result = capture_runtime_execution_result_dry_run(session)

    assert result["result_status"] == "rejected"
    assert result["result_reason"] == "execution_not_started"
    assert result["execution_completed"] is False
    assert result["result_recorded"] is False


def test_rejects_non_dry_run_session(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session["dry_run"] = False

    result = capture_runtime_execution_result_dry_run(session)

    assert result["result_status"] == "rejected"
    assert result["result_reason"] == "dry_run_required"
    assert result["dry_run"] is False
    assert result["execution_completed"] is False


def test_mutation_allowed_remains_false(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session["mutation_allowed"] = True

    result = capture_runtime_execution_result_dry_run(session)

    assert result["result_status"] == "rejected"
    assert result["result_reason"] == "mutation_not_allowed"
    assert result["mutation_allowed"] is True
    assert result["result_recorded"] is False


def test_duplicate_capture_rejected_deterministically(tmp_path: Path) -> None:
    session = _session(tmp_path)
    first = capture_runtime_execution_result_dry_run(session)
    result = capture_runtime_execution_result_dry_run(
        session,
        existing_results=[first],
    )
    repeat = capture_runtime_execution_result_dry_run(
        session,
        existing_results=[first],
    )

    assert result == repeat
    assert result["result_status"] == "rejected"
    assert result["result_reason"] == "duplicate_execution_result_capture"
    assert result["execution_completed"] is False
    assert result["result_recorded"] is False


def test_lineage_mismatch_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session["gate_id"] = "wrong-gate"

    result = capture_runtime_execution_result_dry_run(session)

    assert result["result_status"] == "rejected"
    assert result["result_reason"] == "invalid_lineage"
    assert result["execution_completed"] is False


def test_full_chain_is_deterministic(tmp_path: Path) -> None:
    session = _session(tmp_path)
    first = capture_runtime_execution_result_dry_run(session)
    second = capture_runtime_execution_result_dry_run(session)

    assert first == second
    assert first["execution_result_id"]
    assert first["frozen_metadata"]["lineage"]["execution_session_id"] == (
        session["execution_session_id"]
    )
    assert first["frozen_metadata"]["lineage"]["dispatch_id"] == session[
        "dispatch_id"
    ]
    summary = summarize_runtime_execution_result_capture(first)
    assert summary["runtime_execution_result_capture_status"] == "dry_run_completed"
    assert summary["execution_completed"] is True
    assert summary["execution_result_recorded"] is True
    assert summary["execution_dry_run"] is True
    assert summary["mutation_allowed"] is False


def test_service_output_exposes_result_capture_status(tmp_path: Path) -> None:
    service = RuntimeOperatorService(_config(tmp_path))
    result = service.run_goal("operator result capture")
    status = service.status()
    capture = result["runtime_execution_result_capture"]

    assert result["executor_invocation_gate_open"] is True
    assert result["executor_invocation_recorded"] is True
    assert result["executor_invoked"] is True
    assert result["execution_started"] is True
    assert result["execution_completed"] is True
    assert result["execution_result_recorded"] is True
    assert result["execution_dry_run"] is True
    assert result["mutation_allowed"] is False
    assert result["runtime_execution_result_capture_status"] == "dry_run_completed"
    assert capture["result_status"] == "dry_run_completed"
    assert capture["output_summary"]["executor_output_present"] is False
    assert status["runtime_execution_result_capture_status"][
        "runtime_execution_result_capture_status"
    ] == "dry_run_completed"
    assert status["runtime_execution_result_capture_status"][
        "execution_completed"
    ] is True
    assert status["runtime_execution_result_capture_status"][
        "execution_result_recorded"
    ] is True
    assert status["runtime_execution_result_capture_status"][
        "mutation_allowed"
    ] is False


def test_no_real_execution_surface_or_repo_mutation() -> None:
    files = [
        Path("core/runtime/runtime_execution_result_capture.py"),
        Path("core/runtime/runtime_operator_service.py"),
    ]
    forbidden = [
        "executor.invoke",
        "adapter.invoke",
        "subprocess",
        "step_executor",
        "stepexecutor",
        "task_runner",
        "taskrunner",
        "progress_memory.write",
        "scheduler.advance",
        ".run(",
        "exec(",
        "eval(",
        "open(",
        "write_text",
        "write_bytes",
        "repo_mutated = true",
        "runtime_mutated = true",
        "cursor_advanced = true",
    ]
    for file in files:
        source = file.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in source, f"forbidden token present: {token}"
