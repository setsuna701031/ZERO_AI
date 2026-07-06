from __future__ import annotations

from core.runtime.runtime_task_dispatch_commit import (
    build_runtime_task_dispatch_commit_audit_projection,
    build_runtime_task_dispatch_commit_record,
    build_runtime_task_dispatch_commit_request,
    can_runtime_task_dispatch_commit_execute,
    expire_runtime_task_dispatch_commit,
    revoke_runtime_task_dispatch_commit,
    validate_runtime_task_dispatch_commit_request,
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


def _preparation(status="prepared"):
    return {
        "dispatch_id": "task-dispatch::limited-runtime-session::birth-1209::task-admission-001::abcd",
        "task_admission_id": "task-admission::limited-runtime-session::birth-1209::task-001::abcd",
        "executor_binding_id": _binding()["executor_binding_id"],
        "dispatch_status": status,
        "dispatch_plan": {
            "plan_type": "dispatch_preparation_record_only",
            "requested_task_id": "task-001",
            "requested_task_type": "read_task",
            "executor_run_allowed": False,
            "tool_invocation_allowed": False,
            "state_mutation_allowed": False,
        },
        "executor_target": {
            "executor_binding_id": _binding()["executor_binding_id"],
            "executor_id": "executor-zero",
            "executor_type": "runtime_task_executor",
            "runtime_session_id": _session_id(),
            "execution_lease_id": _lease()["lease_id"],
            "capability_grant_id": _grant()["capability_grant_id"],
            "target_mode": "record_only",
        },
        "denial_reason": "none" if status == "prepared" else f"{status}_for_test",
        "record_only": True,
        "executor_run_performed": False,
        "tool_invoked": False,
        "state_mutation_performed": False,
    }


def _request(**overrides):
    request = build_runtime_task_dispatch_commit_request(
        dispatch_commit_request_id="dispatch-commit-1329",
        dispatch_preparation=_preparation(),
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        commit_time="deterministic-time::1329",
    )
    request.update(overrides)
    return request


def test_1329_prepared_dispatch_creates_commit_record():
    record = build_runtime_task_dispatch_commit_record(_request())

    assert record["dispatch_commit_id"].startswith("task-dispatch-commit::")
    assert record["dispatch_id"] == _preparation()["dispatch_id"]
    assert record["commit_status"] == "committed"
    assert record["dispatch_ready"] is True
    assert record["record_only"] is True


def test_1330_denied_preparation_blocks_commit():
    record = build_runtime_task_dispatch_commit_record(
        _request(dispatch_preparation=_preparation(status="denied"))
    )

    assert record["commit_status"] == "denied"
    assert "denied_dispatch_preparation" in record["denial_reason"]
    assert record["dispatch_ready"] is False


def test_1331_expired_lease_blocks_commit():
    validation = validate_runtime_task_dispatch_commit_request(
        _request(execution_lease=_lease(status="expired"))
    )

    assert validation["commit_status"] == "denied"
    assert "expired_execution_lease" in validation["problems"]


def test_1332_revoked_capability_blocks_commit():
    validation = validate_runtime_task_dispatch_commit_request(
        _request(capability_grant=_grant(status="revoked"))
    )

    assert validation["commit_status"] == "denied"
    assert "revoked_capability_grant" in validation["problems"]


def test_1333_missing_executor_target_blocks_commit():
    preparation = _preparation()
    preparation["executor_target"] = {}
    validation = validate_runtime_task_dispatch_commit_request(
        _request(dispatch_preparation=preparation)
    )

    assert validation["commit_status"] == "denied"
    assert "missing_executor_target" in validation["problems"]


def test_1334_executor_identity_mismatch_blocks_commit():
    preparation = _preparation()
    preparation["executor_target"]["executor_binding_id"] = "other-binding"
    validation = validate_runtime_task_dispatch_commit_request(
        _request(dispatch_preparation=preparation)
    )

    assert validation["commit_status"] == "denied"
    assert "executor_target_mismatch" in validation["problems"]


def test_1335_commit_contains_executor_target_metadata():
    record = build_runtime_task_dispatch_commit_record(_request())
    target = record["executor_target"]

    assert target["executor_binding_id"] == _binding()["executor_binding_id"]
    assert target["executor_id"] == "executor-zero"
    assert target["executor_type"] == "runtime_task_executor"
    assert target["target_mode"] == "record_only"


def test_1336_committed_dispatch_still_cannot_execute():
    record = build_runtime_task_dispatch_commit_record(_request())
    continuation = can_runtime_task_dispatch_commit_execute(record)

    assert record["commit_status"] == "committed"
    assert record["executor_run_performed"] is False
    assert continuation["can_execute"] is False
    assert continuation["blocked_reason"] == "executor_dispatch_execution_boundary_not_open"


def test_1336_commit_cannot_invoke_tools_or_mutate_state():
    record = build_runtime_task_dispatch_commit_record(_request())

    assert record["tool_invoked"] is False
    assert record["filesystem_mutation_performed"] is False
    assert record["state_mutation_performed"] is False
    assert record["task_completed"] is False
    assert record["autonomy_loop_started"] is False
    assert record["background_worker_started"] is False


def test_1336_expired_and_revoked_commit_block_dispatch_readiness():
    record = build_runtime_task_dispatch_commit_record(_request())
    expired = expire_runtime_task_dispatch_commit(record)
    revoked = revoke_runtime_task_dispatch_commit(record)

    assert expired["commit_status"] == "expired"
    assert expired["dispatch_ready"] is False
    assert revoked["commit_status"] == "revoked"
    assert revoked["dispatch_ready"] is False


def test_1336_audit_projection_deterministic():
    first = build_runtime_task_dispatch_commit_audit_projection(
        build_runtime_task_dispatch_commit_record(_request())
    )
    second = build_runtime_task_dispatch_commit_audit_projection(
        build_runtime_task_dispatch_commit_record(_request())
    )

    assert first == second
    assert first["projection_only"] is True
    assert first["committed_record_only"] is True
