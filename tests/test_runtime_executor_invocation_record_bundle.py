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
from core.runtime.runtime_executor_invocation_gate import (
    evaluate_executor_invocation_gate,
)
from core.runtime.runtime_executor_invocation_preparation import (
    evaluate_executor_invocation_preparation,
)
from core.runtime.runtime_executor_invocation_record import (
    ZERO_RUNTIME_EXECUTOR_INVOCATION_RECORD_SCHEMA,
    evaluate_executor_invocation_record,
    summarize_executor_invocation_record,
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
        "checkpoint_path": str(tmp_path / "record-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _gate(tmp_path: Path) -> dict[str, object]:
    launch = launch_goal_session("executor invocation record", _config(tmp_path))
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
    return evaluate_executor_invocation_gate(approval)


def test_valid_open_gate_creates_invocation_record_metadata_only(
    tmp_path: Path,
) -> None:
    gate = _gate(tmp_path)
    result = evaluate_executor_invocation_record(gate)

    assert result["schema"] == ZERO_RUNTIME_EXECUTOR_INVOCATION_RECORD_SCHEMA
    assert result["invocation_record_status"] == "recorded"
    assert result["executor_invocation_recorded"] is True
    assert result["executor_invoked"] is False
    assert result["execution_started"] is False
    assert result["runtime_mutated"] is False
    assert result["source_executor_invocation_gate_id"] == gate[
        "executor_invocation_gate_id"
    ]
    assert result["executor_invocation_gate_id"] == gate[
        "executor_invocation_gate_id"
    ]
    assert result["denial_reason"] == ""


def test_rejected_or_closed_gate_is_rejected(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    gate["invocation_gate_status"] = "rejected"
    gate["executor_invocation_gate_open"] = False

    result = evaluate_executor_invocation_record(gate)

    assert result["invocation_record_status"] == "rejected"
    assert result["executor_invocation_recorded"] is False
    assert result["denial_reason"] == "gate_not_opened"


def test_duplicate_record_is_rejected(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    first = evaluate_executor_invocation_record(gate)
    result = evaluate_executor_invocation_record(
        gate,
        existing_records=[first],
    )

    assert result["invocation_record_status"] == "rejected"
    assert result["executor_invocation_recorded"] is False
    assert result["denial_reason"] == "duplicate_invocation_record"
    assert result["executor_invoked"] is False


def test_invalid_lineage_is_rejected(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    gate["executor_invocation_approval_id"] = ""

    result = evaluate_executor_invocation_record(gate)

    assert result["invocation_record_status"] == "rejected"
    assert result["executor_invocation_recorded"] is False
    assert result["denial_reason"] == "invalid_lineage"


def test_lineage_is_preserved(tmp_path: Path) -> None:
    gate = _gate(tmp_path)
    result = evaluate_executor_invocation_record(gate)

    for field in (
        "goal_id",
        "session_id",
        "runtime_session_id",
        "queue_id",
        "queue_entry_id",
        "worker_id",
        "worker_claim_id",
        "cycle_id",
        "cycle_binding_id",
        "execution_request_id",
        "tick_id",
        "decision_id",
        "proposal_id",
        "authorization_id",
        "commit_id",
        "execution_admission_id",
        "execution_permit_id",
        "executor_envelope_id",
        "executor_adapter_binding_id",
        "executor_adapter_attachment_id",
        "executor_invocation_preparation_id",
        "executor_invocation_approval_id",
        "executor_invocation_gate_id",
    ):
        assert result[field] == gate[field]


def test_recording_does_not_invoke_executor_or_start_execution(tmp_path: Path) -> None:
    service = RuntimeOperatorService(_config(tmp_path))
    result = service.run_goal("operator invocation record")
    status = service.status()
    record = result["executor_invocation_record"]

    assert result["invocation_record_status"] == "recorded"
    assert result["executor_invocation_recorded"] is True
    assert result["executor_invoked"] is True
    assert result["execution_started"] is True
    assert result["execution_dry_run"] is True
    assert result["mutation_allowed"] is False
    assert record["executor_invocation_recorded"] is True
    assert record["executor_invoked"] is False
    assert record["execution_started"] is False
    assert record["runtime_mutated"] is False
    assert status["invocation_record_status"]["invocation_record_status"] == (
        "recorded"
    )
    assert status["invocation_record_status"][
        "executor_invocation_recorded"
    ] is True
    assert status["invocation_record_status"]["executor_invoked"] is False
    assert status["invocation_record_status"]["execution_started"] is False
    assert status["executor_invocation_dispatch_status"]["executor_invoked"] is True
    assert status["executor_invocation_dispatch_status"]["execution_started"] is False
    assert status["runtime_execution_session_start_status"]["execution_started"] is True
    assert status["runtime_execution_session_start_status"]["execution_dry_run"] is True
    assert status["runtime_execution_session_start_status"]["mutation_allowed"] is False


def test_summary_is_operator_visible_and_safe(tmp_path: Path) -> None:
    result = evaluate_executor_invocation_record(_gate(tmp_path))
    summary = summarize_executor_invocation_record(result)

    assert summary["invocation_record_status"] == "recorded"
    assert summary["executor_invocation_recorded"] is True
    assert summary["executor_invoked"] is False
    assert summary["execution_started"] is False
    assert summary["runtime_mutated"] is False
    assert summary["executor_invocation_record_id"]


def test_source_boundary_has_no_forbidden_execution_surfaces() -> None:
    source = Path("core/runtime/runtime_executor_invocation_record.py").read_text(
        encoding="utf-8"
    ).lower()
    forbidden = [
        "executor.invoke",
        "adapter.invoke",
        "subprocess",
        "step_executor",
        "stepexecutor",
        "task_runner",
        "taskrunner",
        "progress_memory",
        "scheduler.",
        "from scheduler",
        "import scheduler",
        ".run(",
        "exec(",
        "eval(",
        "open(",
        "write_text",
        "write_bytes",
        "shell",
        "repo_mutated = true",
        "runtime_mutated = true",
        "cursor_advanced = true",
    ]
    for token in forbidden:
        assert token not in source, f"forbidden token present: {token}"
