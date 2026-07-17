from __future__ import annotations

from core.runtime.runtime_task_execution_admission import (
    AUTHORIZED_TASK_ADMISSION_DECISION,
    build_runtime_task_execution_admission_audit_record,
    build_runtime_task_execution_admission_milestone_seal,
    build_runtime_task_execution_admission_record,
    build_runtime_task_execution_admission_request,
    can_runtime_task_execute,
    validate_runtime_task_execution_admission_request,
)


def _session_id():
    return "limited-runtime-session::birth-1209"


def _lease():
    return {
        "lease_id": "execution-lease::limited-runtime-session::birth-1209::lease-1217",
        "runtime_session_id": _session_id(),
        "lease_status": "granted",
    }


def _grant():
    return {
        "capability_grant_id": (
            "capability-grant::limited-runtime-session::birth-1209::"
            "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
            "capability-1225"
        ),
        "owner_session_id": _session_id(),
        "owner_lease_id": _lease()["lease_id"],
        "grant_status": "granted",
        "granted_capabilities": {
            "read_access": True,
            "write_access": False,
            "tool_access": False,
            "execution_access": False,
            "mutation_access": True,
            "task_admission_access": True,
            "network_access": False,
        },
    }


def _binding():
    return {
        "executor_binding_id": "executor-binding::executor-zero::binding-1233",
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease()["lease_id"],
        "capability_grant_id": _grant()["capability_grant_id"],
        "binding_status": "bound",
    }


def _boundary():
    return {
        "tool_boundary_id": "tool-boundary::inspect-state::tool-boundary-1241",
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease()["lease_id"],
        "capability_grant_id": _grant()["capability_grant_id"],
        "executor_binding_id": _binding()["executor_binding_id"],
        "requested_tool_name": "inspect_state",
        "requested_tool_type": "read_tool",
        "tool_boundary_status": "admitted",
        "admission_granted": True,
    }


def _invocation():
    return {
        "tool_invocation_id": "tool-invocation::inspect-state::tool-invocation-1249",
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease()["lease_id"],
        "capability_grant_id": _grant()["capability_grant_id"],
        "executor_binding_id": _binding()["executor_binding_id"],
        "tool_boundary_id": _boundary()["tool_boundary_id"],
        "tool_name": "inspect_state",
        "invocation_status": "approved",
        "actual_tool_executed": False,
    }


def _recovery(status="restored"):
    return {
        "mutation_recovery_id": "mutation-recovery::mutation-execution-1297::abcd",
        "mutation_execution_id": "mutation-execution-1297",
        "recovery_status": status,
        "audit_projection": {
            "rollback_integrity_verified": True,
            "ownership_chain_validated": True,
            "recovery_audit_evidence": True,
        },
    }


def _request(**overrides):
    request = build_runtime_task_execution_admission_request(
        task_admission_request_id="task-admission-1313",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        tool_boundary=_boundary(),
        tool_invocation=_invocation(),
        requested_task_id="task-001",
        requested_task_type="read_task",
        authorization_input={
            "decision": AUTHORIZED_TASK_ADMISSION_DECISION,
            "explicit_task_admission_authorization": True,
            "authorize_task_admission_record": True,
        },
    )
    request.update(overrides)
    return request


def test_1313_no_session_blocks_task_admission():
    validation = validate_runtime_task_execution_admission_request(
        _request(runtime_session_id=None)
    )

    assert validation["admission_status"] == "denied"
    assert "invalid_runtime_session_id" in validation["problems"]


def test_1314_no_lease_blocks_task_admission():
    validation = validate_runtime_task_execution_admission_request(
        _request(execution_lease={})
    )

    assert validation["admission_status"] == "denied"
    assert "inactive_execution_lease" in validation["problems"]


def test_1315_no_capability_blocks_task_admission():
    validation = validate_runtime_task_execution_admission_request(
        _request(capability_grant={})
    )

    assert validation["admission_status"] == "denied"
    assert "inactive_capability_grant" in validation["problems"]


def test_1316_no_executor_binding_blocks_task_admission():
    validation = validate_runtime_task_execution_admission_request(
        _request(executor_binding={})
    )

    assert validation["admission_status"] == "denied"
    assert "inactive_executor_binding" in validation["problems"]


def test_1317_unauthorized_task_creates_denied_record():
    record = build_runtime_task_execution_admission_record(
        _request(
            authorization_input={
                "decision": "NO_GO",
                "explicit_task_admission_authorization": False,
                "authorize_task_admission_record": False,
            }
        )
    )

    assert record["admission_status"] == "denied"
    assert "task_admission_authorization_missing" in record["denial_reason"]
    assert record["task_executed"] is False


def test_1318_read_task_can_be_admitted_as_record_only():
    record = build_runtime_task_execution_admission_record(_request())

    assert record["task_admission_id"].startswith("task-admission::")
    assert record["requested_task_type"] == "read_task"
    assert record["admission_status"] == "admitted"
    assert record["denial_reason"] == "none"
    assert record["record_only"] is True
    assert record["audit_projection"]["admitted_record_only"] is True


def test_1319_mutation_task_requires_recovery_readiness():
    denied = build_runtime_task_execution_admission_record(
        _request(requested_task_type="mutation_task")
    )
    admitted = build_runtime_task_execution_admission_record(
        _request(requested_task_type="mutation_task", mutation_recovery=_recovery())
    )

    assert denied["admission_status"] == "denied"
    assert "mutation_recovery_readiness_missing" in denied["denial_reason"]
    assert admitted["admission_status"] == "admitted"
    assert admitted["recovery_required"] is True


def test_1319_stale_evidence_blocks_admission():
    validation = validate_runtime_task_execution_admission_request(
        _request(evidence_freshness={"stale_evidence_detected": True})
    )

    assert validation["admission_status"] == "denied"
    assert "stale_evidence" in validation["problems"]


def test_1320_admitted_task_does_not_execute():
    record = build_runtime_task_execution_admission_record(_request())
    continuation = can_runtime_task_execute(record)
    audit = build_runtime_task_execution_admission_audit_record(_request())

    assert record["admission_status"] == "admitted"
    assert record["task_executed"] is False
    assert continuation["can_execute"] is False
    assert continuation["blocked_reason"] == "task_execution_disabled"
    assert audit["task_executed"] is False


def test_1320_task_admission_cannot_start_autonomy():
    record = build_runtime_task_execution_admission_record(_request())
    audit = build_runtime_task_execution_admission_audit_record(_request())
    seal = build_runtime_task_execution_admission_milestone_seal(_request())

    assert record["autonomy_started"] is False
    assert record["self_start_performed"] is False
    assert record["background_loop_started"] is False
    assert audit["autonomy_started"] is False
    assert audit["background_loop_started"] is False
    assert seal["forbidden_surfaces_locked"] is True
