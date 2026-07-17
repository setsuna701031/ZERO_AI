from __future__ import annotations

from core.runtime.runtime_execution_tick import (
    build_runtime_execution_tick_audit_projection,
    build_runtime_execution_tick_record,
    build_runtime_execution_tick_request,
    can_runtime_execution_tick_continue,
    expire_runtime_execution_tick,
    revoke_runtime_execution_tick,
    validate_runtime_execution_tick_request,
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


def _executor_target():
    return {
        "executor_binding_id": _binding()["executor_binding_id"],
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease()["lease_id"],
        "capability_grant_id": _grant()["capability_grant_id"],
        "executor_id": "executor-zero",
        "executor_type": "runtime_task_executor",
        "target_mode": "record_only",
    }


def _invocation_envelope():
    return {
        "envelope_type": "executor_invocation_boundary_record_only",
        "runtime_session_id": _session_id(),
        "dispatch_commit_id": "task-dispatch-commit::dispatch-1329",
        "dispatch_id": "task-dispatch::prepared-1321",
        "task_admission_id": "task-admission::limited-runtime-session::birth-1209::task-001::abcd",
        "executor_binding_id": _binding()["executor_binding_id"],
        "executor_id": "executor-zero",
        "executor_type": "runtime_task_executor",
        "target_mode": "record_only",
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
        "background_worker_allowed": False,
    }


def _boundary(status="bounded"):
    ready = status == "bounded"
    return {
        "executor_invocation_id": "executor-invocation-boundary::limited-runtime-session::birth-1209::invocation-1337",
        "dispatch_commit_id": "task-dispatch-commit::dispatch-1329",
        "dispatch_id": "task-dispatch::prepared-1321",
        "task_admission_id": "task-admission::limited-runtime-session::birth-1209::task-001::abcd",
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease()["lease_id"],
        "capability_grant_id": _grant()["capability_grant_id"],
        "executor_binding_id": _binding()["executor_binding_id"],
        "executor_target": _executor_target(),
        "invocation_envelope": _invocation_envelope(),
        "invocation_status": status,
        "boundary_ready": ready,
        "record_only": True,
        "executor_run_performed": False,
        "task_execution_performed": False,
        "tool_invoked": False,
        "state_mutation_performed": False,
        "task_completed": False,
    }


def _request(**overrides):
    request = build_runtime_execution_tick_request(
        execution_tick_request_id="execution-tick-1345",
        executor_invocation_boundary=_boundary(),
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        tick_authorization=True,
        tick_time="deterministic-time::1345",
    )
    request.update(overrides)
    return request


def test_1345_bounded_executor_invocation_creates_tick_record():
    record = build_runtime_execution_tick_record(_request())

    assert record["execution_tick_id"].startswith("runtime-execution-tick::")
    assert record["executor_invocation_id"] == _boundary()["executor_invocation_id"]
    assert record["tick_status"] == "ticked"
    assert record["tick_ready"] is True
    assert record["record_only"] is True


def test_1346_missing_boundary_blocks_tick():
    validation = validate_runtime_execution_tick_request(
        _request(executor_invocation_boundary={})
    )

    assert validation["tick_status"] == "denied"
    assert "missing_executor_invocation_boundary" in validation["problems"]


def test_1346_denied_boundary_blocks_tick():
    validation = validate_runtime_execution_tick_request(
        _request(executor_invocation_boundary=_boundary(status="denied"))
    )

    assert validation["tick_status"] == "denied"
    assert "denied_executor_invocation_boundary" in validation["problems"]


def test_1347_expired_lease_blocks_tick():
    validation = validate_runtime_execution_tick_request(
        _request(execution_lease=_lease(status="expired"))
    )

    assert validation["tick_status"] == "denied"
    assert "expired_execution_lease" in validation["problems"]


def test_1348_revoked_capability_blocks_tick():
    validation = validate_runtime_execution_tick_request(
        _request(capability_grant=_grant(status="revoked"))
    )

    assert validation["tick_status"] == "denied"
    assert "revoked_capability_grant" in validation["problems"]


def test_1349_missing_authorization_blocks_tick():
    validation = validate_runtime_execution_tick_request(
        _request(tick_authorization=False)
    )

    assert validation["tick_status"] == "denied"
    assert "tick_not_authorized" in validation["problems"]


def test_1350_tick_decision_is_single_cycle_only():
    record = build_runtime_execution_tick_record(_request())
    decision = record["tick_decision"]

    assert decision["single_cycle_only"] is True
    assert decision["continuation_allowed"] is False
    assert record["single_cycle_only"] is True
    assert record["continuation_allowed"] is False


def test_1350_tick_does_not_run_executor_or_task():
    record = build_runtime_execution_tick_record(_request())
    continuation = can_runtime_execution_tick_continue(record)

    assert record["executor_run_performed"] is False
    assert record["task_execution_performed"] is False
    assert continuation["can_run_executor"] is False
    assert continuation["can_execute_task"] is False


def test_1351_tick_cannot_invoke_tools_or_mutate():
    record = build_runtime_execution_tick_record(_request())

    assert record["tool_invoked"] is False
    assert record["filesystem_mutation_performed"] is False
    assert record["state_mutation_performed"] is False
    assert record["tick_decision"]["tool_invocation_allowed"] is False
    assert record["tick_decision"]["state_mutation_allowed"] is False


def test_1351_tick_cannot_start_autonomy_or_background_worker():
    record = build_runtime_execution_tick_record(_request())

    assert record["autonomy_loop_started"] is False
    assert record["self_start_performed"] is False
    assert record["background_worker_started"] is False
    assert record["tick_decision"]["autonomy_loop_allowed"] is False
    assert record["tick_decision"]["background_worker_allowed"] is False


def test_1352_expired_or_revoked_tick_cannot_continue():
    expired = expire_runtime_execution_tick(build_runtime_execution_tick_record(_request()))
    revoked = revoke_runtime_execution_tick(build_runtime_execution_tick_record(_request()))

    assert expired["tick_status"] == "expired"
    assert revoked["tick_status"] == "revoked"
    assert can_runtime_execution_tick_continue(expired)["can_continue"] is False
    assert can_runtime_execution_tick_continue(revoked)["can_continue"] is False


def test_1352_audit_projection_is_deterministic():
    first = build_runtime_execution_tick_audit_projection(
        build_runtime_execution_tick_record(_request())
    )
    second = build_runtime_execution_tick_audit_projection(
        build_runtime_execution_tick_record(_request())
    )

    assert first == second
    assert first["projection_only"] is True
    assert first["ticked_record_only"] is True
    assert first["executor_run_performed"] is False
