from __future__ import annotations

from core.runtime.runtime_loop_controller import (
    build_runtime_loop_controller_audit_projection,
    build_runtime_loop_controller_record,
    build_runtime_loop_controller_request,
    can_runtime_loop_controller_continue,
    expire_runtime_loop_controller,
    pause_runtime_loop_controller,
    revoke_runtime_loop_controller,
    stop_runtime_loop_controller,
    validate_runtime_loop_controller_request,
)


def _session_id():
    return "limited-runtime-session::birth-1209"


def _lease(status="granted"):
    return {
        "lease_id": "execution-lease::limited-runtime-session::birth-1209::lease-1217",
        "runtime_session_id": _session_id(),
        "lease_status": status,
    }


def _grant(status="granted"):
    return {
        "capability_grant_id": (
            "capability-grant::limited-runtime-session::birth-1209::"
            "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
            "capability-1225"
        ),
        "owner_session_id": _session_id(),
        "owner_lease_id": _lease()["lease_id"],
        "grant_status": status,
    }


def _binding(status="bound"):
    return {
        "executor_binding_id": "executor-binding::executor-zero::binding-1233",
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease()["lease_id"],
        "capability_grant_id": _grant()["capability_grant_id"],
        "executor_id": "executor-zero",
        "executor_type": "runtime_task_executor",
        "binding_status": status,
    }


def _tick_decision():
    return {
        "loop_controller_mode": "execution_tick_record_only",
        "single_cycle_only": True,
        "continuation_allowed": False,
        "executor_run_allowed": False,
        "task_execution_allowed": False,
        "tool_invocation_allowed": False,
        "subprocess_allowed": False,
        "shell_allowed": False,
        "network_allowed": False,
        "filesystem_mutation_allowed": False,
        "state_mutation_allowed": False,
        "task_completion_allowed": False,
        "autonomy_loop_allowed": False,
        "self_start_allowed": False,
        "background_worker_allowed": False,
    }


def _tick(status="ticked"):
    ready = status == "ticked"
    return {
        "execution_tick_id": "runtime-execution-tick::limited-runtime-session::birth-1209::tick-1345",
        "executor_invocation_id": "executor-invocation-boundary::limited-runtime-session::birth-1209::invocation-1337",
        "dispatch_commit_id": "task-dispatch-commit::dispatch-1329",
        "dispatch_id": "task-dispatch::prepared-1321",
        "task_admission_id": "task-admission::limited-runtime-session::birth-1209::task-001::abcd",
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease()["lease_id"],
        "capability_grant_id": _grant()["capability_grant_id"],
        "executor_binding_id": _binding()["executor_binding_id"],
        "tick_status": status,
        "tick_ready": ready,
        "record_only": True,
        "single_cycle_only": True,
        "continuation_allowed": False,
        "tick_decision": _tick_decision(),
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
    }


def _request(**overrides):
    request = build_runtime_loop_controller_request(
        loop_controller_request_id="runtime-loop-controller-1353",
        execution_tick=_tick(),
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        loop_authorization=True,
        loop_time="deterministic-time::1353",
    )
    request.update(overrides)
    return request


def test_1353_ticked_execution_cycle_creates_loop_controller_record():
    record = build_runtime_loop_controller_record(_request())

    assert record["loop_controller_id"].startswith("runtime-loop-controller::")
    assert record["execution_tick_id"] == _tick()["execution_tick_id"]
    assert record["loop_status"] == "controlled"
    assert record["loop_ready"] is True
    assert record["record_only"] is True


def test_1354_missing_execution_tick_blocks_loop_control():
    validation = validate_runtime_loop_controller_request(_request(execution_tick={}))

    assert validation["loop_status"] == "denied"
    assert "missing_execution_tick" in validation["problems"]


def test_1354_denied_execution_tick_blocks_loop_control():
    validation = validate_runtime_loop_controller_request(
        _request(execution_tick=_tick(status="denied"))
    )

    assert validation["loop_status"] == "denied"
    assert "denied_execution_tick" in validation["problems"]


def test_1355_expired_lease_blocks_loop_control():
    validation = validate_runtime_loop_controller_request(
        _request(execution_lease=_lease(status="expired"))
    )

    assert validation["loop_status"] == "denied"
    assert "expired_execution_lease" in validation["problems"]


def test_1355_revoked_capability_blocks_loop_control():
    validation = validate_runtime_loop_controller_request(
        _request(capability_grant=_grant(status="revoked"))
    )

    assert validation["loop_status"] == "denied"
    assert "revoked_capability_grant" in validation["problems"]


def test_1356_missing_authorization_blocks_loop_control():
    validation = validate_runtime_loop_controller_request(_request(loop_authorization=False))

    assert validation["loop_status"] == "denied"
    assert "loop_not_authorized" in validation["problems"]


def test_1356_unlocked_tick_decision_blocks_loop_control():
    tick = _tick()
    tick["tick_decision"]["autonomy_loop_allowed"] = True
    validation = validate_runtime_loop_controller_request(_request(execution_tick=tick))

    assert validation["loop_status"] == "denied"
    assert "execution_tick_decision_unlocked" in validation["problems"]


def test_1357_loop_controller_can_request_but_not_start_next_tick():
    record = build_runtime_loop_controller_record(_request())
    continuation = can_runtime_loop_controller_continue(record)

    assert continuation["can_request_next_tick"] is True
    assert continuation["can_continue"] is False
    assert record["automatic_next_tick_allowed"] is False
    assert record["next_tick_started"] is False


def test_1358_loop_controller_does_not_run_executor_or_task():
    record = build_runtime_loop_controller_record(_request())
    continuation = can_runtime_loop_controller_continue(record)

    assert record["executor_run_performed"] is False
    assert record["task_execution_performed"] is False
    assert continuation["can_run_executor"] is False
    assert continuation["can_execute_task"] is False


def test_1358_loop_controller_cannot_invoke_tools_or_mutate():
    record = build_runtime_loop_controller_record(_request())

    assert record["tool_invoked"] is False
    assert record["filesystem_mutation_performed"] is False
    assert record["state_mutation_performed"] is False
    assert record["loop_decision"]["tool_invocation_allowed"] is False
    assert record["loop_decision"]["state_mutation_allowed"] is False


def test_1359_loop_controller_cannot_start_autonomy_or_background_worker():
    record = build_runtime_loop_controller_record(_request())
    continuation = can_runtime_loop_controller_continue(record)

    assert record["autonomy_loop_started"] is False
    assert record["self_start_performed"] is False
    assert record["background_worker_started"] is False
    assert continuation["can_start_background_loop"] is False
    assert continuation["can_self_start"] is False


def test_1359_pause_stop_expire_revoke_block_continuation():
    base = build_runtime_loop_controller_record(_request())
    paused = pause_runtime_loop_controller(base)
    stopped = stop_runtime_loop_controller(base)
    expired = expire_runtime_loop_controller(base)
    revoked = revoke_runtime_loop_controller(base)

    assert paused["loop_status"] == "paused"
    assert stopped["loop_status"] == "stopped"
    assert expired["loop_status"] == "expired"
    assert revoked["loop_status"] == "revoked"
    assert can_runtime_loop_controller_continue(paused)["can_request_next_tick"] is False
    assert can_runtime_loop_controller_continue(stopped)["can_request_next_tick"] is False
    assert can_runtime_loop_controller_continue(expired)["can_request_next_tick"] is False
    assert can_runtime_loop_controller_continue(revoked)["can_request_next_tick"] is False


def test_1360_audit_projection_is_deterministic():
    first = build_runtime_loop_controller_audit_projection(
        build_runtime_loop_controller_record(_request())
    )
    second = build_runtime_loop_controller_audit_projection(
        build_runtime_loop_controller_record(_request())
    )

    assert first == second
    assert first["projection_only"] is True
    assert first["controlled_record_only"] is True
    assert first["executor_run_performed"] is False
