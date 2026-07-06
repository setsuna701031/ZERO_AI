from __future__ import annotations

from core.runtime.runtime_write_planning import (
    build_runtime_write_plan_audit_record,
    build_runtime_write_plan_milestone_seal,
    build_runtime_write_plan_record,
    build_runtime_write_plan_request,
    validate_runtime_write_plan_request,
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


def _request(**overrides):
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
    return request


def test_1281_no_read_verification_blocks_write_plan():
    validation = validate_runtime_write_plan_request(_request(read_verification={}))
    record = build_runtime_write_plan_record(_request(read_verification={}))

    assert validation["valid"] is False
    assert record["write_status"] == "denied"
    assert "verified_read_evidence_missing" in record["denial_reason"]


def test_1282_mismatch_read_blocks_write_plan():
    mismatch = _verification(
        current_digest=_digest("c"),
        verification_status="mismatch",
        mismatch_reason="content_digest_changed",
        stale_read_detected=True,
        mutation_readiness_allowed=False,
    )
    record = build_runtime_write_plan_record(_request(read_verification=mismatch))

    assert record["write_status"] == "denied"
    assert "stale_read_evidence" in record["denial_reason"]
    assert "digest_mismatch" in record["denial_reason"]


def test_1283_invalid_session_blocks_plan():
    validation = validate_runtime_write_plan_request(_request(runtime_session_id=None))

    assert validation["valid"] is False
    assert "invalid_runtime_session_id" in validation["problems"]


def test_1284_invalid_lease_blocks_plan():
    validation = validate_runtime_write_plan_request(
        _request(execution_lease={**_lease(), "lease_status": "expired"})
    )

    assert validation["valid"] is False
    assert validation["write_status"] == "denied"
    assert "inactive_execution_lease" in validation["problems"]


def test_1285_invalid_capability_blocks_plan():
    validation = validate_runtime_write_plan_request(
        _request(capability_grant={**_grant(), "grant_status": "revoked"})
    )

    assert validation["valid"] is False
    assert "inactive_capability_grant" in validation["problems"]


def test_1286_missing_mutation_capability_blocks_plan():
    validation = validate_runtime_write_plan_request(
        _request(capability_grant=_grant(mutation_access=False))
    )

    assert validation["valid"] is False
    assert "mutation_capability_missing" in validation["problems"]


def test_1287_valid_chain_creates_write_plan():
    validation = validate_runtime_write_plan_request(_request())
    record = build_runtime_write_plan_record(_request())

    assert validation["valid"] is True
    assert validation["write_plan_created"] is True
    assert record["write_plan_id"].startswith("write-plan::")
    assert record["runtime_session_id"] == _session_id()
    assert record["source_read_verification_id"] == _verification()["replay_verification_id"]
    assert record["target_resource"] == "README.md"
    assert record["planned_operation"] == "replace"
    assert record["expected_previous_digest"] == _digest()
    assert record["planned_digest"] == _digest("b")
    assert record["write_status"] == "planned"
    assert record["denial_reason"] == "none"
    assert record["audit_projection"]["projection_only"] is True


def test_1287_write_plan_does_not_modify_files():
    record = build_runtime_write_plan_record(_request())
    audit = build_runtime_write_plan_audit_record(_request())

    assert record["plan_only"] is True
    assert record["filesystem_mutation_performed"] is False
    assert record["file_write_performed"] is False
    assert record["open_write_performed"] is False
    assert record["append_performed"] is False
    assert record["delete_performed"] is False
    assert record["rename_performed"] is False
    assert record["chmod_performed"] is False
    assert audit["filesystem_mutation_performed"] is False


def test_1288_write_plan_cannot_execute_commands():
    record = build_runtime_write_plan_record(_request())
    audit = build_runtime_write_plan_audit_record(_request())
    seal = build_runtime_write_plan_milestone_seal(_request())

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


def test_1288_write_plan_creates_rollback_metadata():
    record = build_runtime_write_plan_record(_request(planned_operation="delete"))
    rollback = record["rollback_preparation"]

    assert rollback["rollback_prepared"] is True
    assert rollback["rollback_metadata_only"] is True
    assert rollback["inverse_operation"] == "restore_previous_digest"
    assert rollback["restore_expected_previous_digest"] == _digest()
    assert rollback["planned_digest_to_revert"] == _digest("b")
    assert rollback["rollback_execution_allowed"] is False
    assert rollback["rollback_mutation_performed"] is False
