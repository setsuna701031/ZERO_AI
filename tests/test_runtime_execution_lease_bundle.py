from __future__ import annotations

from core.runtime.runtime_execution_lease import (
    AUTHORIZED_LEASE_DECISION,
    LEASE_STATUSES,
    build_runtime_execution_lease_audit_record,
    build_runtime_execution_lease_heartbeat_projection,
    build_runtime_execution_lease_milestone_seal,
    build_runtime_execution_lease_request,
    can_runtime_execution_lease_authorize_execution,
    expire_runtime_execution_lease,
    revoke_runtime_execution_lease,
    validate_runtime_execution_lease_request,
)


def _session():
    return {
        "runtime_session_id": "limited-runtime-session::birth-1209",
        "session_type": "limited",
        "status": "born_inert",
        "lease_id": None,
        "execution_lease_active": False,
        "capabilities": [],
        "execution_allowed": False,
        "mutation_allowed": False,
    }


def _authorized_request():
    return build_runtime_execution_lease_request(
        lease_request_id="lease-1217",
        runtime_session=_session(),
        authorization_input={
            "decision": AUTHORIZED_LEASE_DECISION,
            "explicit_authorization": True,
            "authorize_lease_record": True,
        },
        lease_owner={
            "operator_id": "operator-zero",
            "executor_id": "executor-zero",
            "ownership_verified": True,
        },
    )


def test_1217_default_session_has_no_lease():
    session = _session()
    request = build_runtime_execution_lease_request(
        lease_request_id="lease-1217",
        runtime_session=session,
    )

    validation = validate_runtime_execution_lease_request(request)

    assert session["lease_id"] is None
    assert session["execution_lease_active"] is False
    assert validation["lease_created"] is False


def test_1218_invalid_session_cannot_get_lease():
    request = build_runtime_execution_lease_request(
        lease_request_id="lease-1218",
        runtime_session={"runtime_session_id": None, "session_type": "limited"},
        authorization_input={
            "decision": AUTHORIZED_LEASE_DECISION,
            "explicit_authorization": True,
            "authorize_lease_record": True,
        },
    )

    validation = validate_runtime_execution_lease_request(request)

    assert validation["lease_created"] is False
    assert "invalid_runtime_session" in validation["problems"]


def test_1219_unauthorized_request_creates_no_lease():
    request = build_runtime_execution_lease_request(
        lease_request_id="lease-1219",
        runtime_session=_session(),
        authorization_input={
            "decision": "NO_GO",
            "explicit_authorization": False,
            "authorize_lease_record": False,
        },
    )

    validation = validate_runtime_execution_lease_request(request)

    assert validation["lease_created"] is False
    assert "lease_authorization_missing" in validation["problems"]


def test_1220_authorized_request_creates_lease_record():
    validation = validate_runtime_execution_lease_request(_authorized_request())
    lease = validation["lease_record"]

    assert validation["lease_created"] is True
    assert lease["lease_id"] == (
        "execution-lease::limited-runtime-session::birth-1209::lease-1217"
    )
    assert lease["runtime_session_id"] == "limited-runtime-session::birth-1209"
    assert lease["lease_status"] == "granted"
    assert lease["allowed_statuses"] == list(LEASE_STATUSES)
    assert lease["lease_owner"]["operator_id"] == "operator-zero"


def test_1220_lease_does_not_start_executor_or_task():
    lease = validate_runtime_execution_lease_request(_authorized_request())["lease_record"]

    assert lease["executor_started"] is False
    assert lease["executor_start_allowed"] is False
    assert lease["task_execution_allowed"] is False
    assert lease["subprocess_allowed"] is False
    assert lease["tool_call_allowed"] is False


def test_1221_lease_cannot_mutate_state_or_io():
    lease = validate_runtime_execution_lease_request(_authorized_request())["lease_record"]

    assert lease["mutation_allowed"] is False
    assert lease["file_mutation_allowed"] is False
    assert lease["io_allowed"] is False
    assert lease["background_loop_allowed"] is False


def test_1222_lease_can_expire():
    lease = validate_runtime_execution_lease_request(_authorized_request())["lease_record"]
    expired = expire_runtime_execution_lease(lease, current_tick=1)

    assert expired["lease_status"] == "expired"
    assert expired["expiration_model"]["expired"] is True
    assert expired["execution_allowed"] is False


def test_1223_lease_can_revoke():
    lease = validate_runtime_execution_lease_request(_authorized_request())["lease_record"]
    revoked = revoke_runtime_execution_lease(lease, reason="operator_revoked")

    assert revoked["lease_status"] == "revoked"
    assert revoked["revocation_model"]["revoked"] is True
    assert revoked["revocation_model"]["revocation_reason"] == "operator_revoked"
    assert revoked["execution_allowed"] is False


def test_1224_expired_or_revoked_lease_cannot_authorize_execution():
    lease = validate_runtime_execution_lease_request(_authorized_request())["lease_record"]
    expired = expire_runtime_execution_lease(lease, current_tick=1)
    revoked = revoke_runtime_execution_lease(lease, reason="operator_revoked")

    expired_auth = can_runtime_execution_lease_authorize_execution(expired)
    revoked_auth = can_runtime_execution_lease_authorize_execution(revoked)

    assert expired_auth["can_authorize_execution"] is False
    assert expired_auth["blocked_reason"] == "lease_expired"
    assert revoked_auth["can_authorize_execution"] is False
    assert revoked_auth["blocked_reason"] == "lease_revoked"


def test_1224_granted_lease_still_has_zero_execution_capability():
    lease = validate_runtime_execution_lease_request(_authorized_request())["lease_record"]
    authorization = can_runtime_execution_lease_authorize_execution(lease)

    assert authorization["lease_status"] == "granted"
    assert authorization["can_authorize_execution"] is False
    assert authorization["blocked_reason"] == "execution_capability_not_granted"


def test_1224_heartbeat_projection_and_audit_are_data_only():
    validation = validate_runtime_execution_lease_request(_authorized_request())
    lease = validation["lease_record"]
    projection = build_runtime_execution_lease_heartbeat_projection(lease)
    audit = build_runtime_execution_lease_audit_record(_authorized_request())
    seal = build_runtime_execution_lease_milestone_seal(_authorized_request())

    assert projection["projection_only"] is True
    assert projection["heartbeat_live"] is False
    assert projection["background_loop_allowed"] is False
    assert audit["decision"] == "reserved_runtime_execution_lease_record_only"
    assert audit["lease_created"] is True
    assert audit["executor_started"] is False
    assert audit["task_executed"] is False
    assert audit["file_mutation_performed"] is False
    assert audit["io_performed"] is False
    assert seal["closed"] is True
    assert seal["next_package"] == 1225
    assert seal["all_execution_surfaces_locked"] is True
