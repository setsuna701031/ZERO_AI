from __future__ import annotations

from core.runtime.runtime_mutation_approval_gate import (
    AUTHORIZED_MUTATION_APPROVAL_DECISION,
    DENIED_MUTATION_APPROVAL_DECISION,
    build_runtime_mutation_approval_audit_record,
    build_runtime_mutation_approval_milestone_seal,
    build_runtime_mutation_approval_record,
    build_runtime_mutation_approval_request,
    can_runtime_mutation_approval_authorize_readiness,
    expire_runtime_mutation_approval,
    revoke_runtime_mutation_approval,
    validate_runtime_mutation_approval_request,
)
from core.runtime.runtime_write_planning import (
    build_runtime_write_plan_record,
    build_runtime_write_plan_request,
)


def _session_id():
    return "limited-runtime-session::birth-1209"


def _lease():
    return {
        "lease_id": "execution-lease::limited-runtime-session::birth-1209::lease-1217",
        "runtime_session_id": _session_id(),
        "lease_status": "granted",
    }


def _grant(mutation_access=True):
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
            "mutation_access": mutation_access,
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


def _digest(value="a"):
    return value * 64


def _verification(**overrides):
    verification = {
        "replay_verification_id": (
            "read-replay-verification::read-execution::read-adapter::README.md::"
            "read-execution-1265::read-replay-1273"
        ),
        "read_execution_id": "read-execution::read-adapter::README.md::read-execution-1265",
        "original_digest": _digest(),
        "current_digest": _digest(),
        "verification_status": "verified",
        "mismatch_reason": "none",
        "stale_read_detected": False,
        "mutation_readiness_allowed": True,
    }
    verification.update(overrides)
    return verification


def _write_plan(**overrides):
    request = build_runtime_write_plan_request(
        write_plan_request_id="write-plan-1281",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        read_verification=_verification(),
        target_resource="README.md",
        planned_operation="replace",
        expected_previous_digest=_digest(),
        planned_digest=_digest("b"),
    )
    request.update(overrides)
    return build_runtime_write_plan_record(request)


def _approval_input():
    return {
        "decision": AUTHORIZED_MUTATION_APPROVAL_DECISION,
        "explicit_approval": True,
        "approval_reason": "operator approved planned digest transition",
    }


def _denial_input():
    return {
        "decision": DENIED_MUTATION_APPROVAL_DECISION,
        "explicit_denial": True,
        "approval_reason": "operator denied mutation readiness",
    }


def _request(**overrides):
    request = build_runtime_mutation_approval_request(
        mutation_approval_request_id="mutation-approval-1289",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        read_verification=_verification(),
        write_plan=_write_plan(),
        approval_input=_approval_input(),
    )
    request.update(overrides)
    return request


def test_1289_no_write_plan_blocks_approval():
    record = build_runtime_mutation_approval_record(_request(write_plan={}))

    assert record["approval_status"] == "denied"
    assert "missing_write_plan" in record["denial_reason"]
    assert record["mutation_readiness_allowed"] is False


def test_1290_invalid_session_blocks_approval():
    validation = validate_runtime_mutation_approval_request(
        _request(runtime_session_id=None)
    )

    assert validation["valid"] is False
    assert "invalid_runtime_session_id" in validation["problems"]


def test_1291_invalid_lease_blocks_approval():
    validation = validate_runtime_mutation_approval_request(
        _request(execution_lease={**_lease(), "lease_status": "expired"})
    )

    assert validation["valid"] is False
    assert "inactive_execution_lease" in validation["problems"]


def test_1292_invalid_capability_blocks_approval():
    validation = validate_runtime_mutation_approval_request(
        _request(capability_grant={**_grant(), "grant_status": "revoked"})
    )

    assert validation["valid"] is False
    assert "inactive_capability_grant" in validation["problems"]


def test_1293_invalid_executor_blocks_approval():
    validation = validate_runtime_mutation_approval_request(
        _request(executor_binding={**_binding(), "binding_status": "revoked"})
    )

    assert validation["valid"] is False
    assert "inactive_executor_binding" in validation["problems"]


def test_1294_missing_mutation_capability_blocks_approval():
    validation = validate_runtime_mutation_approval_request(
        _request(capability_grant=_grant(mutation_access=False))
    )

    assert validation["valid"] is False
    assert "mutation_capability_missing" in validation["problems"]


def test_1294_stale_mismatched_evidence_blocks_approval():
    mismatch = _verification(
        current_digest=_digest("c"),
        verification_status="mismatch",
        mismatch_reason="content_digest_changed",
        stale_read_detected=True,
        mutation_readiness_allowed=False,
    )
    record = build_runtime_mutation_approval_record(
        _request(read_verification=mismatch)
    )

    assert record["approval_status"] == "denied"
    assert "stale_or_mismatched_evidence" in record["denial_reason"]
    assert "digest_mismatch" in record["denial_reason"]
    assert record["mutation_readiness_allowed"] is False


def test_1295_explicit_denial_creates_denied_record():
    record = build_runtime_mutation_approval_record(
        _request(approval_input=_denial_input())
    )

    assert record["approval_status"] == "denied"
    assert record["denial_reason"] == "explicit_denial"
    assert record["approval_reason"] == ""
    assert record["mutation_readiness_allowed"] is False


def test_1295_explicit_approval_creates_approval_record_only():
    validation = validate_runtime_mutation_approval_request(_request())
    record = build_runtime_mutation_approval_record(_request())

    assert validation["valid"] is True
    assert record["mutation_approval_id"].startswith("mutation-approval::")
    assert record["write_plan_id"] == _write_plan()["write_plan_id"]
    assert record["runtime_session_id"] == _session_id()
    assert record["approval_status"] == "approved"
    assert record["approved_operation"] == "replace"
    assert record["target_resource"] == "README.md"
    assert record["expected_previous_digest"] == _digest()
    assert record["approval_reason"] == _approval_input()["approval_reason"]
    assert record["denial_reason"] == "none"
    assert record["rollback_required"] is True
    assert record["approval_record_only"] is True
    assert record["audit_projection"]["projection_only"] is True


def test_1295_approval_does_not_modify_files(tmp_path):
    target = tmp_path / "approval-target.txt"
    target.write_text("before", encoding="utf-8")

    record = build_runtime_mutation_approval_record(_request())
    audit = build_runtime_mutation_approval_audit_record(_request())

    assert target.read_text(encoding="utf-8") == "before"
    assert record["filesystem_mutation_performed"] is False
    assert record["file_write_performed"] is False
    assert record["append_performed"] is False
    assert record["delete_performed"] is False
    assert record["rename_performed"] is False
    assert record["chmod_performed"] is False
    assert audit["filesystem_mutation_performed"] is False


def test_1296_revoked_expired_approval_blocks_mutation_readiness():
    approval = build_runtime_mutation_approval_record(_request())
    expired = expire_runtime_mutation_approval(approval)
    revoked = revoke_runtime_mutation_approval(approval, reason="operator_revoked")

    expired_readiness = can_runtime_mutation_approval_authorize_readiness(expired)
    revoked_readiness = can_runtime_mutation_approval_authorize_readiness(revoked)

    assert expired["approval_status"] == "expired"
    assert revoked["approval_status"] == "revoked"
    assert expired_readiness["mutation_readiness_allowed"] is False
    assert revoked_readiness["mutation_readiness_allowed"] is False
    assert expired_readiness["mutation_execution_allowed"] is False
    assert revoked_readiness["mutation_execution_allowed"] is False


def test_1296_approval_cannot_execute_commands():
    record = build_runtime_mutation_approval_record(_request())
    audit = build_runtime_mutation_approval_audit_record(_request())
    seal = build_runtime_mutation_approval_milestone_seal(_request())

    assert record["subprocess_started"] is False
    assert record["shell_started"] is False
    assert record["network_performed"] is False
    assert record["task_executed"] is False
    assert record["autonomy_started"] is False
    assert record["background_loop_started"] is False
    assert audit["subprocess_started"] is False
    assert audit["shell_started"] is False
    assert seal["closed"] is True
    assert seal["all_mutation_surfaces_locked"] is True
