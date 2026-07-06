from __future__ import annotations

from core.runtime.runtime_executor_invocation_boundary import (
    build_runtime_executor_invocation_boundary_audit_projection,
    build_runtime_executor_invocation_boundary_record,
    build_runtime_executor_invocation_boundary_request,
    can_runtime_executor_invocation_boundary_run,
    expire_runtime_executor_invocation_boundary,
    revoke_runtime_executor_invocation_boundary,
    validate_runtime_executor_invocation_boundary_request,
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


def _commit(status="committed"):
    return {
        "dispatch_commit_id": "task-dispatch-commit::limited-runtime-session::birth-1209::commit-1329",
        "dispatch_id": "task-dispatch::limited-runtime-session::birth-1209::task-admission-001::abcd",
        "task_admission_id": "task-admission::limited-runtime-session::birth-1209::task-001::abcd",
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease()["lease_id"],
        "capability_grant_id": _grant()["capability_grant_id"],
        "executor_binding_id": _binding()["executor_binding_id"],
        "executor_target": {
            "executor_binding_id": _binding()["executor_binding_id"],
            "executor_id": "executor-zero",
            "executor_type": "runtime_task_executor",
            "runtime_session_id": _session_id(),
            "execution_lease_id": _lease()["lease_id"],
            "capability_grant_id": _grant()["capability_grant_id"],
            "target_mode": "record_only",
        },
        "commit_status": status,
        "denial_reason": "none" if status == "committed" else f"{status}_for_test",
        "record_only": True,
        "dispatch_ready": status == "committed",
        "executor_run_performed": False,
        "tool_invoked": False,
        "state_mutation_performed": False,
        "task_completed": False,
    }


def _request(**overrides):
    request = build_runtime_executor_invocation_boundary_request(
        executor_invocation_request_id="executor-invocation-boundary-1337",
        dispatch_commit=_commit(),
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        invocation_time="deterministic-time::1337",
    )
    request.update(overrides)
    return request


def test_1337_committed_dispatch_creates_invocation_boundary():
    record = build_runtime_executor_invocation_boundary_record(_request())

    assert record["executor_invocation_id"].startswith(
        "executor-invocation-boundary::"
    )
    assert record["dispatch_commit_id"] == _commit()["dispatch_commit_id"]
    assert record["invocation_status"] == "bounded"
    assert record["boundary_ready"] is True
    assert record["record_only"] is True


def test_1338_denied_dispatch_commit_blocks_invocation_boundary():
    record = build_runtime_executor_invocation_boundary_record(
        _request(dispatch_commit=_commit(status="denied"))
    )

    assert record["invocation_status"] == "denied"
    assert "denied_dispatch_commit" in record["denial_reason"]
    assert record["boundary_ready"] is False


def test_1339_expired_lease_blocks_invocation_boundary():
    validation = validate_runtime_executor_invocation_boundary_request(
        _request(execution_lease=_lease(status="expired"))
    )

    assert validation["invocation_status"] == "denied"
    assert "expired_execution_lease" in validation["problems"]


def test_1340_revoked_capability_blocks_invocation_boundary():
    validation = validate_runtime_executor_invocation_boundary_request(
        _request(capability_grant=_grant(status="revoked"))
    )

    assert validation["invocation_status"] == "denied"
    assert "revoked_capability_grant" in validation["problems"]


def test_1341_missing_executor_binding_blocks_invocation_boundary():
    validation = validate_runtime_executor_invocation_boundary_request(
        _request(executor_binding={})
    )

    assert validation["invocation_status"] == "denied"
    assert "missing_executor_binding" in validation["problems"]
    assert "inactive_executor_binding" in validation["problems"]


def test_1342_executor_target_mismatch_blocks_invocation_boundary():
    commit = _commit()
    commit["executor_target"]["executor_binding_id"] = "other-binding"
    validation = validate_runtime_executor_invocation_boundary_request(
        _request(dispatch_commit=commit)
    )

    assert validation["invocation_status"] == "denied"
    assert "executor_target_mismatch" in validation["problems"]


def test_1343_invocation_boundary_contains_execution_envelope():
    record = build_runtime_executor_invocation_boundary_record(_request())
    envelope = record["invocation_envelope"]

    assert envelope["envelope_type"] == "executor_invocation_boundary_record_only"
    assert envelope["executor_binding_id"] == _binding()["executor_binding_id"]
    assert envelope["executor_id"] == "executor-zero"
    assert envelope["executor_type"] == "runtime_task_executor"
    assert envelope["target_mode"] == "record_only"


def test_1344_invocation_boundary_does_not_run_executor():
    record = build_runtime_executor_invocation_boundary_record(_request())
    continuation = can_runtime_executor_invocation_boundary_run(record)

    assert record["invocation_status"] == "bounded"
    assert record["executor_run_performed"] is False
    assert record["task_execution_performed"] is False
    assert continuation["can_run_executor"] is False
    assert continuation["can_execute_task"] is False
    assert continuation["blocked_reason"] == "runtime_executor_invocation_execution_disabled"


def test_1344_invocation_boundary_cannot_invoke_tools_or_mutate_state():
    record = build_runtime_executor_invocation_boundary_record(_request())
    envelope = record["invocation_envelope"]

    assert record["tool_invoked"] is False
    assert record["filesystem_mutation_performed"] is False
    assert record["state_mutation_performed"] is False
    assert record["task_completed"] is False
    assert record["autonomy_loop_started"] is False
    assert record["background_worker_started"] is False
    assert envelope["tool_invocation_allowed"] is False
    assert envelope["state_mutation_allowed"] is False


def test_1344_expired_and_revoked_boundary_block_executor_readiness():
    record = build_runtime_executor_invocation_boundary_record(_request())
    expired = expire_runtime_executor_invocation_boundary(record)
    revoked = revoke_runtime_executor_invocation_boundary(record)

    assert expired["invocation_status"] == "expired"
    assert expired["boundary_ready"] is False
    assert revoked["invocation_status"] == "revoked"
    assert revoked["boundary_ready"] is False


def test_1344_audit_projection_deterministic():
    first = build_runtime_executor_invocation_boundary_audit_projection(
        build_runtime_executor_invocation_boundary_record(_request())
    )
    second = build_runtime_executor_invocation_boundary_audit_projection(
        build_runtime_executor_invocation_boundary_record(_request())
    )

    assert first == second
    assert first["projection_only"] is True
    assert first["bounded_record_only"] is True
