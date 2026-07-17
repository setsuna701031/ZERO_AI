from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_WRITE_PLANNING_SCHEMA = "zero.runtime.write_planning.v1"

WRITE_PLAN_STATUSES = ("planned", "denied", "expired", "revoked")

SUPPORTED_WRITE_OPERATIONS = ("create", "replace", "append", "delete")

REQUIRED_WRITE_PLAN_FIELDS = (
    "write_plan_request_id",
    "runtime_session_id",
    "execution_lease",
    "capability_grant",
    "executor_binding",
    "read_verification",
    "target_resource",
    "planned_operation",
    "expected_previous_digest",
    "planned_digest",
    "audit_required",
)

WRITE_PLANNING_LOCKS = {
    "file_write_allowed": False,
    "open_write_allowed": False,
    "append_allowed": False,
    "delete_allowed": False,
    "rename_allowed": False,
    "chmod_allowed": False,
    "mutation_allowed": False,
    "subprocess_allowed": False,
    "shell_allowed": False,
    "network_allowed": False,
    "task_execution_allowed": False,
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
    "no_digest_mismatch_required",
    "stale_evidence_blocked",
    "mutation_ownership_required",
    "rollback_preparation_required",
    "audit_evidence_required",
    "plan_only_no_filesystem_mutation",
    "open_write_locked",
    "append_locked",
    "delete_locked",
    "rename_locked",
    "chmod_locked",
    "subprocess_locked",
    "shell_locked",
    "network_locked",
    "task_execution_locked",
    "autonomy_locked",
    "background_loop_locked",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_WRITE_PLAN_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in WRITE_PLANNING_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _write_plan_id(
    request_id: str,
    session_id: str,
    verification_id: str,
    target_resource: str,
    planned_operation: str,
    planned_digest: str,
) -> str:
    fragment = _stable_fragment(
        {
            "request_id": request_id,
            "session_id": session_id,
            "verification_id": verification_id,
            "target_resource": target_resource,
            "planned_operation": planned_operation,
            "planned_digest": planned_digest,
        }
    )
    return f"write-plan::{session_id}::{verification_id}::{fragment}"


def build_runtime_write_plan_request(
    *,
    write_plan_request_id: str,
    runtime_session_id: str | None = None,
    execution_lease: dict[str, Any] | None = None,
    capability_grant: dict[str, Any] | None = None,
    executor_binding: dict[str, Any] | None = None,
    read_verification: dict[str, Any] | None = None,
    target_resource: str | None = None,
    planned_operation: str = "replace",
    expected_previous_digest: str | None = None,
    planned_digest: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_WRITE_PLANNING_SCHEMA,
        "write_plan_request_id": write_plan_request_id,
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
        "target_resource": target_resource,
        "planned_operation": planned_operation,
        "expected_previous_digest": expected_previous_digest,
        "planned_digest": planned_digest,
        "boundary_locks": deepcopy(WRITE_PLANNING_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def _evaluate_write_plan_request(record: dict[str, Any]) -> dict[str, Any]:
    session_id = record.get("runtime_session_id")
    lease = _as_mapping(record.get("execution_lease"))
    grant = _as_mapping(record.get("capability_grant"))
    binding = _as_mapping(record.get("executor_binding"))
    verification = _as_mapping(record.get("read_verification"))
    granted_capabilities = _as_mapping(grant.get("granted_capabilities"))

    lease_id = lease.get("lease_id")
    capability_grant_id = grant.get("capability_grant_id")
    executor_binding_id = binding.get("executor_binding_id")
    verification_id = verification.get("replay_verification_id")
    verification_status = verification.get("verification_status")
    target_resource = record.get("target_resource")
    planned_operation = record.get("planned_operation")
    expected_previous_digest = record.get("expected_previous_digest")
    planned_digest = record.get("planned_digest")

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
        bool(verification_id)
        and verification_status == "verified"
        and verification.get("mutation_readiness_allowed") is True
        and verification.get("mismatch_reason") in {None, "none"}
        and verification.get("stale_read_detected") is not True
    )
    digest_match = (
        bool(expected_previous_digest)
        and expected_previous_digest == verification.get("current_digest")
        and verification.get("original_digest") == verification.get("current_digest")
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
    if verification_status == "mismatch" or verification.get("stale_read_detected") is True:
        problems.append("stale_read_evidence")
    if verification_status == "expired":
        problems.append("read_evidence_expired")
    if verification_status == "revoked":
        problems.append("read_evidence_revoked")
    if verification_status not in {"verified", "mismatch", "expired", "revoked"}:
        problems.append("read_evidence_invalid")
    if not digest_match:
        problems.append("digest_mismatch")
    if not target_resource:
        problems.append("target_resource_required")
    if planned_operation not in SUPPORTED_WRITE_OPERATIONS:
        problems.append("unsupported_planned_operation")
    if not planned_digest:
        problems.append("planned_digest_required")

    return {
        "runtime_session_id": session_id,
        "execution_lease_id": lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "source_read_verification_id": verification_id,
        "target_resource": target_resource,
        "planned_operation": planned_operation,
        "expected_previous_digest": expected_previous_digest,
        "planned_digest": planned_digest,
        "verification_status": verification_status,
        "problems": problems,
    }


def validate_runtime_write_plan_request(request: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_write_plan_request(record)
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

    status = "planned" if not problems else "denied"
    if "read_evidence_expired" in problems:
        status = "expired"
    if "read_evidence_revoked" in problems:
        status = "revoked"

    return {
        "schema": RUNTIME_WRITE_PLANNING_SCHEMA,
        "valid": not problems,
        "write_plan_request_id": record.get("write_plan_request_id"),
        "runtime_session_id": evaluation["runtime_session_id"],
        "execution_lease_id": evaluation["execution_lease_id"],
        "capability_grant_id": evaluation["capability_grant_id"],
        "executor_binding_id": evaluation["executor_binding_id"],
        "source_read_verification_id": evaluation["source_read_verification_id"],
        "target_resource": evaluation["target_resource"],
        "planned_operation": evaluation["planned_operation"],
        "write_status": status,
        "denial_reason": "none" if not problems else ";".join(problems),
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "write_plan_created": not problems,
        "filesystem_mutation_performed": False,
        "file_write_performed": False,
        "open_write_performed": False,
        "append_performed": False,
        "delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
        "audit_required": True,
    }


def _rollback_metadata(
    *,
    target_resource: str | None,
    planned_operation: str | None,
    expected_previous_digest: str | None,
    planned_digest: str | None,
    source_read_verification_id: str | None,
) -> dict[str, Any]:
    inverse_operation = {
        "create": "delete_if_created",
        "replace": "restore_previous_digest",
        "append": "restore_previous_digest",
        "delete": "restore_previous_digest",
    }.get(str(planned_operation), "none")
    return {
        "rollback_prepared": True,
        "rollback_metadata_only": True,
        "target_resource": target_resource,
        "inverse_operation": inverse_operation,
        "restore_expected_previous_digest": expected_previous_digest,
        "planned_digest_to_revert": planned_digest,
        "source_read_verification_id": source_read_verification_id,
        "rollback_execution_allowed": False,
        "rollback_mutation_performed": False,
    }


def build_runtime_write_plan_record(request: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(request)
    validation = validate_runtime_write_plan_request(record)
    write_plan_id = _write_plan_id(
        str(record.get("write_plan_request_id")),
        str(validation.get("runtime_session_id")),
        str(validation.get("source_read_verification_id")),
        str(validation.get("target_resource")),
        str(validation.get("planned_operation")),
        str(record.get("planned_digest")),
    )
    plan = {
        "write_plan_id": write_plan_id,
        "runtime_session_id": validation["runtime_session_id"],
        "source_read_verification_id": validation["source_read_verification_id"],
        "target_resource": validation["target_resource"],
        "planned_operation": validation["planned_operation"],
        "expected_previous_digest": record.get("expected_previous_digest"),
        "planned_digest": record.get("planned_digest"),
        "write_status": validation["write_status"],
        "denial_reason": validation["denial_reason"],
        "audit_projection": {},
        "supported_operations": list(SUPPORTED_WRITE_OPERATIONS),
        "supported_statuses": list(WRITE_PLAN_STATUSES),
        "mutation_ownership": {
            "owner_session_id": validation["runtime_session_id"],
            "owner_lease_id": validation["execution_lease_id"],
            "capability_grant_id": validation["capability_grant_id"],
            "executor_binding_id": validation["executor_binding_id"],
            "ownership_verified": validation["valid"],
        },
        "rollback_preparation": _rollback_metadata(
            target_resource=validation["target_resource"],
            planned_operation=validation["planned_operation"],
            expected_previous_digest=record.get("expected_previous_digest"),
            planned_digest=record.get("planned_digest"),
            source_read_verification_id=validation["source_read_verification_id"],
        ),
        "audit_evidence": {
            "verified_read_evidence_required": True,
            "source_read_verification_id": validation["source_read_verification_id"],
            "verification_status": _as_mapping(record.get("read_verification")).get(
                "verification_status"
            ),
            "no_digest_mismatch": validation["valid"],
            "plan_only": True,
        },
        "plan_only": True,
        "filesystem_mutation_performed": False,
        "file_write_performed": False,
        "open_write_performed": False,
        "append_performed": False,
        "delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
    }
    plan["audit_projection"] = build_runtime_write_plan_audit_projection(plan)
    return plan


def build_runtime_write_plan_audit_projection(
    write_plan_record: dict[str, Any] | None,
) -> dict[str, Any]:
    plan = _as_mapping(write_plan_record)
    return {
        "projection": "runtime_write_planning_audit",
        "projection_only": True,
        "write_plan_id": plan.get("write_plan_id"),
        "runtime_session_id": plan.get("runtime_session_id"),
        "source_read_verification_id": plan.get("source_read_verification_id"),
        "target_resource": plan.get("target_resource"),
        "planned_operation": plan.get("planned_operation"),
        "write_status": plan.get("write_status", "denied"),
        "denial_reason": plan.get("denial_reason", "missing_write_plan"),
        "rollback_prepared": bool(
            _as_mapping(plan.get("rollback_preparation")).get("rollback_prepared")
        ),
        "audit_evidence_present": bool(plan.get("audit_evidence")),
        "plan_only": True,
        "filesystem_mutation_performed": False,
        "file_write_performed": False,
        "open_write_performed": False,
        "append_performed": False,
        "delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
    }


def build_runtime_write_plan_audit_record(request: dict[str, Any]) -> dict[str, Any]:
    validation = validate_runtime_write_plan_request(request)
    plan = build_runtime_write_plan_record(request)

    return {
        "audit_schema": RUNTIME_WRITE_PLANNING_SCHEMA + ".audit",
        "decision": "reserved_runtime_write_planning_plan_only",
        "write_plan_request_id": validation.get("write_plan_request_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "source_read_verification_id": validation.get("source_read_verification_id"),
        "request_valid": validation["valid"],
        "write_plan_created": validation["write_plan_created"],
        "write_plan_record": plan,
        "audit_projection": build_runtime_write_plan_audit_projection(plan),
        "filesystem_mutation_performed": False,
        "file_write_performed": False,
        "open_write_performed": False,
        "append_performed": False,
        "delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
        "non_mainline_issues": validation["problems"],
    }


def build_runtime_write_plan_milestone_seal(request: dict[str, Any]) -> dict[str, Any]:
    audit = build_runtime_write_plan_audit_record(request)
    plan = _as_mapping(audit.get("write_plan_record"))

    return {
        "seal": "runtime_write_planning_bundle",
        "schema": RUNTIME_WRITE_PLANNING_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_WRITE_PLANS_ONLY_ZERO_MUTATION",
        "next_package": 1289,
        "write_plan_id": plan.get("write_plan_id"),
        "write_status": plan.get("write_status"),
        "audit_decision": audit["decision"],
        "plan_only": True,
        "filesystem_mutation_performed": False,
        "file_write_performed": False,
        "open_write_performed": False,
        "append_performed": False,
        "delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
        "all_mutation_surfaces_locked": True,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


__all__ = [
    "RUNTIME_WRITE_PLANNING_SCHEMA",
    "WRITE_PLAN_STATUSES",
    "SUPPORTED_WRITE_OPERATIONS",
    "REQUIRED_WRITE_PLAN_FIELDS",
    "WRITE_PLANNING_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_runtime_write_plan_request",
    "validate_runtime_write_plan_request",
    "build_runtime_write_plan_record",
    "build_runtime_write_plan_audit_projection",
    "build_runtime_write_plan_audit_record",
    "build_runtime_write_plan_milestone_seal",
]
