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
from core.runtime.runtime_controlled_real_executor_unlock import (
    ZERO_RUNTIME_CONTROLLED_REAL_EXECUTOR_UNLOCK_SCHEMA,
    unlock_controlled_real_executor,
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
from core.runtime.runtime_executor_runtime_closure import close_executor_runtime_dry_run
from core.runtime.runtime_goal_queue_admission import submit_goal_session_to_queue
from core.runtime.runtime_goal_session_launcher import launch_goal_session
from core.runtime.runtime_operator_service import RuntimeOperatorService
from core.runtime.runtime_queue_worker_pickup import (
    submit_queue_entry_for_worker_pickup,
)


class FakeSafeNoMutationAdapter:
    safe_no_mutation_adapter = True

    def __init__(self) -> None:
        self.requests = []

    def execute_controlled_no_mutation(self, request):
        self.requests.append(request)
        return {
            "adapter_status": "completed",
            "mutation_allowed": False,
            "repo_mutation_enabled": False,
            "output_summary": {"summary": "fake_controlled_execution_complete"},
            "error_summary": {},
            "non_mainline_issues": [],
        }


def _config(tmp_path: Path, **overrides):
    data = {
        "runtime_mode": "autonomous",
        "max_tick_limit": 3,
        "checkpoint_path": str(tmp_path / "controlled-real-executor-checkpoint.json"),
        "auto_resume_enabled": False,
        "emergency_stop_enabled": True,
    }
    data.update(overrides)
    return data


def _closure(tmp_path: Path) -> dict[str, object]:
    launch = launch_goal_session("controlled real executor unlock", _config(tmp_path))
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
    capture = capture_runtime_execution_result_dry_run(session)
    return close_executor_runtime_dry_run(capture)


def test_unlock_consumes_runtime_executor_runtime_closure_result(
    tmp_path: Path,
) -> None:
    closure = _closure(tmp_path)
    result = unlock_controlled_real_executor(
        closure,
        runtime_operator_service_authorized=True,
    )

    assert result["schema"] == ZERO_RUNTIME_CONTROLLED_REAL_EXECUTOR_UNLOCK_SCHEMA
    assert result["closure_id"] == closure["closure_id"]
    assert result["execution_result_id"] == closure["execution_result_id"]
    assert result["real_executor_ready"] is True
    assert result["controlled_real_executor_unlock_status"] == (
        "blocked_no_safe_executor_adapter"
    )


def test_cannot_unlock_before_closure() -> None:
    result = unlock_controlled_real_executor(
        None,
        runtime_operator_service_authorized=True,
    )

    assert result["controlled_real_executor_unlock_status"] == "rejected"
    assert result["unlock_reason"] == "missing_closure_result"
    assert result["real_executor_enabled"] is False
    assert result["execution_real"] is False


def test_cannot_unlock_if_mutation_allowed(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    closure["mutation_allowed"] = True

    result = unlock_controlled_real_executor(
        closure,
        runtime_operator_service_authorized=True,
    )

    assert result["controlled_real_executor_unlock_status"] == "rejected"
    assert result["unlock_reason"] == "mutation_not_allowed"
    assert result["mutation_allowed"] is False
    assert result["repo_mutation_enabled"] is False


def test_no_repo_mutation_and_no_direct_process_surface() -> None:
    files = [
        Path("core/runtime/runtime_controlled_real_executor_unlock.py"),
        Path("core/runtime/runtime_operator_service.py"),
    ]
    forbidden = [
        "popen",
        "system(",
        "run_shell",
        "exec(",
        "eval(",
        "write_text",
        "write_bytes",
        "repo_mutation_enabled=True",
        "mutation_allowed=True",
    ]
    for file in files:
        source = file.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"forbidden token present: {token}"


def test_no_bypass_of_runtime_operator_service(tmp_path: Path) -> None:
    closure = _closure(tmp_path)
    adapter = FakeSafeNoMutationAdapter()

    result = unlock_controlled_real_executor(closure, safe_executor_adapter=adapter)

    assert result["controlled_real_executor_unlock_status"] == "rejected"
    assert result["unlock_reason"] == "runtime_operator_service_required"
    assert result["real_executor_enabled"] is False
    assert result["execution_real"] is False
    assert adapter.requests == []


def test_deterministic_blocked_result_if_no_safe_adapter_exists(
    tmp_path: Path,
) -> None:
    closure = _closure(tmp_path)
    first = unlock_controlled_real_executor(
        closure,
        runtime_operator_service_authorized=True,
    )
    second = unlock_controlled_real_executor(
        closure,
        runtime_operator_service_authorized=True,
    )

    assert first == second
    assert first["controlled_real_executor_unlock_status"] == (
        "blocked_no_safe_executor_adapter"
    )
    assert first["real_executor_enabled"] is False
    assert first["execution_real"] is False
    assert first["mutation_allowed"] is False


def test_deterministic_success_if_fake_safe_adapter_is_injected(
    tmp_path: Path,
) -> None:
    adapter = FakeSafeNoMutationAdapter()
    service = RuntimeOperatorService(
        _config(tmp_path),
        controlled_real_executor_adapter=adapter,
    )

    first = service.run_goal("fake safe controlled real executor")
    status = service.status()
    result = first["controlled_real_executor_result"]

    assert first["real_executor_ready"] is True
    assert first["real_executor_enabled"] is True
    assert first["execution_real"] is True
    assert first["mutation_allowed"] is False
    assert first["repo_mutation_enabled"] is False
    assert first["controlled_real_executor_unlock_status"] == (
        "controlled_real_executor_unlocked"
    )
    assert result["adapter_result"]["adapter_completed"] is True
    assert result["adapter_request"]["real_executor_enabled"] is True
    assert result["adapter_request"]["mutation_allowed"] is False
    assert status["controlled_real_executor_unlock_status"][
        "controlled_real_executor_unlock_status"
    ] == "controlled_real_executor_unlocked"
    assert status["controlled_real_executor_unlock_status"][
        "real_executor_enabled"
    ] is True
    assert adapter.requests


def test_real_and_execution_flags_only_on_adapter_success(tmp_path: Path) -> None:
    blocked_service = RuntimeOperatorService(_config(tmp_path))
    blocked = blocked_service.run_goal("blocked controlled real executor")

    assert blocked["real_executor_ready"] is True
    assert blocked["real_executor_enabled"] is False
    assert blocked["execution_real"] is False
    assert blocked["controlled_real_executor_unlock_status"] == (
        "blocked_no_safe_executor_adapter"
    )

    success_service = RuntimeOperatorService(
        _config(tmp_path),
        controlled_real_executor_adapter=FakeSafeNoMutationAdapter(),
    )
    success = success_service.run_goal("successful controlled real executor")

    assert success["real_executor_enabled"] is True
    assert success["execution_real"] is True
    assert success["mutation_allowed"] is False
    assert success["repo_mutation_enabled"] is False


def test_full_chain_remains_deterministic_with_fake_adapter(tmp_path: Path) -> None:
    first_service = RuntimeOperatorService(
        _config(tmp_path),
        controlled_real_executor_adapter=FakeSafeNoMutationAdapter(),
    )
    second_service = RuntimeOperatorService(
        _config(tmp_path),
        controlled_real_executor_adapter=FakeSafeNoMutationAdapter(),
    )

    first = first_service.run_goal("deterministic controlled real executor")
    second = second_service.run_goal("deterministic controlled real executor")

    assert first["controlled_real_executor_result"] == second[
        "controlled_real_executor_result"
    ]
    assert first["real_executor_ready"] is True
    assert first["real_executor_enabled"] is True
    assert first["execution_real"] is True
    assert first["mutation_allowed"] is False
