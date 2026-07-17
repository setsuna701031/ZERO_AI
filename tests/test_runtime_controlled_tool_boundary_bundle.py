from __future__ import annotations

from core.runtime.runtime_controlled_tool_boundary import (
    AUTHORIZED_TOOL_ADMISSION_DECISION,
    REQUESTED_TOOL_TYPES,
    TOOL_BOUNDARY_STATUSES,
    build_runtime_controlled_tool_audit_projection,
    build_runtime_controlled_tool_boundary_audit_record,
    build_runtime_controlled_tool_boundary_milestone_seal,
    build_runtime_controlled_tool_boundary_request,
    can_runtime_controlled_tool_boundary_authorize_invocation,
    expire_runtime_controlled_tool_boundary,
    revoke_runtime_controlled_tool_boundary,
    validate_runtime_controlled_tool_boundary_request,
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


def _authorized_request(**overrides):
    request = build_runtime_controlled_tool_boundary_request(
        tool_boundary_request_id="tool-boundary-1241",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        requested_tool_name="inspect_state",
        requested_tool_type="read_tool",
        authorization_input={
            "decision": AUTHORIZED_TOOL_ADMISSION_DECISION,
            "explicit_tool_authorization": True,
            "authorize_tool_admission_record": True,
        },
    )
    request.update(overrides)
    return request


def test_1241_default_runtime_has_no_admitted_tool():
    request = build_runtime_controlled_tool_boundary_request(
        tool_boundary_request_id="tool-boundary-1241",
        runtime_session_id=_session_id(),
    )

    validation = validate_runtime_controlled_tool_boundary_request(request)
    boundary = validation["tool_boundary_record"]

    assert validation["tool_boundary_created"] is True
    assert validation["admission_granted"] is False
    assert boundary["tool_boundary_status"] == "denied"
    assert boundary["tool_invoked"] is False


def test_1242_executor_binding_alone_cannot_admit_tool():
    request = build_runtime_controlled_tool_boundary_request(
        tool_boundary_request_id="tool-boundary-1242",
        runtime_session_id=_session_id(),
        executor_binding=_binding(),
        requested_tool_name="inspect_state",
        authorization_input={
            "decision": AUTHORIZED_TOOL_ADMISSION_DECISION,
            "explicit_tool_authorization": True,
            "authorize_tool_admission_record": True,
        },
    )

    validation = validate_runtime_controlled_tool_boundary_request(request)

    assert validation["admission_granted"] is False
    assert "inactive_execution_lease" in validation["problems"]
    assert "inactive_capability_grant" in validation["problems"]
    assert "inactive_executor_binding" in validation["problems"]


def test_1242_invalid_session_cannot_admit_tool():
    request = _authorized_request(runtime_session_id=None)

    validation = validate_runtime_controlled_tool_boundary_request(request)

    assert validation["admission_granted"] is False
    assert "invalid_runtime_session_id" in validation["problems"]


def test_1243_invalid_lease_cannot_admit_tool():
    request = _authorized_request(execution_lease={**_lease(), "lease_status": "expired"})

    validation = validate_runtime_controlled_tool_boundary_request(request)

    assert validation["admission_granted"] is False
    assert "inactive_execution_lease" in validation["problems"]


def test_1243_invalid_capability_cannot_admit_tool():
    request = _authorized_request(capability_grant={**_grant(), "grant_status": "revoked"})

    validation = validate_runtime_controlled_tool_boundary_request(request)

    assert validation["admission_granted"] is False
    assert "inactive_capability_grant" in validation["problems"]


def test_1244_invalid_executor_binding_cannot_admit_tool():
    request = _authorized_request(
        executor_binding={**_binding(), "binding_status": "expired"}
    )

    validation = validate_runtime_controlled_tool_boundary_request(request)

    assert validation["admission_granted"] is False
    assert "inactive_executor_binding" in validation["problems"]


def test_1245_unauthorized_request_creates_denied_record():
    request = build_runtime_controlled_tool_boundary_request(
        tool_boundary_request_id="tool-boundary-1245",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        requested_tool_name="inspect_state",
        requested_tool_type="read_tool",
    )

    validation = validate_runtime_controlled_tool_boundary_request(request)
    boundary = validation["tool_boundary_record"]

    assert validation["tool_boundary_created"] is True
    assert validation["admission_granted"] is False
    assert boundary["tool_boundary_status"] == "denied"
    assert "tool_authorization_missing" in boundary["denial_reason"]


def test_1246_authorized_request_creates_admitted_record_only():
    validation = validate_runtime_controlled_tool_boundary_request(_authorized_request())
    boundary = validation["tool_boundary_record"]

    assert validation["admission_granted"] is True
    assert boundary["tool_boundary_id"] == (
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
    )
    assert boundary["tool_boundary_status"] == "admitted"
    assert boundary["denial_reason"] == "none"
    assert boundary["supported_statuses"] == list(TOOL_BOUNDARY_STATUSES)
    assert boundary["supported_requested_tool_types"] == list(REQUESTED_TOOL_TYPES)


def test_1246_admitted_record_does_not_invoke_any_tool():
    boundary = validate_runtime_controlled_tool_boundary_request(_authorized_request())[
        "tool_boundary_record"
    ]
    authorization = can_runtime_controlled_tool_boundary_authorize_invocation(boundary)

    assert boundary["admission_granted"] is True
    assert boundary["tool_runtime_enabled"] is False
    assert boundary["tool_invoked"] is False
    assert boundary["tool_invocation_allowed"] is False
    assert boundary["subprocess_allowed"] is False
    assert boundary["shell_command_allowed"] is False
    assert boundary["file_read_allowed"] is False
    assert boundary["file_write_allowed"] is False
    assert boundary["network_allowed"] is False
    assert boundary["mutation_allowed"] is False
    assert authorization["can_authorize_invocation"] is False
    assert authorization["blocked_reason"] == "tool_invocation_disabled"


def test_1247_all_supported_tool_types_remain_inert():
    for tool_type in REQUESTED_TOOL_TYPES:
        boundary = validate_runtime_controlled_tool_boundary_request(
            _authorized_request(requested_tool_type=tool_type)
        )["tool_boundary_record"]

        assert boundary["requested_tool_type"] == tool_type
        assert boundary["tool_boundary_status"] == "admitted"
        assert boundary["tool_invoked"] is False
        assert boundary["tool_invocation_allowed"] is False
        assert boundary["subprocess_allowed"] is False
        assert boundary["file_read_allowed"] is False
        assert boundary["file_write_allowed"] is False
        assert boundary["network_allowed"] is False
        assert boundary["mutation_allowed"] is False
        assert boundary["task_execution_allowed"] is False


def test_1247_revoked_or_expired_boundary_cannot_authorize_invocation():
    boundary = validate_runtime_controlled_tool_boundary_request(_authorized_request())[
        "tool_boundary_record"
    ]
    revoked = revoke_runtime_controlled_tool_boundary(boundary, reason="operator_revoked")
    expired = expire_runtime_controlled_tool_boundary(boundary, current_tick=1)

    revoked_auth = can_runtime_controlled_tool_boundary_authorize_invocation(revoked)
    expired_auth = can_runtime_controlled_tool_boundary_authorize_invocation(expired)

    assert revoked["tool_boundary_status"] == "revoked"
    assert revoked["admission_granted"] is False
    assert revoked_auth["can_authorize_invocation"] is False
    assert revoked_auth["blocked_reason"] == "tool_boundary_revoked"
    assert expired["tool_boundary_status"] == "expired"
    assert expired["admission_granted"] is False
    assert expired_auth["can_authorize_invocation"] is False
    assert expired_auth["blocked_reason"] == "tool_boundary_expired"


def test_1248_tool_boundary_cannot_bypass_full_chain():
    mismatched_binding = {**_binding(), "capability_grant_id": "other-capability"}
    request = _authorized_request(executor_binding=mismatched_binding)

    validation = validate_runtime_controlled_tool_boundary_request(request)

    assert validation["admission_granted"] is False
    assert "inactive_executor_binding" in validation["problems"]


def test_1248_audit_projection_and_seal_are_data_only():
    validation = validate_runtime_controlled_tool_boundary_request(_authorized_request())
    boundary = validation["tool_boundary_record"]
    projection = build_runtime_controlled_tool_audit_projection(boundary)
    audit = build_runtime_controlled_tool_boundary_audit_record(_authorized_request())
    seal = build_runtime_controlled_tool_boundary_milestone_seal(_authorized_request())

    assert projection["projection_only"] is True
    assert projection["tool_invoked"] is False
    assert projection["tool_invocation_allowed"] is False
    assert audit["decision"] == "reserved_runtime_controlled_tool_boundary_record_only"
    assert audit["tool_boundary_created"] is True
    assert audit["tool_invoked"] is False
    assert audit["subprocess_started"] is False
    assert audit["file_read_performed"] is False
    assert audit["file_write_performed"] is False
    assert audit["network_performed"] is False
    assert seal["closed"] is True
    assert seal["next_package"] == 1249
    assert seal["all_tool_surfaces_locked"] is True
