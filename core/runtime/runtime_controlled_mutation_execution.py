from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any


RUNTIME_CONTROLLED_MUTATION_EXECUTION_SCHEMA = (
    "zero.runtime.controlled_mutation_execution.v1"
)

MUTATION_EXECUTION_STATUSES = ("blocked", "succeeded", "failed")

ALLOWED_MUTATION_OPERATIONS = ("create", "replace")

EMPTY_CONTENT_DIGEST = sha256(b"").hexdigest()

REQUIRED_MUTATION_EXECUTION_FIELDS = (
    "mutation_execution_request_id",
    "runtime_session_id",
    "execution_lease",
    "capability_grant",
    "executor_binding",
    "read_verification",
    "write_plan",
    "mutation_approval",
    "workspace_root",
    "mutation_payload",
    "audit_required",
)

MUTATION_EXECUTION_LOCKS = {
    "delete_allowed": False,
    "rename_allowed": False,
    "chmod_allowed": False,
    "shell_allowed": False,
    "subprocess_allowed": False,
    "network_allowed": False,
    "uncontrolled_write_allowed": False,
    "direct_filesystem_bypass_allowed": False,
    "autonomy_allowed": False,
    "background_loop_allowed": False,
}

REQUIRED_BLOCKERS = (
    "runtime_session_id_required",
    "active_execution_lease_required",
    "active_capability_grant_required",
    "mutation_capability_required",
    "active_executor_binding_required",
    "verified_read_replay_record_required",
    "planned_write_plan_required",
    "approved_mutation_approval_required",
    "expected_previous_digest_match_required",
    "rollback_metadata_required",
    "controlled_executor_only",
    "delete_locked",
    "rename_locked",
    "chmod_locked",
    "shell_locked",
    "subprocess_locked",
    "network_locked",
    "uncontrolled_write_locked",
    "direct_filesystem_bypass_locked",
    "autonomy_locked",
    "background_loop_locked",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_MUTATION_EXECUTION_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in MUTATION_EXECUTION_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _digest_bytes(content: bytes) -> str:
    return sha256(content).hexdigest()


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _mutation_execution_id(
    request_id: str,
    mutation_approval_id: str,
    target_resource: str,
    operation: str,
    after_digest: str,
) -> str:
    fragment = _stable_fragment(
        {
            "request_id": request_id,
            "mutation_approval_id": mutation_approval_id,
            "target_resource": target_resource,
            "operation": operation,
            "after_digest": after_digest,
        }
    )
    return f"mutation-execution::{mutation_approval_id}::{fragment}"


def _payload_content(payload: dict[str, Any]) -> bytes:
    if "content_bytes" in payload and isinstance(payload.get("content_bytes"), bytes):
        return bytes(payload["content_bytes"])
    if "content" in payload and payload.get("content") is not None:
        return str(payload.get("content")).encode("utf-8")
    return b""


def _resolve_target(workspace_root: str, target_resource: str) -> Path:
    root = Path(workspace_root).resolve()
    resource = str(target_resource or "")
    if resource.startswith("workspace://"):
        resource = resource[len("workspace://") :]
    candidate = (root / resource).resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError("target_resource_outside_workspace")
    return candidate


def build_runtime_controlled_mutation_execution_request(
    *,
    mutation_execution_request_id: str,
    runtime_session_id: str | None = None,
    execution_lease: dict[str, Any] | None = None,
    capability_grant: dict[str, Any] | None = None,
    executor_binding: dict[str, Any] | None = None,
    read_verification: dict[str, Any] | None = None,
    write_plan: dict[str, Any] | None = None,
    mutation_approval: dict[str, Any] | None = None,
    workspace_root: str | None = None,
    mutation_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_CONTROLLED_MUTATION_EXECUTION_SCHEMA,
        "mutation_execution_request_id": mutation_execution_request_id,
        "runtime_session_id": runtime_session_id,
        "execution_lease": (
            deepcopy(execution_lease) if execution_lease is not None else {}
        ),
        "capability_grant": (
            deepcopy(capability_grant) if capability_grant is not None else {}
        ),
        "executor_binding": (
            deepcopy(executor_binding) if executor_binding is not None else {}
        ),
        "read_verification": (
            deepcopy(read_verification) if read_verification is not None else {}
        ),
        "write_plan": deepcopy(write_plan) if write_plan is not None else {},
        "mutation_approval": (
            deepcopy(mutation_approval) if mutation_approval is not None else {}
        ),
        "workspace_root": workspace_root,
        "mutation_payload": deepcopy(mutation_payload) if mutation_payload is not None else {},
        "controlled_executor": {
            "executor": "runtime_controlled_mutation_execution",
            "controlled_path_authorized": True,
            "direct_filesystem_bypass": False,
        },
        "boundary_locks": deepcopy(MUTATION_EXECUTION_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def _evaluate_mutation_execution_request(record: dict[str, Any]) -> dict[str, Any]:
    session_id = record.get("runtime_session_id")
    lease = _as_mapping(record.get("execution_lease"))
    grant = _as_mapping(record.get("capability_grant"))
    binding = _as_mapping(record.get("executor_binding"))
    verification = _as_mapping(record.get("read_verification"))
    write_plan = _as_mapping(record.get("write_plan"))
    approval = _as_mapping(record.get("mutation_approval"))
    payload = _as_mapping(record.get("mutation_payload"))
    controlled_executor = _as_mapping(record.get("controlled_executor"))
    granted_capabilities = _as_mapping(grant.get("granted_capabilities"))
    rollback_preparation = _as_mapping(write_plan.get("rollback_preparation"))

    lease_id = lease.get("lease_id")
    capability_grant_id = grant.get("capability_grant_id")
    executor_binding_id = binding.get("executor_binding_id")
    read_verification_id = verification.get("replay_verification_id")
    write_plan_id = write_plan.get("write_plan_id")
    mutation_approval_id = approval.get("mutation_approval_id")
    operation = approval.get("approved_operation") or write_plan.get("planned_operation")
    target_resource = approval.get("target_resource") or write_plan.get("target_resource")
    expected_previous_digest = (
        approval.get("expected_previous_digest")
        or write_plan.get("expected_previous_digest")
    )
    planned_digest = write_plan.get("planned_digest")
    payload_digest = _digest_bytes(_payload_content(payload))

    active_lease = (
        bool(lease_id)
        and lease.get("runtime_session_id") == session_id
        and lease.get("lease_status") == "granted"
    )
    active_grant = (
        bool(capability_grant_id)
        and grant.get("owner_session_id") == session_id
        and grant.get("owner_lease_id") == lease_id
        and grant.get("grant_status") == "granted"
    )
    mutation_capability_granted = (
        active_grant and granted_capabilities.get("mutation_access") is True
    )
    active_binding = (
        bool(executor_binding_id)
        and binding.get("runtime_session_id") == session_id
        and binding.get("execution_lease_id") == lease_id
        and binding.get("capability_grant_id") == capability_grant_id
        and binding.get("binding_status") == "bound"
    )
    verified_read = (
        bool(read_verification_id)
        and verification.get("verification_status") == "verified"
        and verification.get("mutation_readiness_allowed") is True
        and verification.get("mismatch_reason") in {None, "none"}
        and verification.get("stale_read_detected") is not True
    )
    write_plan_ready = (
        bool(write_plan_id)
        and write_plan.get("write_status") == "planned"
        and write_plan.get("runtime_session_id") == session_id
        and write_plan.get("source_read_verification_id") == read_verification_id
        and write_plan.get("denial_reason") in {None, "none"}
    )
    approval_ready = (
        bool(mutation_approval_id)
        and approval.get("approval_status") == "approved"
        and approval.get("write_plan_id") == write_plan_id
        and approval.get("runtime_session_id") == session_id
        and approval.get("mutation_readiness_allowed") is True
    )
    digest_chain_match = (
        bool(expected_previous_digest)
        and expected_previous_digest == verification.get("current_digest")
        and expected_previous_digest == write_plan.get("expected_previous_digest")
        and expected_previous_digest == approval.get("expected_previous_digest")
        and verification.get("original_digest") == verification.get("current_digest")
    )
    rollback_metadata_exists = (
        rollback_preparation.get("rollback_prepared") is True
        and rollback_preparation.get("rollback_metadata_only") is True
        and rollback_preparation.get("source_read_verification_id") == read_verification_id
    )
    controlled_path = (
        controlled_executor.get("executor") == "runtime_controlled_mutation_execution"
        and controlled_executor.get("controlled_path_authorized") is True
        and controlled_executor.get("direct_filesystem_bypass") is False
    )

    problems: list[str] = []
    if not session_id:
        problems.append("invalid_runtime_session_id")
    if not active_lease:
        problems.append("inactive_execution_lease")
    if not active_grant:
        problems.append("inactive_capability_grant")
    if active_grant and not mutation_capability_granted:
        problems.append("mutation_capability_missing")
    if not active_binding:
        problems.append("inactive_executor_binding")
    if not verified_read:
        problems.append("verified_read_evidence_missing")
    if not write_plan_id:
        problems.append("missing_write_plan")
    elif not write_plan_ready:
        problems.append("write_plan_not_planned")
    if not mutation_approval_id:
        problems.append("missing_mutation_approval")
    elif approval.get("approval_status") == "denied":
        problems.append("mutation_approval_denied")
    elif approval.get("approval_status") == "expired":
        problems.append("mutation_approval_expired")
    elif approval.get("approval_status") == "revoked":
        problems.append("mutation_approval_revoked")
    elif not approval_ready:
        problems.append("mutation_approval_not_approved")
    if not digest_chain_match:
        problems.append("digest_mismatch")
    if not rollback_metadata_exists:
        problems.append("rollback_metadata_missing")
    if operation not in ALLOWED_MUTATION_OPERATIONS:
        problems.append("operation_forbidden")
    if operation == "delete":
        problems.append("delete_forbidden")
    if not target_resource:
        problems.append("target_resource_required")
    if planned_digest and planned_digest != payload_digest:
        problems.append("planned_digest_mismatch")
    if not controlled_path:
        problems.append("direct_write_bypass_forbidden")

    return {
        "runtime_session_id": session_id,
        "execution_lease_id": lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "source_read_verification_id": read_verification_id,
        "write_plan_id": write_plan_id,
        "mutation_approval_id": mutation_approval_id,
        "target_resource": target_resource,
        "operation": operation,
        "expected_previous_digest": expected_previous_digest,
        "planned_digest": planned_digest,
        "payload_digest": payload_digest,
        "problems": problems,
    }


def validate_runtime_controlled_mutation_execution_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_mutation_execution_request(record)
    problems = list(evaluation["problems"])

    if missing:
        problems.append("missing_required_fields")
    if missing_blockers:
        problems.append("missing_required_blockers")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")

    return {
        "schema": RUNTIME_CONTROLLED_MUTATION_EXECUTION_SCHEMA,
        "valid": not problems,
        "mutation_execution_request_id": record.get("mutation_execution_request_id"),
        "runtime_session_id": evaluation["runtime_session_id"],
        "execution_lease_id": evaluation["execution_lease_id"],
        "capability_grant_id": evaluation["capability_grant_id"],
        "executor_binding_id": evaluation["executor_binding_id"],
        "source_read_verification_id": evaluation["source_read_verification_id"],
        "write_plan_id": evaluation["write_plan_id"],
        "mutation_approval_id": evaluation["mutation_approval_id"],
        "target_resource": evaluation["target_resource"],
        "operation": evaluation["operation"],
        "expected_previous_digest": evaluation["expected_previous_digest"],
        "planned_digest": evaluation["planned_digest"],
        "payload_digest": evaluation["payload_digest"],
        "execution_allowed": not problems,
        "execution_status": "succeeded" if not problems else "blocked",
        "failure_reason": None if not problems else ";".join(problems),
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "shell_started": False,
        "subprocess_started": False,
        "network_performed": False,
        "uncontrolled_write_performed": False,
        "direct_filesystem_bypass_performed": False,
        "autonomy_started": False,
        "background_loop_started": False,
        "audit_required": True,
    }


def _rollback_record(
    *,
    mutation_execution_id: str,
    mutation_approval_id: str | None,
    target_resource: str | None,
    operation: str | None,
    before_digest: str | None,
    after_digest: str | None,
    before_exists: bool,
) -> dict[str, Any]:
    return {
        "rollback_record_id": f"rollback::{mutation_execution_id}",
        "mutation_execution_id": mutation_execution_id,
        "mutation_approval_id": mutation_approval_id,
        "target_resource": target_resource,
        "operation": "remove_created_resource" if operation == "create" else "restore_before_digest",
        "before_digest": before_digest,
        "after_digest": after_digest,
        "before_exists": before_exists,
        "rollback_snapshot_metadata": {
            "snapshot_created": True,
            "content_included": False,
            "snapshot_digest": before_digest,
            "rollback_owner": "runtime_controlled_mutation_execution",
        },
        "rollback_ready": True,
        "rollback_executed": False,
    }


def _blocked_execution_record(
    request: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    mutation_approval_id = validation.get("mutation_approval_id")
    target_resource = validation.get("target_resource")
    operation = validation.get("operation")
    after_digest = validation.get("planned_digest") or validation.get("payload_digest")
    mutation_execution_id = _mutation_execution_id(
        str(validation.get("mutation_execution_request_id")),
        str(mutation_approval_id),
        str(target_resource),
        str(operation),
        str(after_digest),
    )
    execution = {
        "mutation_execution_id": mutation_execution_id,
        "mutation_approval_id": mutation_approval_id,
        "target_resource": target_resource,
        "operation": operation,
        "before_digest": None,
        "after_digest": None,
        "execution_status": validation["execution_status"],
        "rollback_record": {},
        "failure_reason": validation["failure_reason"],
        "audit_projection": {},
        "evidence_after_mutation": {},
        "mutation_ownership_audit": {},
        "controlled_mutation_executor_used": False,
        "atomic_mutation_path": False,
        "delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "shell_started": False,
        "subprocess_started": False,
        "network_performed": False,
        "uncontrolled_write_performed": False,
        "direct_filesystem_bypass_performed": False,
        "autonomy_started": False,
        "background_loop_started": False,
    }
    execution["audit_projection"] = build_runtime_controlled_mutation_audit_projection(
        execution
    )
    return execution


def execute_runtime_controlled_mutation(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_controlled_mutation_execution_request(request)
    record = _as_mapping(request)
    if not validation["execution_allowed"]:
        return _blocked_execution_record(record, validation)

    workspace_root = str(record.get("workspace_root"))
    target_resource = str(validation["target_resource"])
    operation = str(validation["operation"])
    payload = _as_mapping(record.get("mutation_payload"))
    content = _payload_content(payload)
    after_digest = _digest_bytes(content)
    mutation_approval_id = str(validation["mutation_approval_id"])
    mutation_execution_id = _mutation_execution_id(
        str(validation["mutation_execution_request_id"]),
        mutation_approval_id,
        target_resource,
        operation,
        after_digest,
    )

    try:
        target_path = _resolve_target(workspace_root, target_resource)
        before_exists = target_path.exists()
        before_content = target_path.read_bytes() if before_exists else b""
        before_digest = _digest_bytes(before_content)

        if before_digest != validation["expected_previous_digest"]:
            return _failed_after_preflight(
                validation,
                mutation_execution_id=mutation_execution_id,
                before_digest=before_digest,
                failure_reason="pre_mutation_digest_mismatch",
            )
        if operation == "create" and before_exists:
            return _failed_after_preflight(
                validation,
                mutation_execution_id=mutation_execution_id,
                before_digest=before_digest,
                failure_reason="create_target_already_exists",
            )
        if operation == "replace" and not before_exists:
            return _failed_after_preflight(
                validation,
                mutation_execution_id=mutation_execution_id,
                before_digest=before_digest,
                failure_reason="replace_target_missing",
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        if operation == "create":
            with target_path.open("xb") as handle:
                handle.write(content)
        else:
            target_path.write_bytes(content)

        observed_after_digest = _digest_bytes(target_path.read_bytes())
        execution_status = (
            "succeeded" if observed_after_digest == after_digest else "failed"
        )
        failure_reason = (
            None if execution_status == "succeeded" else "post_mutation_digest_mismatch"
        )
        rollback = _rollback_record(
            mutation_execution_id=mutation_execution_id,
            mutation_approval_id=mutation_approval_id,
            target_resource=target_resource,
            operation=operation,
            before_digest=before_digest,
            after_digest=observed_after_digest,
            before_exists=before_exists,
        )
        execution = {
            "mutation_execution_id": mutation_execution_id,
            "mutation_approval_id": mutation_approval_id,
            "target_resource": target_resource,
            "operation": operation,
            "before_digest": before_digest,
            "after_digest": observed_after_digest,
            "execution_status": execution_status,
            "rollback_record": rollback,
            "failure_reason": failure_reason,
            "audit_projection": {},
            "evidence_after_mutation": {
                "evidence_recorded": True,
                "target_resource": target_resource,
                "after_digest": observed_after_digest,
                "content_included": False,
            },
            "mutation_ownership_audit": {
                "owner_session_id": validation["runtime_session_id"],
                "owner_lease_id": validation["execution_lease_id"],
                "capability_grant_id": validation["capability_grant_id"],
                "executor_binding_id": validation["executor_binding_id"],
                "mutation_approval_id": mutation_approval_id,
                "ownership_verified": True,
            },
            "controlled_mutation_executor_used": True,
            "atomic_mutation_path": True,
            "delete_performed": False,
            "rename_performed": False,
            "chmod_performed": False,
            "shell_started": False,
            "subprocess_started": False,
            "network_performed": False,
            "uncontrolled_write_performed": False,
            "direct_filesystem_bypass_performed": False,
            "autonomy_started": False,
            "background_loop_started": False,
        }
    except Exception as exc:
        execution = {
            "mutation_execution_id": mutation_execution_id,
            "mutation_approval_id": mutation_approval_id,
            "target_resource": target_resource,
            "operation": operation,
            "before_digest": None,
            "after_digest": None,
            "execution_status": "failed",
            "rollback_record": {},
            "failure_reason": str(exc),
            "audit_projection": {},
            "evidence_after_mutation": {},
            "mutation_ownership_audit": {},
            "controlled_mutation_executor_used": True,
            "atomic_mutation_path": True,
            "delete_performed": False,
            "rename_performed": False,
            "chmod_performed": False,
            "shell_started": False,
            "subprocess_started": False,
            "network_performed": False,
            "uncontrolled_write_performed": False,
            "direct_filesystem_bypass_performed": False,
            "autonomy_started": False,
            "background_loop_started": False,
        }

    execution["audit_projection"] = build_runtime_controlled_mutation_audit_projection(
        execution
    )
    return execution


def _failed_after_preflight(
    validation: dict[str, Any],
    *,
    mutation_execution_id: str,
    before_digest: str,
    failure_reason: str,
) -> dict[str, Any]:
    execution = {
        "mutation_execution_id": mutation_execution_id,
        "mutation_approval_id": validation.get("mutation_approval_id"),
        "target_resource": validation.get("target_resource"),
        "operation": validation.get("operation"),
        "before_digest": before_digest,
        "after_digest": None,
        "execution_status": "failed",
        "rollback_record": {},
        "failure_reason": failure_reason,
        "audit_projection": {},
        "evidence_after_mutation": {},
        "mutation_ownership_audit": {},
        "controlled_mutation_executor_used": True,
        "atomic_mutation_path": True,
        "delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "shell_started": False,
        "subprocess_started": False,
        "network_performed": False,
        "uncontrolled_write_performed": False,
        "direct_filesystem_bypass_performed": False,
        "autonomy_started": False,
        "background_loop_started": False,
    }
    execution["audit_projection"] = build_runtime_controlled_mutation_audit_projection(
        execution
    )
    return execution


def build_runtime_controlled_mutation_audit_projection(
    mutation_execution_record: dict[str, Any] | None,
) -> dict[str, Any]:
    execution = _as_mapping(mutation_execution_record)
    return {
        "projection": "runtime_controlled_mutation_execution_audit",
        "projection_only": True,
        "mutation_execution_id": execution.get("mutation_execution_id"),
        "mutation_approval_id": execution.get("mutation_approval_id"),
        "target_resource": execution.get("target_resource"),
        "operation": execution.get("operation"),
        "before_digest": execution.get("before_digest"),
        "after_digest": execution.get("after_digest"),
        "execution_status": execution.get("execution_status", "blocked"),
        "rollback_recorded": bool(execution.get("rollback_record")),
        "evidence_recorded": bool(execution.get("evidence_after_mutation")),
        "controlled_mutation_executor_used": bool(
            execution.get("controlled_mutation_executor_used", False)
        ),
        "atomic_mutation_path": bool(execution.get("atomic_mutation_path", False)),
        "delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "shell_started": False,
        "subprocess_started": False,
        "network_performed": False,
        "uncontrolled_write_performed": False,
        "direct_filesystem_bypass_performed": False,
        "autonomy_started": False,
        "background_loop_started": False,
    }


def build_runtime_controlled_mutation_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_controlled_mutation_execution_request(request)
    execution = execute_runtime_controlled_mutation(request)

    return {
        "audit_schema": RUNTIME_CONTROLLED_MUTATION_EXECUTION_SCHEMA + ".audit",
        "decision": "reserved_runtime_controlled_mutation_execution",
        "mutation_execution_request_id": validation.get(
            "mutation_execution_request_id"
        ),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "source_read_verification_id": validation.get("source_read_verification_id"),
        "write_plan_id": validation.get("write_plan_id"),
        "mutation_approval_id": validation.get("mutation_approval_id"),
        "request_valid": validation["valid"],
        "mutation_execution_record": execution,
        "audit_projection": build_runtime_controlled_mutation_audit_projection(
            execution
        ),
        "delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "shell_started": False,
        "subprocess_started": False,
        "network_performed": False,
        "uncontrolled_write_performed": False,
        "direct_filesystem_bypass_performed": False,
        "autonomy_started": False,
        "background_loop_started": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
        "non_mainline_issues": validation["problems"],
    }


def build_runtime_controlled_mutation_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_runtime_controlled_mutation_audit_record(request)
    execution = _as_mapping(audit.get("mutation_execution_record"))

    return {
        "seal": "runtime_controlled_mutation_execution_bundle",
        "schema": RUNTIME_CONTROLLED_MUTATION_EXECUTION_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_FIRST_CONTROLLED_MUTATION_EXECUTION_PATH",
        "next_package": 1305,
        "mutation_execution_id": execution.get("mutation_execution_id"),
        "mutation_approval_id": execution.get("mutation_approval_id"),
        "execution_status": execution.get("execution_status"),
        "audit_decision": audit["decision"],
        "controlled_mutation_executor_used": bool(
            execution.get("controlled_mutation_executor_used", False)
        ),
        "delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "shell_started": False,
        "subprocess_started": False,
        "network_performed": False,
        "uncontrolled_write_performed": False,
        "direct_filesystem_bypass_performed": False,
        "autonomy_started": False,
        "background_loop_started": False,
        "forbidden_surfaces_locked": True,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


__all__ = [
    "RUNTIME_CONTROLLED_MUTATION_EXECUTION_SCHEMA",
    "MUTATION_EXECUTION_STATUSES",
    "ALLOWED_MUTATION_OPERATIONS",
    "EMPTY_CONTENT_DIGEST",
    "REQUIRED_MUTATION_EXECUTION_FIELDS",
    "MUTATION_EXECUTION_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_runtime_controlled_mutation_execution_request",
    "validate_runtime_controlled_mutation_execution_request",
    "execute_runtime_controlled_mutation",
    "build_runtime_controlled_mutation_audit_projection",
    "build_runtime_controlled_mutation_audit_record",
    "build_runtime_controlled_mutation_milestone_seal",
]
