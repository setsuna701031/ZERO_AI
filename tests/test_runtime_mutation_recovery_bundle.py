from __future__ import annotations

from hashlib import sha256

from core.runtime.runtime_controlled_mutation_execution import (
    build_runtime_controlled_mutation_execution_request,
    execute_runtime_controlled_mutation,
)
from core.runtime.runtime_mutation_approval_gate import (
    AUTHORIZED_MUTATION_APPROVAL_DECISION,
    build_runtime_mutation_approval_record,
    build_runtime_mutation_approval_request,
)
from core.runtime.runtime_mutation_recovery import (
    build_runtime_mutation_recovery_audit_record,
    build_runtime_mutation_recovery_record,
    execute_runtime_mutation_recovery,
    validate_runtime_mutation_recovery_request,
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


def _digest(content: bytes | str):
    data = content.encode("utf-8") if isinstance(content, str) else content
    return sha256(data).hexdigest()


def _verification(before_digest):
    return {
        "replay_verification_id": (
            "read-replay-verification::read-execution::read-adapter::target::"
            "read-execution-1265::read-replay-1273"
        ),
        "read_execution_id": "read-execution::read-adapter::target::read-execution-1265",
        "original_digest": before_digest,
        "current_digest": before_digest,
        "verification_status": "verified",
        "mismatch_reason": "none",
        "stale_read_detected": False,
        "mutation_readiness_allowed": True,
    }


def _write_plan(target, operation, before_digest, after_content, verification):
    request = build_runtime_write_plan_request(
        write_plan_request_id=f"write-plan-1281-{operation}-{target}",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        read_verification=verification,
        target_resource=target,
        planned_operation=operation,
        expected_previous_digest=before_digest,
        planned_digest=_digest(after_content),
    )
    return build_runtime_write_plan_record(request)


def _approval(write_plan, verification):
    request = build_runtime_mutation_approval_request(
        mutation_approval_request_id="mutation-approval-1289",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        read_verification=verification,
        write_plan=write_plan,
        approval_input={
            "decision": AUTHORIZED_MUTATION_APPROVAL_DECISION,
            "explicit_approval": True,
            "approval_reason": "operator approved controlled mutation",
        },
    )
    return build_runtime_mutation_approval_record(request)


def _mutation_execution(tmp_path, *, target="target.txt", before="before", after="after"):
    (tmp_path / target).write_text(before, encoding="utf-8")
    before_digest = _digest(before)
    verification = _verification(before_digest)
    plan = _write_plan(target, "replace", before_digest, after, verification)
    approval = _approval(plan, verification)
    request = build_runtime_controlled_mutation_execution_request(
        mutation_execution_request_id="mutation-execution-1297",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        read_verification=verification,
        write_plan=plan,
        mutation_approval=approval,
        workspace_root=str(tmp_path),
        mutation_payload={"content": after},
    )
    return execute_runtime_controlled_mutation(request)


def _recovery_request(tmp_path, execution, *, before="before", rollback_source=None):
    return {
        "mutation_execution_id": execution["mutation_execution_id"],
        "mutation_execution_record": execution,
        "rollback_record": execution["rollback_record"],
        "rollback_source": rollback_source
        or {
            "source_type": "inline_before_content",
            "target_resource": execution["target_resource"],
            "before_content": before,
            "before_digest": _digest(before),
        },
        "workspace_root": str(tmp_path),
        "before_digest": execution["before_digest"],
        "after_digest": execution["after_digest"],
        "mutation_ownership_evidence": execution["mutation_ownership_audit"],
        "recovery_reason": "operator requested controlled rollback",
    }


def test_1305_no_mutation_record_blocks_recovery(tmp_path):
    request = _recovery_request(tmp_path, _mutation_execution(tmp_path))
    request["mutation_execution_record"] = {}

    record = build_runtime_mutation_recovery_record(request)

    assert record["recovery_status"] == "denied"
    assert "mutation_record_missing" in record["failure_reason"]


def test_1306_missing_rollback_blocks_recovery(tmp_path):
    execution = _mutation_execution(tmp_path)
    request = _recovery_request(tmp_path, execution)
    request["rollback_record"] = {}

    validation = validate_runtime_mutation_recovery_request(request)

    assert validation["valid"] is False
    assert "rollback_record_missing" in validation["problems"]


def test_1307_invalid_ownership_blocks_recovery(tmp_path):
    execution = _mutation_execution(tmp_path)
    request = _recovery_request(tmp_path, execution)
    request["mutation_ownership_evidence"] = {
        **execution["mutation_ownership_audit"],
        "ownership_verified": False,
    }

    record = build_runtime_mutation_recovery_record(request)

    assert record["recovery_status"] == "denied"
    assert "mutation_ownership_invalid" in record["failure_reason"]


def test_1308_corrupted_rollback_blocks_recovery(tmp_path):
    execution = _mutation_execution(tmp_path)
    request = _recovery_request(tmp_path, execution)
    request["rollback_record"] = {
        **execution["rollback_record"],
        "after_digest": _digest("tampered"),
    }

    record = build_runtime_mutation_recovery_record(request)

    assert record["recovery_status"] == "denied"
    assert "rollback_after_digest_mismatch" in record["failure_reason"]


def test_1309_valid_mutation_creates_recovery_plan(tmp_path):
    execution = _mutation_execution(tmp_path)
    record = build_runtime_mutation_recovery_record(_recovery_request(tmp_path, execution))

    assert record["mutation_recovery_id"].startswith("mutation-recovery::")
    assert record["mutation_execution_id"] == execution["mutation_execution_id"]
    assert record["recovery_status"] == "planned"
    assert record["rollback_source"]["source_type"] == "inline_before_content"
    assert record["audit_projection"]["rollback_integrity_verified"] is True


def test_1310_recovery_restores_controlled_mutation(tmp_path):
    execution = _mutation_execution(tmp_path, before="before", after="after")
    restored = execute_runtime_mutation_recovery(
        _recovery_request(tmp_path, execution, before="before")
    )

    assert restored["recovery_status"] == "restored"
    assert restored["restored_digest"] == _digest("before")
    assert (tmp_path / "target.txt").read_text(encoding="utf-8") == "before"


def test_1311_recovery_creates_audit_evidence(tmp_path):
    execution = _mutation_execution(tmp_path)
    audit = build_runtime_mutation_recovery_audit_record(
        _recovery_request(tmp_path, execution)
    )

    assert audit["audit_schema"] == "zero.runtime.mutation_recovery.v1.audit"
    assert audit["recovery_record"]["audit_projection"]["ownership_chain_validated"] is True
    assert audit["recovery_record"]["audit_projection"]["recovery_audit_evidence"] is True
    assert audit["arbitrary_write_performed"] is False


def test_1311_recovery_cannot_modify_unrelated_file(tmp_path):
    execution = _mutation_execution(tmp_path)
    (tmp_path / "other.txt").write_text("keep", encoding="utf-8")
    request = _recovery_request(tmp_path, execution)
    request["rollback_source"] = {
        **request["rollback_source"],
        "target_resource": "other.txt",
    }

    restored = execute_runtime_mutation_recovery(request)

    assert restored["recovery_status"] == "denied"
    assert "rollback_source_target_mismatch" in restored["failure_reason"]
    assert (tmp_path / "other.txt").read_text(encoding="utf-8") == "keep"


def test_1312_recovery_cannot_execute_commands(tmp_path):
    execution = _mutation_execution(tmp_path)
    restored = execute_runtime_mutation_recovery(_recovery_request(tmp_path, execution))
    audit = build_runtime_mutation_recovery_audit_record(
        _recovery_request(tmp_path, execution)
    )

    assert restored["shell_started"] is False
    assert restored["subprocess_started"] is False
    assert restored["network_performed"] is False
    assert restored["autonomy_started"] is False
    assert restored["background_loop_started"] is False
    assert audit["shell_started"] is False
    assert audit["subprocess_started"] is False


def test_1312_recovery_cannot_bypass_mutation_chain(tmp_path):
    execution = _mutation_execution(tmp_path)
    request = _recovery_request(tmp_path, execution)
    request["mutation_execution_id"] = "mutation-execution::forged"

    validation = validate_runtime_mutation_recovery_request(request)

    assert validation["valid"] is False
    assert "mutation_execution_id_mismatch" in validation["problems"]
