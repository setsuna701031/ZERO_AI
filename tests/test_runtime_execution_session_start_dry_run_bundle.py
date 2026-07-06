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
from core.runtime.runtime_execution_session_start import (
    ZERO_RUNTIME_EXECUTION_SESSION_START_SCHEMA,
    start_runtime_execution_session_dry_run,
    summarize_runtime_execution_session_start,
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
        "checkpoint_path": str(tmp_path / "session-start-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _dispatch(tmp_path: Path) -> dict[str, object]:
    launch = launch_goal_session("execution session start", _config(tmp_path))
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
    return bind_executor_invocation_dispatch(record)


def test_session_start_consumes_dispatch_result(tmp_path: Path) -> None:
    dispatch = _dispatch(tmp_path)
    result = start_runtime_execution_session_dry_run(dispatch)

    assert result["schema"] == ZERO_RUNTIME_EXECUTION_SESSION_START_SCHEMA
    assert result["execution_status"] == "dry_run_started"
    assert result["execution_reason"] == "dry_run_execution_session_started_no_mutation"
    assert result["dispatch_id"] == dispatch["dispatch_id"]
    assert result["invocation_id"] == dispatch["invocation_id"]
    assert result["gate_id"] == dispatch["gate_id"]
    assert result["execution_started"] is True
    assert result["dry_run"] is True
    assert result["mutation_allowed"] is False
    assert result["frozen_metadata"]["real_execution_enabled"] is False
    assert result["safe_summary"]["execution_dry_run"] is True


def test_execution_started_true_only_in_dry_run_mode(tmp_path: Path) -> None:
    dispatch = _dispatch(tmp_path)
    rejected = start_runtime_execution_session_dry_run(dispatch, dry_run=False)

    assert rejected["execution_status"] == "rejected"
    assert rejected["execution_reason"] == "dry_run_required"
    assert rejected["execution_started"] is False
    assert rejected["dry_run"] is False

    started = start_runtime_execution_session_dry_run(dispatch, dry_run=True)
    assert started["execution_status"] == "dry_run_started"
    assert started["execution_started"] is True
    assert started["dry_run"] is True


def test_mutation_allowed_false_is_required(tmp_path: Path) -> None:
    dispatch = _dispatch(tmp_path)
    result = start_runtime_execution_session_dry_run(
        dispatch,
        mutation_allowed=True,
    )

    assert result["execution_status"] == "rejected"
    assert result["execution_reason"] == "mutation_not_allowed"
    assert result["execution_started"] is False
    assert result["mutation_allowed"] is True


def test_dispatch_rejection_cases_are_deterministic(tmp_path: Path) -> None:
    missing = start_runtime_execution_session_dry_run(None)
    assert missing["execution_status"] == "rejected"
    assert missing["execution_reason"] == "missing_executor_invocation_dispatch"

    dispatch = _dispatch(tmp_path)
    dispatch["executor_invoked"] = False
    first = start_runtime_execution_session_dry_run(dispatch)
    second = start_runtime_execution_session_dry_run(dispatch)

    assert first == second
    assert first["execution_status"] == "rejected"
    assert first["execution_reason"] == "executor_not_invoked"
    assert first["execution_started"] is False


def test_execution_already_started_on_dispatch_is_rejected(tmp_path: Path) -> None:
    dispatch = _dispatch(tmp_path)
    dispatch["execution_started"] = True

    result = start_runtime_execution_session_dry_run(dispatch)

    assert result["execution_status"] == "rejected"
    assert result["execution_reason"] == "dispatch_execution_already_started"
    assert result["execution_started"] is False


def test_duplicate_session_rejected_deterministically(tmp_path: Path) -> None:
    dispatch = _dispatch(tmp_path)
    first = start_runtime_execution_session_dry_run(dispatch)
    result = start_runtime_execution_session_dry_run(
        dispatch,
        existing_sessions=[first],
    )
    repeat = start_runtime_execution_session_dry_run(
        dispatch,
        existing_sessions=[first],
    )

    assert result == repeat
    assert result["execution_status"] == "rejected"
    assert result["execution_reason"] == "duplicate_execution_session_start"
    assert result["execution_started"] is False


def test_invalid_lineage_rejected(tmp_path: Path) -> None:
    dispatch = _dispatch(tmp_path)
    dispatch["gate_id"] = "wrong-gate"

    result = start_runtime_execution_session_dry_run(dispatch)

    assert result["execution_status"] == "rejected"
    assert result["execution_reason"] == "invalid_lineage"
    assert result["execution_started"] is False


def test_chain_remains_deterministic(tmp_path: Path) -> None:
    dispatch = _dispatch(tmp_path)
    first = start_runtime_execution_session_dry_run(dispatch)
    second = start_runtime_execution_session_dry_run(dispatch)

    assert first == second
    assert first["execution_session_id"]
    assert first["frozen_metadata"]["lineage"]["dispatch_id"] == dispatch[
        "dispatch_id"
    ]
    summary = summarize_runtime_execution_session_start(first)
    assert summary["runtime_execution_session_start_status"] == "dry_run_started"
    assert summary["execution_started"] is True
    assert summary["execution_dry_run"] is True
    assert summary["mutation_allowed"] is False


def test_service_output_exposes_execution_session_start_status(tmp_path: Path) -> None:
    service = RuntimeOperatorService(_config(tmp_path))
    result = service.run_goal("operator session start")
    status = service.status()
    session = result["runtime_execution_session_start"]

    assert result["executor_invocation_gate_open"] is True
    assert result["executor_invocation_recorded"] is True
    assert result["executor_invoked"] is True
    assert result["runtime_execution_session_start_status"] == "dry_run_started"
    assert result["execution_started"] is True
    assert result["execution_dry_run"] is True
    assert result["mutation_allowed"] is False
    assert session["execution_status"] == "dry_run_started"
    assert session["execution_started"] is True
    assert session["dry_run"] is True
    assert session["mutation_allowed"] is False
    assert status["runtime_execution_session_start_status"][
        "runtime_execution_session_start_status"
    ] == "dry_run_started"
    assert status["runtime_execution_session_start_status"]["execution_started"] is True
    assert status["runtime_execution_session_start_status"]["execution_dry_run"] is True
    assert status["runtime_execution_session_start_status"]["mutation_allowed"] is False


def test_no_real_execution_surface_or_repo_mutation() -> None:
    files = [
        Path("core/runtime/runtime_execution_session_start.py"),
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
