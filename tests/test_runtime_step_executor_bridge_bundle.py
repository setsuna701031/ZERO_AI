from __future__ import annotations

from core.runtime.runtime_step_executor_bridge import (
    build_runtime_step_executor_bridge_audit_projection,
    build_runtime_step_executor_bridge_record,
    build_runtime_step_executor_bridge_request,
    can_runtime_step_executor_bridge_execute,
    validate_runtime_step_executor_bridge_request,
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


def _loop_id():
    return "runtime-loop-controller::limited-runtime-session::birth-1209::loop-1353"


def _tick_id():
    return "runtime-execution-tick::limited-runtime-session::birth-1209::tick-1345"


def _work_cycle_id():
    return (
        "runtime-work-cycle::limited-runtime-session::birth-1209::"
        "runtime-loop-controller::limited-runtime-session::birth-1209::loop-1353::abcd"
    )


def _work_cycle(status="coordinated", decision="continue"):
    return {
        "work_cycle_id": _work_cycle_id(),
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease_id(),
        "capability_grant_id": _grant_id(),
        "executor_binding_id": _binding_id(),
        "loop_controller_id": _loop_id(),
        "execution_tick_id": _tick_id(),
        "cycle_status": status,
        "cycle_decision": decision,
        "recovery_required": status == "recovery_required",
        "record_only": True,
        "coordination_only": True,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "filesystem_mutation_performed": False,
        "state_mutation_performed": False,
        "task_completed": False,
        "autonomy_loop_started": False,
        "background_worker_started": False,
    }


def _request(**overrides):
    request = build_runtime_step_executor_bridge_request(
        step_bridge_request_id="runtime-step-bridge-1369",
        runtime_session_id=_session_id(),
        execution_lease_id=_lease_id(),
        capability_grant_id=_grant_id(),
        executor_binding_id=_binding_id(),
        loop_controller_id=_loop_id(),
        execution_tick_id=_tick_id(),
        work_cycle=_work_cycle(),
        step_request_type="noop_step",
        bridge_time="deterministic-time::1369",
    )
    request.update(overrides)
    return request


def test_1369_no_work_cycle_blocks_bridge():
    validation = validate_runtime_step_executor_bridge_request(_request(work_cycle={}))

    assert validation["bridge_status"] == "blocked"
    assert "missing_work_cycle" in validation["problems"]


def test_1370_stopped_cycle_blocks_bridge():
    record = build_runtime_step_executor_bridge_record(
        _request(work_cycle=_work_cycle("stopped", "stop"))
    )

    assert record["bridge_status"] == "blocked"
    assert record["next_step_intent"] == "stop_before_step_executor_bridge"
    assert "stopped_work_cycle" in record["denial_reason"]


def test_1370_denied_cycle_blocks_bridge():
    record = build_runtime_step_executor_bridge_record(
        _request(work_cycle=_work_cycle("denied", "deny"))
    )

    assert record["bridge_status"] == "denied"
    assert record["next_step_intent"] == "deny_step_executor_bridge"
    assert "denied_work_cycle" in record["denial_reason"]


def test_1371_recovery_required_cycle_blocks_bridge():
    record = build_runtime_step_executor_bridge_record(
        _request(work_cycle=_work_cycle("recovery_required", "recover"))
    )

    assert record["bridge_status"] == "blocked"
    assert record["next_step_intent"] == "route_to_recovery_step_bridge"
    assert "recovery_required_work_cycle" in record["denial_reason"]


def test_1372_coordinated_continue_cycle_creates_bridge_record():
    record = build_runtime_step_executor_bridge_record(_request())

    assert record["step_bridge_id"].startswith("runtime-step-bridge::")
    assert record["work_cycle_id"] == _work_cycle_id()
    assert record["bridge_status"] == "bridged"
    assert record["step_request_type"] == "noop_step"
    assert record["record_only"] is True


def test_1373_expired_or_revoked_upstream_blocks_bridge():
    expired_cycle = _work_cycle()
    expired_cycle["upstream_statuses"] = {"execution_tick": "expired"}
    revoked_cycle = _work_cycle()
    revoked_cycle["upstream_statuses"] = {"executor_binding": "revoked"}

    expired = build_runtime_step_executor_bridge_record(_request(work_cycle=expired_cycle))
    revoked = build_runtime_step_executor_bridge_record(_request(work_cycle=revoked_cycle))

    assert expired["bridge_status"] == "blocked"
    assert "expired_execution_tick" in expired["denial_reason"]
    assert revoked["bridge_status"] == "blocked"
    assert "revoked_executor_binding" in revoked["denial_reason"]


def test_1373_bridge_contains_deterministic_step_request_id():
    first = build_runtime_step_executor_bridge_record(_request())
    second = build_runtime_step_executor_bridge_record(_request())

    assert first["step_request_id"] == second["step_request_id"]
    assert first["step_request_id"].startswith("runtime-step-request::")
    assert first["step_request"]["step_request_id"] == first["step_request_id"]


def test_1374_bridge_does_not_execute_step():
    record = build_runtime_step_executor_bridge_record(_request())
    execution = can_runtime_step_executor_bridge_execute(record)

    assert record["step_executed"] is False
    assert record["step_request"]["step_execution_allowed"] is False
    assert execution["can_execute_step"] is False
    assert execution["can_run_executor"] is False


def test_1374_bridge_does_not_invoke_tools():
    record = build_runtime_step_executor_bridge_record(_request())
    execution = can_runtime_step_executor_bridge_execute(record)

    assert record["tool_invoked"] is False
    assert record["step_request"]["tool_invocation_allowed"] is False
    assert execution["can_invoke_tools"] is False


def test_1375_bridge_does_not_mutate_filesystem():
    record = build_runtime_step_executor_bridge_record(_request())
    execution = can_runtime_step_executor_bridge_execute(record)

    assert record["filesystem_mutation_performed"] is False
    assert record["filesystem_write_performed"] is False
    assert record["step_request"]["filesystem_mutation_allowed"] is False
    assert execution["can_mutate_filesystem"] is False


def test_1375_bridge_does_not_complete_task():
    record = build_runtime_step_executor_bridge_record(_request())
    execution = can_runtime_step_executor_bridge_execute(record)

    assert record["task_completed"] is False
    assert record["step_request"]["task_completion_allowed"] is False
    assert execution["can_complete_task"] is False


def test_1376_audit_projection_deterministic():
    first = build_runtime_step_executor_bridge_audit_projection(
        build_runtime_step_executor_bridge_record(_request())
    )
    second = build_runtime_step_executor_bridge_audit_projection(
        build_runtime_step_executor_bridge_record(_request())
    )

    assert first == second
    assert first["projection_only"] is True
    assert first["bridged_record_only"] is True
    assert first["step_executed"] is False
    assert first["filesystem_mutation_performed"] is False
