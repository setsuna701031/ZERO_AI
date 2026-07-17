from __future__ import annotations

from core.runtime.runtime_work_cycle_coordinator import (
    build_runtime_work_cycle_audit_projection,
    build_runtime_work_cycle_record,
    build_runtime_work_cycle_request,
    can_runtime_work_cycle_act,
    validate_runtime_work_cycle_request,
)


def _session_id():
    return "limited-runtime-session::birth-1209"


def _lease_id():
    return "execution-lease::limited-runtime-session::birth-1209::lease-1217"


def _grant_id():
    return (
        "capability-grant::limited-runtime-session::birth-1209::"
        "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
        "capability-1225"
    )


def _binding_id():
    return "executor-binding::executor-zero::binding-1233"


def _task_admission_id():
    return "task-admission::limited-runtime-session::birth-1209::task-001::abcd"


def _dispatch_commit_id():
    return "task-dispatch-commit::dispatch-1329"


def _dispatch_id():
    return "task-dispatch::prepared-1321"


def _invocation_id():
    return (
        "executor-invocation-boundary::limited-runtime-session::birth-1209::"
        "invocation-1337"
    )


def _tick_id():
    return "runtime-execution-tick::limited-runtime-session::birth-1209::tick-1345"


def _loop_id():
    return "runtime-loop-controller::limited-runtime-session::birth-1209::loop-1353"


def _common_chain():
    return {
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease_id(),
        "capability_grant_id": _grant_id(),
        "executor_binding_id": _binding_id(),
        "task_admission_id": _task_admission_id(),
        "dispatch_commit_id": _dispatch_commit_id(),
        "dispatch_id": _dispatch_id(),
    }


def _dispatch_commit(status="committed"):
    ready = status == "committed"
    return {
        **_common_chain(),
        "dispatch_commit_id": _dispatch_commit_id(),
        "commit_status": status,
        "dispatch_ready": ready,
        "record_only": True,
        "executor_run_performed": False,
        "tool_invoked": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
    }


def _boundary(status="bounded"):
    ready = status == "bounded"
    return {
        **_common_chain(),
        "executor_invocation_id": _invocation_id(),
        "invocation_status": status,
        "boundary_ready": ready,
        "record_only": True,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
    }


def _tick(status="ticked"):
    ready = status == "ticked"
    return {
        **_common_chain(),
        "execution_tick_id": _tick_id(),
        "executor_invocation_id": _invocation_id(),
        "tick_status": status,
        "tick_ready": ready,
        "record_only": True,
        "single_cycle_only": True,
        "continuation_allowed": False,
        "tick_decision": {
            "single_cycle_only": True,
            "continuation_allowed": False,
            "executor_run_allowed": False,
            "task_execution_allowed": False,
            "tool_invocation_allowed": False,
            "state_mutation_allowed": False,
            "autonomy_loop_allowed": False,
            "background_worker_allowed": False,
        },
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
    }


def _loop(status="controlled"):
    ready = status == "controlled"
    return {
        **_common_chain(),
        "loop_controller_id": _loop_id(),
        "execution_tick_id": _tick_id(),
        "executor_invocation_id": _invocation_id(),
        "loop_status": status,
        "loop_ready": ready,
        "record_only": True,
        "loop_decision": {
            "controlled": ready,
            "next_tick_may_be_requested": ready,
            "automatic_next_tick_allowed": False,
            "executor_run_allowed": False,
            "task_execution_allowed": False,
            "tool_invocation_allowed": False,
            "state_mutation_allowed": False,
            "autonomy_loop_allowed": False,
            "background_worker_allowed": False,
        },
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
    }


def _request(**overrides):
    request = build_runtime_work_cycle_request(
        work_cycle_request_id="runtime-work-cycle-1361",
        runtime_session_id=_session_id(),
        execution_lease_id=_lease_id(),
        capability_grant_id=_grant_id(),
        executor_binding_id=_binding_id(),
        loop_controller=_loop(),
        execution_tick=_tick(),
        task_admission_id=_task_admission_id(),
        dispatch_commit=_dispatch_commit(),
        executor_invocation_boundary=_boundary(),
        cycle_time="deterministic-time::1361",
    )
    request.update(overrides)
    return request


def test_1361_no_loop_controller_blocks_cycle():
    validation = validate_runtime_work_cycle_request(_request(loop_controller={}))

    assert validation["cycle_status"] == "blocked"
    assert validation["cycle_decision"] == "wait"
    assert "missing_loop_controller" in validation["problems"]


def test_1361_no_execution_tick_blocks_cycle():
    validation = validate_runtime_work_cycle_request(_request(execution_tick={}))

    assert validation["cycle_status"] == "blocked"
    assert validation["cycle_decision"] == "wait"
    assert "missing_execution_tick" in validation["problems"]


def test_1362_no_dispatch_commit_blocks_cycle():
    validation = validate_runtime_work_cycle_request(_request(dispatch_commit={}))

    assert validation["cycle_status"] == "blocked"
    assert validation["cycle_decision"] == "wait"
    assert "missing_dispatch_commit" in validation["problems"]


def test_1362_no_executor_invocation_boundary_blocks_cycle():
    validation = validate_runtime_work_cycle_request(
        _request(executor_invocation_boundary={})
    )

    assert validation["cycle_status"] == "blocked"
    assert validation["cycle_decision"] == "wait"
    assert "missing_executor_invocation_boundary" in validation["problems"]


def test_1363_valid_chain_creates_coordinated_cycle():
    record = build_runtime_work_cycle_record(_request())

    assert record["work_cycle_id"].startswith("runtime-work-cycle::")
    assert record["cycle_status"] == "coordinated"
    assert record["cycle_decision"] == "continue"
    assert record["next_action"] == "return_controlled_cycle_decision"
    assert record["record_only"] is True


def test_1364_denied_upstream_produces_denied_cycle():
    record = build_runtime_work_cycle_record(_request(loop_controller=_loop("denied")))

    assert record["cycle_status"] == "denied"
    assert record["cycle_decision"] == "deny"
    assert "denied_loop_controller" in record["denial_reason"]


def test_1364_expired_or_revoked_upstream_blocks_cycle():
    expired = build_runtime_work_cycle_record(_request(execution_tick=_tick("expired")))
    revoked = build_runtime_work_cycle_record(
        _request(dispatch_commit=_dispatch_commit("revoked"))
    )

    assert expired["cycle_status"] == "blocked"
    assert expired["cycle_decision"] == "wait"
    assert revoked["cycle_status"] == "blocked"
    assert revoked["cycle_decision"] == "wait"


def test_1365_stale_tick_blocks_cycle():
    tick = _tick()
    tick["tick_stale"] = True
    record = build_runtime_work_cycle_record(_request(execution_tick=tick))

    assert record["cycle_status"] == "blocked"
    assert record["cycle_decision"] == "wait"
    assert "stale_execution_tick" in record["denial_reason"]


def test_1365_recovery_required_upstream_produces_recovery_required_cycle():
    tick = _tick()
    tick["recovery_required"] = True
    record = build_runtime_work_cycle_record(_request(execution_tick=tick))

    assert record["cycle_status"] == "recovery_required"
    assert record["cycle_decision"] == "recover"
    assert record["recovery_required"] is True
    assert record["next_action"] == "enter_recovery_coordination"


def test_1366_stop_upstream_produces_stopped_cycle():
    record = build_runtime_work_cycle_record(_request(loop_controller=_loop("stopped")))

    assert record["cycle_status"] == "stopped"
    assert record["cycle_decision"] == "stop"
    assert record["stop_reason"] == "upstream_stop"


def test_1366_coordinated_cycle_does_not_execute_task():
    record = build_runtime_work_cycle_record(_request())
    action = can_runtime_work_cycle_act(record)

    assert record["task_execution_performed"] is False
    assert record["task_completed"] is False
    assert action["can_execute_task"] is False


def test_1367_coordinated_cycle_does_not_invoke_tools():
    record = build_runtime_work_cycle_record(_request())
    action = can_runtime_work_cycle_act(record)

    assert record["tool_invoked"] is False
    assert record["decision_record"]["tool_invocation_allowed"] is False
    assert action["can_invoke_tools"] is False


def test_1367_coordinated_cycle_does_not_mutate_filesystem():
    record = build_runtime_work_cycle_record(_request())
    action = can_runtime_work_cycle_act(record)

    assert record["filesystem_mutation_performed"] is False
    assert record["state_mutation_performed"] is False
    assert record["decision_record"]["filesystem_mutation_allowed"] is False
    assert action["can_mutate_filesystem"] is False


def test_1368_audit_projection_deterministic():
    first = build_runtime_work_cycle_audit_projection(
        build_runtime_work_cycle_record(_request())
    )
    second = build_runtime_work_cycle_audit_projection(
        build_runtime_work_cycle_record(_request())
    )

    assert first == second
    assert first["projection_only"] is True
    assert first["coordinated_record_only"] is True
    assert first["executor_run_performed"] is False
    assert first["filesystem_mutation_performed"] is False
