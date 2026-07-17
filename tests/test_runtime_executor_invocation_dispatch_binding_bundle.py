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
from core.runtime.runtime_executor_adapter_attachment import (
    attach_runtime_executor_adapter,
)
from core.runtime.runtime_executor_adapter_binding import bind_runtime_executor_adapter
from core.runtime.runtime_executor_envelope import prepare_runtime_executor_envelope
from core.runtime.runtime_executor_invocation_approval import (
    evaluate_executor_invocation_approval,
)
from core.runtime.runtime_executor_invocation_dispatch import (
    ZERO_RUNTIME_EXECUTOR_INVOCATION_DISPATCH_SCHEMA,
    bind_executor_invocation_dispatch,
    summarize_executor_invocation_dispatch,
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
        "checkpoint_path": str(tmp_path / "dispatch-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _record(tmp_path: Path) -> dict[str, object]:
    launch = launch_goal_session("executor invocation dispatch", _config(tmp_path))
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
    return evaluate_executor_invocation_record(gate)


def test_dispatch_consumes_executor_invocation_record(tmp_path: Path) -> None:
    record = _record(tmp_path)
    result = bind_executor_invocation_dispatch(record)

    assert result["schema"] == ZERO_RUNTIME_EXECUTOR_INVOCATION_DISPATCH_SCHEMA
    assert result["dispatch_status"] == "dispatch_bound"
    assert result["dispatch_reason"] == "dispatch_binding_only_no_execution_start"
    assert result["invocation_id"] == record["executor_invocation_record_id"]
    assert result["gate_id"] == record["executor_invocation_gate_id"]
    assert result["executor_invoked"] is True
    assert result["execution_started"] is False
    assert result["frozen_metadata"]["dispatch_binding_only"] is True
    assert result["frozen_metadata"]["real_execution_enabled"] is False
    assert result["safe_summary"]["executor_invoked"] is True
    assert result["safe_summary"]["execution_started"] is False


def test_missing_or_unrecorded_invocation_record_is_rejected(tmp_path: Path) -> None:
    missing = bind_executor_invocation_dispatch(None)
    assert missing["dispatch_status"] == "rejected"
    assert missing["dispatch_reason"] == "missing_executor_invocation_record"
    assert missing["executor_invoked"] is False

    record = _record(tmp_path)
    record["executor_invocation_recorded"] = False
    result = bind_executor_invocation_dispatch(record)

    assert result["dispatch_status"] == "rejected"
    assert result["dispatch_reason"] == "invocation_recorded_false"
    assert result["executor_invoked"] is False
    assert result["execution_started"] is False


def test_execution_already_started_is_rejected(tmp_path: Path) -> None:
    record = _record(tmp_path)
    record["execution_started"] = True

    result = bind_executor_invocation_dispatch(record)

    assert result["dispatch_status"] == "rejected"
    assert result["dispatch_reason"] == "execution_already_started"
    assert result["executor_invoked"] is False
    assert result["execution_started"] is False


def test_duplicate_dispatch_rejected_deterministically(tmp_path: Path) -> None:
    record = _record(tmp_path)
    first = bind_executor_invocation_dispatch(record)
    result = bind_executor_invocation_dispatch(
        record,
        existing_dispatches=[first],
    )
    repeat = bind_executor_invocation_dispatch(
        record,
        existing_dispatches=[first],
    )

    assert result == repeat
    assert result["dispatch_status"] == "rejected"
    assert result["dispatch_reason"] == "duplicate_invocation_dispatch"
    assert result["executor_invoked"] is False
    assert result["execution_started"] is False


def test_invalid_lineage_rejected(tmp_path: Path) -> None:
    record = _record(tmp_path)
    record["source_executor_invocation_gate_id"] = "wrong-gate"

    result = bind_executor_invocation_dispatch(record)

    assert result["dispatch_status"] == "rejected"
    assert result["dispatch_reason"] == "invalid_lineage"
    assert result["executor_invoked"] is False
    assert result["execution_started"] is False


def test_approval_gate_record_dispatch_chain_is_deterministic(tmp_path: Path) -> None:
    record = _record(tmp_path)
    first = bind_executor_invocation_dispatch(record)
    second = bind_executor_invocation_dispatch(record)

    assert first == second
    assert first["dispatch_id"]
    assert first["frozen_metadata"]["lineage"]["executor_invocation_record_id"] == (
        record["executor_invocation_record_id"]
    )
    assert first["frozen_metadata"]["lineage"]["executor_invocation_gate_id"] == (
        record["executor_invocation_gate_id"]
    )
    summary = summarize_executor_invocation_dispatch(first)
    assert summary["executor_invocation_dispatch_status"] == "dispatch_bound"
    assert summary["executor_invoked"] is True
    assert summary["execution_started"] is False


def test_service_output_exposes_dispatch_status(tmp_path: Path) -> None:
    service = RuntimeOperatorService(_config(tmp_path))
    result = service.run_goal("operator invocation dispatch")
    status = service.status()
    dispatch = result["executor_invocation_dispatch"]

    assert result["invocation_gate_status"] == "opened"
    assert result["executor_invocation_gate_open"] is True
    assert result["invocation_record_status"] == "recorded"
    assert result["executor_invocation_recorded"] is True
    assert result["executor_invocation_dispatch_status"] == "dispatch_bound"
    assert result["executor_invoked"] is True
    assert result["execution_started"] is True
    assert result["execution_dry_run"] is True
    assert result["mutation_allowed"] is False
    assert dispatch["dispatch_status"] == "dispatch_bound"
    assert dispatch["executor_invoked"] is True
    assert dispatch["execution_started"] is False
    assert status["executor_invocation_dispatch_status"][
        "executor_invocation_dispatch_status"
    ] == "dispatch_bound"
    assert status["executor_invocation_dispatch_status"]["executor_invoked"] is True
    assert status["executor_invocation_dispatch_status"]["execution_started"] is False
    assert status["runtime_execution_session_start_status"]["execution_started"] is True
    assert status["runtime_execution_session_start_status"]["execution_dry_run"] is True
    assert status["runtime_execution_session_start_status"]["mutation_allowed"] is False


def test_no_real_execution_surface_or_repo_mutation() -> None:
    files = [
        Path("core/runtime/runtime_executor_invocation_dispatch.py"),
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
