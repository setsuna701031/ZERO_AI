from __future__ import annotations

from core.runtime.runtime_tool_invocation_controller import (
    AUTHORIZED_TOOL_INVOCATION_DECISION,
    TOOL_INVOCATION_STATES,
    build_runtime_tool_invocation_audit_projection,
    build_runtime_tool_invocation_audit_record,
    build_runtime_tool_invocation_heartbeat_projection,
    build_runtime_tool_invocation_milestone_seal,
    build_runtime_tool_invocation_request,
    can_runtime_tool_invocation_continue,
    expire_runtime_tool_invocation,
    fail_runtime_tool_invocation,
    revoke_runtime_tool_invocation,
    validate_runtime_tool_invocation_request,
)


def _session_id():
    return "limited-runtime-session::birth-1209"


def _lease():
    return {
        "lease_id": "execution-lease::limited-runtime-session::birth-1209::lease-1217",
        "runtime_session_id": _session_id(),
        "lease_status": "granted",
        "execution_allowed": False,
        "mutation_allowed": False,
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
        "tool_call_allowed": False,
        "execution_allowed": False,
    }


def _binding():
    return {
        "executor_binding_id": (
            "executor-binding::limited-runtime-session::birth-1209::"
            "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
            "capability-grant::limited-runtime-session::birth-1209::"
            "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
            "capability-1225::executor-zero::binding-1233"
        ),
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease()["lease_id"],
        "capability_grant_id": _grant()["capability_grant_id"],
        "executor_id": "executor-zero",
        "executor_type": "tool_executor",
        "binding_status": "bound",
        "tool_call_allowed": False,
        "execution_allowed": False,
    }


def _boundary():
    return {
        "tool_boundary_id": (
            "tool-boundary::limited-runtime-session::birth-1209::"
            "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
            "capability-grant::limited-runtime-session::birth-1209::"
            "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
            "capability-1225::"
            "executor-binding::limited-runtime-session::birth-1209::"
            "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
            "capability-grant::limited-runtime-session::birth-1209::"
            "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
            "capability-1225::executor-zero::binding-1233::"
            "inspect_state::tool-boundary-1241"
        ),
        "runtime_session_id": _session_id(),
        "execution_lease_id": _lease()["lease_id"],
        "capability_grant_id": _grant()["capability_grant_id"],
        "executor_binding_id": _binding()["executor_binding_id"],
        "requested_tool_name": "inspect_state",
        "requested_tool_type": "read_tool",
        "tool_boundary_status": "admitted",
        "admission_granted": True,
        "tool_invoked": False,
        "tool_invocation_allowed": False,
    }


def _authorized_request(**overrides):
    request = build_runtime_tool_invocation_request(
        tool_invocation_request_id="tool-invocation-1249",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        tool_boundary=_boundary(),
        authorization_input={
            "decision": AUTHORIZED_TOOL_INVOCATION_DECISION,
            "explicit_invocation_authorization": True,
            "authorize_tool_invocation_record": True,
        },
    )
    request.update(overrides)
    return request


def test_1249_no_boundary_no_invocation():
    request = build_runtime_tool_invocation_request(
        tool_invocation_request_id="tool-invocation-1249",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        authorization_input={
            "decision": AUTHORIZED_TOOL_INVOCATION_DECISION,
            "explicit_invocation_authorization": True,
            "authorize_tool_invocation_record": True,
        },
    )

    validation = validate_runtime_tool_invocation_request(request)

    assert validation["invocation_created"] is False
    assert validation["tool_invocation_record"] is None
    assert "missing_tool_boundary" in validation["problems"]


def test_1250_denied_boundary_cannot_invoke():
    request = _authorized_request(
        tool_boundary={
            **_boundary(),
            "tool_boundary_status": "denied",
            "admission_granted": False,
        }
    )

    validation = validate_runtime_tool_invocation_request(request)

    assert validation["invocation_created"] is False
    assert "tool_boundary_not_admitted" in validation["problems"]


def test_1250_invalid_session_blocks_invocation():
    request = _authorized_request(runtime_session_id=None)

    validation = validate_runtime_tool_invocation_request(request)

    assert validation["invocation_created"] is False
    assert "invalid_runtime_session_id" in validation["problems"]


def test_1251_invalid_lease_blocks_invocation():
    request = _authorized_request(execution_lease={**_lease(), "lease_status": "expired"})

    validation = validate_runtime_tool_invocation_request(request)

    assert validation["invocation_created"] is False
    assert "inactive_execution_lease" in validation["problems"]


def test_1251_invalid_capability_blocks_invocation():
    request = _authorized_request(capability_grant={**_grant(), "grant_status": "expired"})

    validation = validate_runtime_tool_invocation_request(request)

    assert validation["invocation_created"] is False
    assert "inactive_capability_grant" in validation["problems"]


def test_1252_invalid_executor_binding_blocks_invocation():
    request = _authorized_request(
        executor_binding={**_binding(), "binding_status": "revoked"}
    )

    validation = validate_runtime_tool_invocation_request(request)

    assert validation["invocation_created"] is False
    assert "inactive_executor_binding" in validation["problems"]


def test_1253_admitted_boundary_creates_invocation_record_only():
    validation = validate_runtime_tool_invocation_request(_authorized_request())
    invocation = validation["tool_invocation_record"]

    assert validation["invocation_created"] is True
    assert invocation["tool_invocation_id"] == (
        "tool-invocation::limited-runtime-session::birth-1209::"
        "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
        "capability-grant::limited-runtime-session::birth-1209::"
        "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
        "capability-1225::"
        "executor-binding::limited-runtime-session::birth-1209::"
        "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
        "capability-grant::limited-runtime-session::birth-1209::"
        "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
        "capability-1225::executor-zero::binding-1233::"
        "tool-boundary::limited-runtime-session::birth-1209::"
        "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
        "capability-grant::limited-runtime-session::birth-1209::"
        "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
        "capability-1225::"
        "executor-binding::limited-runtime-session::birth-1209::"
        "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
        "capability-grant::limited-runtime-session::birth-1209::"
        "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
        "capability-1225::executor-zero::binding-1233::"
        "inspect_state::tool-boundary-1241::inspect_state::tool-invocation-1249"
    )
    assert invocation["invocation_status"] == "approved"
    assert invocation["invocation_result"]["result_type"] == "synthetic_only"
    assert invocation["supported_states"] == list(TOOL_INVOCATION_STATES)


def test_1253_invocation_does_not_execute_real_tool():
    invocation = validate_runtime_tool_invocation_request(_authorized_request())[
        "tool_invocation_record"
    ]
    continuation = can_runtime_tool_invocation_continue(invocation)

    assert invocation["actual_tool_executed"] is False
    assert invocation["subprocess_allowed"] is False
    assert invocation["shell_allowed"] is False
    assert continuation["can_continue"] is False
    assert continuation["blocked_reason"] == "actual_tool_execution_disabled"


def test_1254_invocation_cannot_mutate_filesystem():
    invocation = validate_runtime_tool_invocation_request(_authorized_request())[
        "tool_invocation_record"
    ]

    assert invocation["filesystem_access_allowed"] is False
    assert invocation["file_read_allowed"] is False
    assert invocation["file_write_allowed"] is False
    assert invocation["network_allowed"] is False
    assert invocation["mutation_allowed"] is False


def test_1254_invocation_failure_is_recorded():
    invocation = validate_runtime_tool_invocation_request(_authorized_request())[
        "tool_invocation_record"
    ]
    failed = fail_runtime_tool_invocation(
        invocation,
        reason="synthetic_tool_failure",
        owner="tool_boundary_owner",
    )

    assert failed["invocation_status"] == "failed"
    assert failed["failure_reason"] == "synthetic_tool_failure"
    assert failed["failure_ownership"]["failure_recorded"] is True
    assert failed["failure_ownership"]["failure_owner"] == "tool_boundary_owner"
    assert failed["invocation_result"]["result_type"] == "synthetic_failure"
    assert failed["actual_tool_executed"] is False


def test_1255_expired_or_revoked_invocation_cannot_continue():
    invocation = validate_runtime_tool_invocation_request(_authorized_request())[
        "tool_invocation_record"
    ]
    expired = expire_runtime_tool_invocation(invocation, current_tick=1)
    revoked = revoke_runtime_tool_invocation(invocation, reason="operator_cancelled")

    expired_continue = can_runtime_tool_invocation_continue(expired)
    revoked_continue = can_runtime_tool_invocation_continue(revoked)

    assert expired["invocation_status"] == "expired"
    assert expired_continue["can_continue"] is False
    assert expired_continue["blocked_reason"] == "tool_invocation_expired"
    assert revoked["invocation_status"] == "revoked"
    assert revoked["cancellation_model"]["cancelled"] is True
    assert revoked_continue["can_continue"] is False
    assert revoked_continue["blocked_reason"] == "tool_invocation_revoked"


def test_1256_invocation_cannot_bypass_runtime_chain():
    mismatched_boundary = {**_boundary(), "executor_binding_id": "other-binding"}
    request = _authorized_request(tool_boundary=mismatched_boundary)

    validation = validate_runtime_tool_invocation_request(request)

    assert validation["invocation_created"] is False
    assert "tool_boundary_not_admitted" in validation["problems"]


def test_1256_heartbeat_audit_and_seal_are_data_only():
    validation = validate_runtime_tool_invocation_request(_authorized_request())
    invocation = validation["tool_invocation_record"]
    heartbeat = build_runtime_tool_invocation_heartbeat_projection(invocation)
    projection = build_runtime_tool_invocation_audit_projection(invocation)
    audit = build_runtime_tool_invocation_audit_record(_authorized_request())
    seal = build_runtime_tool_invocation_milestone_seal(_authorized_request())

    assert heartbeat["projection_only"] is True
    assert heartbeat["heartbeat_live"] is False
    assert heartbeat["background_loop_allowed"] is False
    assert projection["projection_only"] is True
    assert projection["actual_tool_executed"] is False
    assert audit["decision"] == "reserved_runtime_tool_invocation_record_only"
    assert audit["invocation_created"] is True
    assert audit["actual_tool_executed"] is False
    assert audit["filesystem_access_performed"] is False
    assert audit["network_performed"] is False
    assert audit["mutation_performed"] is False
    assert seal["closed"] is True
    assert seal["next_package"] == 1257
    assert seal["all_real_world_effects_locked"] is True
