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
    capture_runtime_execution_result_dry_run,
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
from core.runtime.runtime_executor_runtime_closure import (
    ZERO_RUNTIME_EXECUTOR_RUNTIME_CLOSURE_SCHEMA,
    close_executor_runtime_dry_run,
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
        "checkpoint_path": str(tmp_path / "executor-closure-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _result_capture(tmp_path: Path) -> dict[str, object]:
    launch = launch_goal_session("executor runtime closure", _config(tmp_path))
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
    session = start_runtime_execution_session_dry_run(dispatch)
    return capture_runtime_execution_result_dry_run(session)


def test_closure_consumes_result_capture_and_records_handoffs(tmp_path: Path) -> None:
    capture = _result_capture(tmp_path)
    closure = close_executor_runtime_dry_run(capture)

    assert closure["schema"] == ZERO_RUNTIME_EXECUTOR_RUNTIME_CLOSURE_SCHEMA
    assert closure["closure_status"] == "dry_run_runtime_closed"
    assert closure["feedback_recorded"] is True
    assert closure["recovery_handoff_recorded"] is True
    assert closure["memory_handoff_recorded"] is True
    assert closure["recovery_connected"] is True
    assert closure["memory_connected"] is True
    assert closure["real_executor_ready"] is True
    assert closure["real_executor_enabled"] is False
    assert closure["execution_dry_run"] is True
    assert closure["mutation_allowed"] is False
    assert closure["feedback_record"]["feedback_recorded"] is True
    assert closure["recovery_handoff"]["recovery_connected"] is True
    assert closure["memory_handoff"]["memory_connected"] is True
    assert closure["readiness_status"]["real_executor_enabled"] is False


def test_rejects_invalid_result_capture_states(tmp_path: Path) -> None:
    missing = close_executor_runtime_dry_run(None)
    assert missing["closure_status"] == "rejected"
    assert missing["closure_reason"] == "missing_execution_result_capture"

    capture = _result_capture(tmp_path)
    capture["execution_completed"] = False
    not_completed = close_executor_runtime_dry_run(capture)
    assert not_completed["closure_reason"] == "execution_not_completed"

    capture = _result_capture(tmp_path)
    capture["result_recorded"] = False
    not_recorded = close_executor_runtime_dry_run(capture)
    assert not_recorded["closure_reason"] == "execution_result_not_recorded"

    capture = _result_capture(tmp_path)
    capture["dry_run"] = False
    not_dry_run = close_executor_runtime_dry_run(capture)
    assert not_dry_run["closure_reason"] == "dry_run_required"

    capture = _result_capture(tmp_path)
    capture["mutation_allowed"] = True
    mutation = close_executor_runtime_dry_run(capture)
    assert mutation["closure_reason"] == "mutation_not_allowed"


def test_duplicate_closure_rejected_deterministically(tmp_path: Path) -> None:
    capture = _result_capture(tmp_path)
    first = close_executor_runtime_dry_run(capture)
    result = close_executor_runtime_dry_run(capture, existing_closures=[first])
    repeat = close_executor_runtime_dry_run(capture, existing_closures=[first])

    assert result == repeat
    assert result["closure_status"] == "rejected"
    assert result["closure_reason"] == "duplicate_executor_runtime_closure"
    assert result["feedback_recorded"] is False
    assert result["real_executor_enabled"] is False


def test_lineage_mismatch_rejected(tmp_path: Path) -> None:
    capture = _result_capture(tmp_path)
    capture["gate_id"] = "wrong-gate"

    result = close_executor_runtime_dry_run(capture)

    assert result["closure_status"] == "rejected"
    assert result["closure_reason"] == "invalid_lineage"
    assert result["feedback_recorded"] is False


def test_full_chain_closure_is_deterministic(tmp_path: Path) -> None:
    capture = _result_capture(tmp_path)
    first = close_executor_runtime_dry_run(capture)
    second = close_executor_runtime_dry_run(capture)

    assert first == second
    assert first["closure_id"]
    assert first["execution_result_id"] == capture["execution_result_id"]
    assert first["safe_summary"]["runtime_executor_closure_status"] == (
        "dry_run_runtime_closed"
    )
    assert first["frozen_metadata"]["lineage"]["execution_result_id"] == (
        capture["execution_result_id"]
    )


def test_runtime_operator_service_exposes_closure_fields(tmp_path: Path) -> None:
    service = RuntimeOperatorService(_config(tmp_path))
    result = service.run_goal("operator executor runtime closure")
    status = service.status()
    closure = result["runtime_executor_closure"]

    assert result["executor_invocation_gate_open"] is True
    assert result["executor_invocation_recorded"] is True
    assert result["executor_invoked"] is True
    assert result["execution_started"] is True
    assert result["execution_completed"] is True
    assert result["execution_result_recorded"] is True
    assert result["feedback_recorded"] is True
    assert result["recovery_handoff_recorded"] is True
    assert result["memory_handoff_recorded"] is True
    assert result["recovery_connected"] is True
    assert result["memory_connected"] is True
    assert result["real_executor_ready"] is True
    assert result["real_executor_enabled"] is False
    assert result["execution_dry_run"] is True
    assert result["mutation_allowed"] is False
    assert result["runtime_executor_closure_status"] == "dry_run_runtime_closed"
    assert closure["closure_status"] == "dry_run_runtime_closed"
    assert status["runtime_executor_closure_status"][
        "runtime_executor_closure_status"
    ] == "dry_run_runtime_closed"
    assert status["runtime_executor_closure_status"]["feedback_recorded"] is True
    assert status["runtime_executor_closure_status"]["real_executor_ready"] is True
    assert status["runtime_executor_closure_status"]["real_executor_enabled"] is False


def test_no_real_execution_surface_or_repo_mutation() -> None:
    files = [
        Path("core/runtime/runtime_executor_runtime_closure.py"),
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
