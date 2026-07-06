from __future__ import annotations

from core.runtime.runtime_capability_grant import (
    AUTHORIZED_CAPABILITY_GRANT_DECISION,
    CAPABILITY_CATEGORIES,
    build_runtime_capability_audit_projection,
    build_runtime_capability_grant_audit_record,
    build_runtime_capability_grant_milestone_seal,
    build_runtime_capability_grant_request,
    can_runtime_capability_grant_authorize_executor,
    expire_runtime_capability_grant,
    revoke_runtime_capability_grant,
    validate_runtime_capability_grant_request,
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


def _authorized_request(**overrides):
    request = build_runtime_capability_grant_request(
        capability_request_id="capability-1225",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        authorization_input={
            "decision": AUTHORIZED_CAPABILITY_GRANT_DECISION,
            "explicit_authorization": True,
            "authorize_capability_record": True,
        },
        requested_capabilities=overrides.pop("requested_capabilities", None),
    )
    request.update(overrides)
    return request


def test_1225_session_default_has_no_capability():
    request = build_runtime_capability_grant_request(
        capability_request_id="capability-1225",
        runtime_session_id=_session_id(),
    )

    validation = validate_runtime_capability_grant_request(request)

    assert validation["grant_created"] is False
    assert validation["capability_grant_record"] is None


def test_1226_lease_default_has_no_capability():
    lease = _lease()

    assert lease.get("capabilities") is None
    assert lease["execution_allowed"] is False


def test_1227_invalid_lease_cannot_grant_capability():
    request = build_runtime_capability_grant_request(
        capability_request_id="capability-1227",
        runtime_session_id=_session_id(),
        execution_lease={**_lease(), "lease_status": "expired"},
        authorization_input={
            "decision": AUTHORIZED_CAPABILITY_GRANT_DECISION,
            "explicit_authorization": True,
            "authorize_capability_record": True,
        },
    )

    validation = validate_runtime_capability_grant_request(request)

    assert validation["grant_created"] is False
    assert "inactive_execution_lease" in validation["problems"]


def test_1228_unauthorized_request_creates_none():
    request = build_runtime_capability_grant_request(
        capability_request_id="capability-1228",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
    )

    validation = validate_runtime_capability_grant_request(request)

    assert validation["grant_created"] is False
    assert "capability_authorization_missing" in validation["problems"]


def test_1229_authorized_request_creates_capability_record():
    validation = validate_runtime_capability_grant_request(_authorized_request())
    grant = validation["capability_grant_record"]

    assert validation["grant_created"] is True
    assert grant["capability_grant_id"] == (
        "capability-grant::limited-runtime-session::birth-1209::"
        "execution-lease::limited-runtime-session::birth-1209::lease-1217::"
        "capability-1225"
    )
    assert grant["owner_session_id"] == _session_id()
    assert grant["owner_lease_id"] == _lease()["lease_id"]
    assert grant["grant_status"] == "granted"


def test_1230_all_capabilities_default_false():
    grant = validate_runtime_capability_grant_request(_authorized_request())[
        "capability_grant_record"
    ]

    for category in CAPABILITY_CATEGORIES:
        assert grant["granted_capabilities"][category] is False
        assert grant["denied_capabilities"][category] is True


def test_1231_grant_can_expire():
    grant = validate_runtime_capability_grant_request(_authorized_request())[
        "capability_grant_record"
    ]
    expired = expire_runtime_capability_grant(grant, current_tick=1)

    assert expired["grant_status"] == "expired"
    assert expired["expiration_model"]["expired"] is True
    assert expired["executor_start_allowed"] is False


def test_1231_grant_can_revoke():
    grant = validate_runtime_capability_grant_request(_authorized_request())[
        "capability_grant_record"
    ]
    revoked = revoke_runtime_capability_grant(grant, reason="operator_revoked")

    assert revoked["grant_status"] == "revoked"
    assert revoked["revocation_model"]["revoked"] is True
    assert revoked["revocation_model"]["revocation_reason"] == "operator_revoked"
    assert revoked["executor_start_allowed"] is False


def test_1232_revoked_or_expired_grant_cannot_authorize_executor():
    grant = validate_runtime_capability_grant_request(_authorized_request())[
        "capability_grant_record"
    ]
    expired = expire_runtime_capability_grant(grant, current_tick=1)
    revoked = revoke_runtime_capability_grant(grant, reason="operator_revoked")

    expired_auth = can_runtime_capability_grant_authorize_executor(expired)
    revoked_auth = can_runtime_capability_grant_authorize_executor(revoked)

    assert expired_auth["can_authorize_executor"] is False
    assert expired_auth["blocked_reason"] == "capability_grant_expired"
    assert revoked_auth["can_authorize_executor"] is False
    assert revoked_auth["blocked_reason"] == "capability_grant_revoked"


def test_1232_granted_capability_still_does_not_execute_anything():
    grant = validate_runtime_capability_grant_request(
        _authorized_request(requested_capabilities={"read_access": True})
    )["capability_grant_record"]
    authorization = can_runtime_capability_grant_authorize_executor(grant)

    assert authorization["can_authorize_executor"] is False
    assert authorization["blocked_reason"] == "executor_detached"
    assert grant["executor_started"] is False
    assert grant["task_execution_allowed"] is False
    assert grant["subprocess_allowed"] is False
    assert grant["file_mutation_allowed"] is False
    assert grant["io_allowed"] is False
    assert grant["tool_call_allowed"] is False
    assert grant["background_loop_allowed"] is False


def test_1232_capability_audit_projection_and_seal_are_data_only():
    validation = validate_runtime_capability_grant_request(_authorized_request())
    grant = validation["capability_grant_record"]
    projection = build_runtime_capability_audit_projection(grant)
    audit = build_runtime_capability_grant_audit_record(_authorized_request())
    seal = build_runtime_capability_grant_milestone_seal(_authorized_request())

    assert projection["projection_only"] is True
    assert projection["executor_start_allowed"] is False
    assert audit["decision"] == "reserved_runtime_capability_grant_record_only"
    assert audit["grant_created"] is True
    assert audit["executor_started"] is False
    assert audit["task_executed"] is False
    assert audit["file_mutation_performed"] is False
    assert audit["io_performed"] is False
    assert seal["closed"] is True
    assert seal["next_package"] == 1233
    assert seal["all_execution_surfaces_locked"] is True
