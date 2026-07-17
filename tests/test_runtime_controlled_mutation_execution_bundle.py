from __future__ import annotations

from hashlib import sha256

from core.runtime.runtime_controlled_mutation_execution import (
    EMPTY_CONTENT_DIGEST,
    build_runtime_controlled_mutation_execution_request,
    build_runtime_controlled_mutation_milestone_seal,
    execute_runtime_controlled_mutation,
    validate_runtime_controlled_mutation_execution_request,
)
from core.runtime.runtime_mutation_approval_gate import (
    AUTHORIZED_MUTATION_APPROVAL_DECISION,
    DENIED_MUTATION_APPROVAL_DECISION,
    build_runtime_mutation_approval_record,
    build_runtime_mutation_approval_request,
    expire_runtime_mutation_approval,
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


def _verification(before_digest, **overrides):
    verification = {
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
    verification.update(overrides)
    return verification


def _write_plan(target, operation, before_digest, after_content, verification=None, **overrides):
    read_verification = verification or _verification(before_digest)
    request = build_runtime_write_plan_request(
        write_plan_request_id=f"write-plan-1281-{operation}-{target}",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        read_verification=read_verification,
        target_resource=target,
        planned_operation=operation,
        expected_previous_digest=before_digest,
        planned_digest=_digest(after_content),
    )
    request.update(overrides)
    return build_runtime_write_plan_record(request)


def _approval(write_plan, verification, *, denied=False):
    approval_input = (
        {
            "decision": DENIED_MUTATION_APPROVAL_DECISION,
            "explicit_denial": True,
            "approval_reason": "operator denied",
        }
        if denied
        else {
            "decision": AUTHORIZED_MUTATION_APPROVAL_DECISION,
            "explicit_approval": True,
            "approval_reason": "operator approved controlled mutation",
        }
    )
    request = build_runtime_mutation_approval_request(
        mutation_approval_request_id="mutation-approval-1289",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        read_verification=verification,
        write_plan=write_plan,
        approval_input=approval_input,
    )
    return build_runtime_mutation_approval_record(request)


def _request(tmp_path, *, target="target.txt", operation="replace", before="before", after="after", approval=None, write_plan=None, verification=None, controlled_executor=None):
    before_digest = EMPTY_CONTENT_DIGEST if operation == "create" else _digest(before)
    read_verification = verification or _verification(before_digest)
    plan = write_plan or _write_plan(target, operation, before_digest, after, read_verification)
    approval_record = _approval(plan, read_verification) if approval is None else approval
    request = build_runtime_controlled_mutation_execution_request(
        mutation_execution_request_id="mutation-execution-1297",
        runtime_session_id=_session_id(),
        execution_lease=_lease(),
        capability_grant=_grant(),
        executor_binding=_binding(),
        read_verification=read_verification,
        write_plan=plan,
        mutation_approval=approval_record,
        workspace_root=str(tmp_path),
        mutation_payload={"content": after},
    )
    if controlled_executor is not None:
        request["controlled_executor"] = controlled_executor
    return request


def test_1297_no_approval_blocks_mutation(tmp_path):
    request = _request(tmp_path, approval={})
    execution = execute_runtime_controlled_mutation(request)

    assert execution["execution_status"] == "blocked"
    assert "missing_mutation_approval" in execution["failure_reason"]


def test_1298_denied_approval_blocks_mutation(tmp_path):
    before = "before"
    verification = _verification(_digest(before))
    plan = _write_plan("target.txt", "replace", _digest(before), "after", verification)
    approval = _approval(plan, verification, denied=True)
    execution = execute_runtime_controlled_mutation(
        _request(tmp_path, approval=approval, write_plan=plan, verification=verification)
    )

    assert execution["execution_status"] == "blocked"
    assert "mutation_approval_denied" in execution["failure_reason"]


def test_1299_expired_approval_blocks_mutation(tmp_path):
    before = "before"
    verification = _verification(_digest(before))
    plan = _write_plan("target.txt", "replace", _digest(before), "after", verification)
    approval = expire_runtime_mutation_approval(_approval(plan, verification))
    execution = execute_runtime_controlled_mutation(
        _request(tmp_path, approval=approval, write_plan=plan, verification=verification)
    )

    assert execution["execution_status"] == "blocked"
    assert "mutation_approval_expired" in execution["failure_reason"]


def test_1300_digest_mismatch_blocks_mutation(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("changed", encoding="utf-8")
    request = _request(tmp_path, before="before", after="after")
    execution = execute_runtime_controlled_mutation(request)

    assert execution["execution_status"] == "failed"
    assert execution["failure_reason"] == "pre_mutation_digest_mismatch"
    assert target.read_text(encoding="utf-8") == "changed"


def test_1300_missing_rollback_metadata_blocks_mutation(tmp_path):
    before = "before"
    verification = _verification(_digest(before))
    plan = _write_plan("target.txt", "replace", _digest(before), "after", verification)
    plan["rollback_preparation"] = {}
    approval = _approval(plan, verification)
    validation = validate_runtime_controlled_mutation_execution_request(
        _request(tmp_path, write_plan=plan, approval=approval, verification=verification)
    )

    assert validation["execution_allowed"] is False
    assert "rollback_metadata_missing" in validation["problems"]


def test_1301_approved_create_executes_through_controlled_path(tmp_path):
    request = _request(
        tmp_path,
        target="created.txt",
        operation="create",
        before="",
        after="created content",
    )
    execution = execute_runtime_controlled_mutation(request)

    assert execution["execution_status"] == "succeeded"
    assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "created content"
    assert execution["operation"] == "create"
    assert execution["before_digest"] == EMPTY_CONTENT_DIGEST
    assert execution["after_digest"] == _digest("created content")
    assert execution["controlled_mutation_executor_used"] is True


def test_1302_approved_replace_executes_through_controlled_path(tmp_path):
    target = tmp_path / "target.txt"
    target.write_text("before", encoding="utf-8")
    execution = execute_runtime_controlled_mutation(
        _request(tmp_path, before="before", after="replacement")
    )

    assert execution["execution_status"] == "succeeded"
    assert target.read_text(encoding="utf-8") == "replacement"
    assert execution["operation"] == "replace"
    assert execution["before_digest"] == _digest("before")
    assert execution["after_digest"] == _digest("replacement")
    assert execution["atomic_mutation_path"] is True


def test_1303_mutation_creates_evidence(tmp_path):
    (tmp_path / "target.txt").write_text("before", encoding="utf-8")
    execution = execute_runtime_controlled_mutation(
        _request(tmp_path, before="before", after="after")
    )

    evidence = execution["evidence_after_mutation"]
    ownership = execution["mutation_ownership_audit"]

    assert evidence["evidence_recorded"] is True
    assert evidence["after_digest"] == _digest("after")
    assert evidence["content_included"] is False
    assert ownership["ownership_verified"] is True
    assert ownership["mutation_approval_id"] == execution["mutation_approval_id"]


def test_1303_mutation_creates_rollback_record(tmp_path):
    (tmp_path / "target.txt").write_text("before", encoding="utf-8")
    execution = execute_runtime_controlled_mutation(
        _request(tmp_path, before="before", after="after")
    )
    rollback = execution["rollback_record"]

    assert rollback["rollback_ready"] is True
    assert rollback["rollback_executed"] is False
    assert rollback["before_digest"] == _digest("before")
    assert rollback["after_digest"] == _digest("after")
    assert rollback["rollback_snapshot_metadata"]["content_included"] is False


def test_1304_direct_write_bypass_forbidden(tmp_path):
    request = _request(
        tmp_path,
        controlled_executor={
            "executor": "external_writer",
            "controlled_path_authorized": False,
            "direct_filesystem_bypass": True,
        },
    )
    validation = validate_runtime_controlled_mutation_execution_request(request)

    assert validation["execution_allowed"] is False
    assert "direct_write_bypass_forbidden" in validation["problems"]


def test_1304_delete_forbidden(tmp_path):
    (tmp_path / "target.txt").write_text("before", encoding="utf-8")
    request = _request(
        tmp_path,
        operation="delete",
        before="before",
        after="after",
    )
    execution = execute_runtime_controlled_mutation(request)

    assert execution["execution_status"] == "blocked"
    assert "delete_forbidden" in execution["failure_reason"]
    assert (tmp_path / "target.txt").read_text(encoding="utf-8") == "before"


def test_1304_command_execution_forbidden(tmp_path):
    (tmp_path / "target.txt").write_text("before", encoding="utf-8")
    execution = execute_runtime_controlled_mutation(
        _request(tmp_path, before="before", after="after")
    )
    seal = build_runtime_controlled_mutation_milestone_seal(
        _request(tmp_path, target="sealed.txt", operation="create", before="", after="sealed")
    )

    assert execution["shell_started"] is False
    assert execution["subprocess_started"] is False
    assert execution["network_performed"] is False
    assert execution["autonomy_started"] is False
    assert execution["background_loop_started"] is False
    assert seal["shell_started"] is False
    assert seal["subprocess_started"] is False
    assert seal["forbidden_surfaces_locked"] is True
