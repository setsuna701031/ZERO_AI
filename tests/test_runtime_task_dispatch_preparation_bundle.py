from __future__ import annotations

from core.runtime.runtime_task_dispatch_preparation import (
    build_runtime_task_dispatch_preparation_audit_projection,
    build_runtime_task_dispatch_preparation_record,
    build_runtime_task_dispatch_preparation_request,
    can_runtime_dispatch_execute,
    validate_runtime_task_dispatch_preparation_request,
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


def _admission(status="admitted"):
    return {
        "task_admission_id": "task-admission::limited-runtime-session::birth-1209::task-001::abcd",
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease()["lease_id"],
        "capability_grant_id": _grant()["capability_grant_id"],
        "executor_binding_id": _binding()["executor_binding_id"],
        "requested_task_id": "task-001",
        "requested_task_type": "read_task",
        "admission_status": status,
        "denial_reason": "none" if status == "admitted" else "denied_for_test",
    }


def _request(**overrides):
    request = build_runtime_task_dispatch_preparation_request(
        dispatch_preparation_request_id="dispatch-preparation-1321",
        task_admission=_admission(),
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        preparation_time="deterministic-time::1321",
    )
    request.update(overrides)
    return request


def test_1321_valid_admitted_task_creates_dispatch_preparation():
    record = build_runtime_task_dispatch_preparation_record(_request())

    assert record["dispatch_id"].startswith("task-dispatch::")
    assert record["task_admission_id"] == _admission()["task_admission_id"]
    assert record["dispatch_status"] == "prepared"
    assert record["denial_reason"] == "none"
    assert record["record_only"] is True


def test_1322_denied_admission_blocks_preparation():
    record = build_runtime_task_dispatch_preparation_record(
        _request(task_admission=_admission(status="denied"))
    )

    assert record["dispatch_status"] == "denied"
    assert "denied_admission" in record["denial_reason"]


def test_1323_expired_lease_blocks_preparation():
    validation = validate_runtime_task_dispatch_preparation_request(
        _request(execution_lease=_lease(status="expired"))
    )

    assert validation["dispatch_status"] == "denied"
    assert "expired_execution_lease" in validation["problems"]


def test_1324_revoked_capability_blocks_preparation():
    validation = validate_runtime_task_dispatch_preparation_request(
        _request(capability_grant=_grant(status="revoked"))
    )

    assert validation["dispatch_status"] == "denied"
    assert "revoked_capability_grant" in validation["problems"]


def test_1325_missing_executor_binding_blocks_preparation():
    validation = validate_runtime_task_dispatch_preparation_request(
        _request(executor_binding={})
    )

    assert validation["dispatch_status"] == "denied"
    assert "missing_executor_binding" in validation["problems"]
    assert "inactive_executor_binding" in validation["problems"]


def test_1326_dispatch_contains_executor_target_metadata():
    record = build_runtime_task_dispatch_preparation_record(_request())
    target = record["executor_target"]

    assert target["executor_binding_id"] == _binding()["executor_binding_id"]
    assert target["executor_id"] == "executor-zero"
    assert target["executor_type"] == "runtime_task_executor"
    assert target["target_mode"] == "record_only"


def test_1327_dispatch_preparation_does_not_execute():
    record = build_runtime_task_dispatch_preparation_record(_request())
    continuation = can_runtime_dispatch_execute(record)

    assert record["dispatch_status"] == "prepared"
    assert record["executor_run_performed"] is False
    assert continuation["can_execute"] is False
    assert continuation["blocked_reason"] == "executor_dispatch_execution_disabled"


def test_1327_dispatch_preparation_cannot_invoke_tools():
    record = build_runtime_task_dispatch_preparation_record(_request())

    assert record["tool_invoked"] is False
    assert record["dispatch_plan"]["tool_invocation_allowed"] is False
    assert record["audit_record"]["tool_invoked"] is False


def test_1328_dispatch_preparation_cannot_mutate_state():
    record = build_runtime_task_dispatch_preparation_record(_request())

    assert record["filesystem_mutation_performed"] is False
    assert record["state_mutation_performed"] is False
    assert record["dispatch_plan"]["state_mutation_allowed"] is False
    assert record["task_completed"] is False


def test_1328_audit_projection_deterministic():
    first = build_runtime_task_dispatch_preparation_audit_projection(
        build_runtime_task_dispatch_preparation_record(_request())
    )
    second = build_runtime_task_dispatch_preparation_audit_projection(
        build_runtime_task_dispatch_preparation_record(_request())
    )

    assert first == second
    assert first["projection_only"] is True
    assert first["prepared_record_only"] is True
