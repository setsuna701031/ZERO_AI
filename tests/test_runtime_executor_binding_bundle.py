from __future__ import annotations

from core.runtime.runtime_executor_binding import (
    AUTHORIZED_EXECUTOR_BIND_DECISION,
    EXECUTOR_BINDING_STATES,
    EXECUTOR_TYPES,
    build_runtime_executor_binding_audit_record,
    build_runtime_executor_binding_heartbeat_projection,
    build_runtime_executor_binding_milestone_seal,
    build_runtime_executor_binding_request,
    can_runtime_executor_binding_authorize_execution,
    expire_runtime_executor_binding,
    revoke_runtime_executor_binding,
    validate_runtime_executor_binding_request,
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
        "executor_start_allowed": False,
        "execution_allowed": False,
    }


def _authorized_request(**overrides):
    request = build_runtime_executor_binding_request(
        binding_request_id="binding-1233",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_id="executor-zero",
        executor_type="task_executor",
        authorization_input={
            "decision": AUTHORIZED_EXECUTOR_BIND_DECISION,
            "explicit_bind_authorization": True,
            "authorize_executor_binding_record": True,
        },
    )
    request.update(overrides)
    return request


def test_1233_default_runtime_has_no_executor():
    request = build_runtime_executor_binding_request(
        binding_request_id="binding-1233",
        runtime_session_id=_session_id(),
    )

    validation = validate_runtime_executor_binding_request(request)

    assert validation["binding_created"] is False
    assert validation["executor_binding_record"] is None
    assert validation["executor_enabled"] is False


def test_1234_lease_alone_cannot_bind_executor():
    request = build_runtime_executor_binding_request(
        binding_request_id="binding-1234",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        executor_id="executor-zero",
        authorization_input={
            "decision": AUTHORIZED_EXECUTOR_BIND_DECISION,
            "explicit_bind_authorization": True,
            "authorize_executor_binding_record": True,
        },
    )

    validation = validate_runtime_executor_binding_request(request)

    assert validation["binding_created"] is False
    assert "inactive_capability_grant" in validation["problems"]


def test_1235_capability_alone_cannot_bind_executor():
    request = build_runtime_executor_binding_request(
        binding_request_id="binding-1235",
        runtime_session_id=_session_id(),
        capability_grant=_grant(),
        executor_id="executor-zero",
        authorization_input={
            "decision": AUTHORIZED_EXECUTOR_BIND_DECISION,
            "explicit_bind_authorization": True,
            "authorize_executor_binding_record": True,
        },
    )

    validation = validate_runtime_executor_binding_request(request)

    assert validation["binding_created"] is False
    assert "inactive_execution_lease" in validation["problems"]
    assert "inactive_capability_grant" in validation["problems"]


def test_1236_invalid_capability_cannot_bind_executor():
    request = _authorized_request(
        capability_grant={**_grant(), "grant_status": "expired"}
    )

    validation = validate_runtime_executor_binding_request(request)

    assert validation["binding_created"] is False
    assert "inactive_capability_grant" in validation["problems"]


def test_1237_unauthorized_request_creates_no_binding():
    request = build_runtime_executor_binding_request(
        binding_request_id="binding-1237",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_id="executor-zero",
    )

    validation = validate_runtime_executor_binding_request(request)

    assert validation["binding_created"] is False
    assert "executor_bind_authorization_missing" in validation["problems"]


def test_1238_authorized_request_creates_binding_record():
    validation = validate_runtime_executor_binding_request(_authorized_request())
    binding = validation["executor_binding_record"]

    assert validation["binding_created"] is True
    assert binding["executor_binding_id"] == (
        "executor-binding::limited-runtime-session::birth-1209::"
        "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
        "capability-grant::limited-runtime-session::birth-1209::"
        "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
        "capability-1225::executor-zero::binding-1233"
    )
    assert binding["runtime_session_id"] == _session_id()
    assert binding["execution_lease_id"] == _lease()["lease_id"]
    assert binding["capability_grant_id"] == _grant()["capability_grant_id"]
    assert binding["executor_id"] == "executor-zero"
    assert binding["executor_type"] == "task_executor"
    assert binding["binding_status"] == "bound"
    assert binding["supported_states"] == list(EXECUTOR_BINDING_STATES)
    assert binding["reserved_executor_types"] == list(EXECUTOR_TYPES)


def test_1238_binding_does_not_execute_anything():
    binding = validate_runtime_executor_binding_request(_authorized_request())[
        "executor_binding_record"
    ]
    authorization = can_runtime_executor_binding_authorize_execution(binding)

    assert binding["executor_enabled"] is False
    assert binding["executor_started"] is False
    assert binding["task_execution_allowed"] is False
    assert binding["subprocess_allowed"] is False
    assert binding["file_mutation_allowed"] is False
    assert binding["io_allowed"] is False
    assert binding["tool_call_allowed"] is False
    assert binding["background_loop_allowed"] is False
    assert authorization["can_authorize_execution"] is False
    assert authorization["blocked_reason"] == "executor_disabled"


def test_1239_revoked_binding_blocks_executor():
    binding = validate_runtime_executor_binding_request(_authorized_request())[
        "executor_binding_record"
    ]
    revoked = revoke_runtime_executor_binding(binding, reason="operator_revoked")
    authorization = can_runtime_executor_binding_authorize_execution(revoked)

    assert revoked["binding_status"] == "revoked"
    assert revoked["revocation_model"]["revoked"] is True
    assert revoked["executor_enabled"] is False
    assert authorization["can_authorize_execution"] is False
    assert authorization["blocked_reason"] == "executor_binding_revoked"


def test_1239_expired_binding_blocks_executor():
    binding = validate_runtime_executor_binding_request(_authorized_request())[
        "executor_binding_record"
    ]
    expired = expire_runtime_executor_binding(binding, current_tick=1)
    authorization = can_runtime_executor_binding_authorize_execution(expired)

    assert expired["binding_status"] == "expired"
    assert expired["expiration_model"]["expired"] is True
    assert expired["executor_enabled"] is False
    assert authorization["can_authorize_execution"] is False
    assert authorization["blocked_reason"] == "executor_binding_expired"


def test_1240_executor_cannot_bypass_session_lease_capability_chain():
    mismatched_grant = {**_grant(), "owner_lease_id": "other-lease"}
    request = _authorized_request(capability_grant=mismatched_grant)

    validation = validate_runtime_executor_binding_request(request)

    assert validation["binding_created"] is False
    assert "inactive_capability_grant" in validation["problems"]


def test_1240_heartbeat_audit_and_seal_are_data_only():
    validation = validate_runtime_executor_binding_request(_authorized_request())
    binding = validation["executor_binding_record"]
    projection = build_runtime_executor_binding_heartbeat_projection(binding)
    audit = build_runtime_executor_binding_audit_record(_authorized_request())
    seal = build_runtime_executor_binding_milestone_seal(_authorized_request())

    assert projection["projection_only"] is True
    assert projection["heartbeat_live"] is False
    assert projection["executor_enabled"] is False
    assert projection["background_loop_allowed"] is False
    assert audit["decision"] == "reserved_runtime_executor_binding_record_only"
    assert audit["binding_created"] is True
    assert audit["executor_enabled"] is False
    assert audit["executor_started"] is False
    assert audit["task_executed"] is False
    assert audit["file_mutation_performed"] is False
    assert audit["io_performed"] is False
    assert seal["closed"] is True
    assert seal["next_package"] == 1241
    assert seal["all_execution_surfaces_locked"] is True
