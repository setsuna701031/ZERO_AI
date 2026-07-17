from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_MUTATION_APPROVAL_GATE_SCHEMA = "zero.runtime.mutation_approval_gate.v1"

AUTHORIZED_MUTATION_APPROVAL_DECISION = "APPROVE_MUTATION_PLAN_RECORD_ONLY"
DENIED_MUTATION_APPROVAL_DECISION = "DENY_MUTATION_PLAN_RECORD_ONLY"

MUTATION_APPROVAL_STATUSES = ("approved", "denied", "expired", "revoked")

REQUIRED_MUTATION_APPROVAL_FIELDS = (
    "mutation_approval_request_id",
    "runtime_session_id",
    "execution_lease",
    "capability_grant",
    "executor_binding",
    "read_verification",
    "write_plan",
    "approval_input",
    "audit_required",
)

MUTATION_APPROVAL_LOCKS = {
    "file_write_allowed": False,
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
    "write_plan_required",
    "write_plan_status_planned_required",
    "explicit_approval_input_required",
    "stale_or_mismatch_evidence_blocked",
    "approval_record_only",
    "file_write_locked",
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
    return [field for field in REQUIRED_MUTATION_APPROVAL_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in MUTATION_APPROVAL_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _approval_id(
    request_id: str,
    session_id: str,
    write_plan_id: str,
    approval_decision: str,
) -> str:
    fragment = _stable_fragment(
        {
            "request_id": request_id,
            "session_id": session_id,
            "write_plan_id": write_plan_id,
            "approval_decision": approval_decision,
        }
    )
    return f"mutation-approval::{session_id}::{write_plan_id}::{fragment}"


def build_runtime_mutation_approval_request(
    *,
    mutation_approval_request_id: str,
    runtime_session_id: str | None = None,
    execution_lease: dict[str, Any] | None = None,
    capability_grant: dict[str, Any] | None = None,
    executor_binding: dict[str, Any] | None = None,
    read_verification: dict[str, Any] | None = None,
    write_plan: dict[str, Any] | None = None,
    approval_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_MUTATION_APPROVAL_GATE_SCHEMA,
        "mutation_approval_request_id": mutation_approval_request_id,
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
        "approval_input": (
            deepcopy(approval_input)
            if approval_input is not None
            else {
                "decision": "NO_GO",
                "explicit_approval": False,
                "approval_reason": "",
            }
        ),
        "boundary_locks": deepcopy(MUTATION_APPROVAL_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def _evaluate_mutation_approval_request(record: dict[str, Any]) -> dict[str, Any]:
    session_id = record.get("runtime_session_id")
    lease = _as_mapping(record.get("execution_lease"))
    grant = _as_mapping(record.get("capability_grant"))
    binding = _as_mapping(record.get("executor_binding"))
    verification = _as_mapping(record.get("read_verification"))
    write_plan = _as_mapping(record.get("write_plan"))
    approval_input = _as_mapping(record.get("approval_input"))
    granted_capabilities = _as_mapping(grant.get("granted_capabilities"))

    lease_id = lease.get("lease_id")
    capability_grant_id = grant.get("capability_grant_id")
    executor_binding_id = binding.get("executor_binding_id")
    read_verification_id = verification.get("replay_verification_id")
    verification_status = verification.get("verification_status")
    write_plan_id = write_plan.get("write_plan_id")
    write_plan_status = write_plan.get("write_status")
    planned_operation = write_plan.get("planned_operation")
    target_resource = write_plan.get("target_resource")
    expected_previous_digest = write_plan.get("expected_previous_digest")
    decision = approval_input.get("decision")

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
        and verification_status == "verified"
        and verification.get("mutation_readiness_allowed") is True
        and verification.get("mismatch_reason") in {None, "none"}
        and verification.get("stale_read_detected") is not True
    )
    write_plan_ready = (
        bool(write_plan_id)
        and write_plan_status == "planned"
        and write_plan.get("runtime_session_id") == session_id
        and write_plan.get("source_read_verification_id") == read_verification_id
        and write_plan.get("denial_reason") in {None, "none"}
    )
    digest_match = (
        bool(expected_previous_digest)
        and expected_previous_digest == verification.get("current_digest")
        and verification.get("original_digest") == verification.get("current_digest")
    )
    explicit_approval = (
        decision == AUTHORIZED_MUTATION_APPROVAL_DECISION
        and approval_input.get("explicit_approval") is True
    )
    explicit_denial = (
        decision == DENIED_MUTATION_APPROVAL_DECISION
        and approval_input.get("explicit_denial") is True
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
        problems.append("stale_or_mismatched_evidence")
    if verification_status == "expired":
        problems.append("read_evidence_expired")
    if verification_status == "revoked":
        problems.append("read_evidence_revoked")
    if verification_status not in {"verified", "mismatch", "expired", "revoked"}:
        problems.append("read_evidence_invalid")
    if not digest_match:
        problems.append("digest_mismatch")
    if not write_plan_id:
        problems.append("missing_write_plan")
    elif not write_plan_ready:
        problems.append("write_plan_not_planned")
    if not explicit_approval and not explicit_denial:
        problems.append("explicit_approval_input_missing")

    return {
        "runtime_session_id": session_id,
        "execution_lease_id": lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "source_read_verification_id": read_verification_id,
        "write_plan_id": write_plan_id,
        "write_plan_status": write_plan_status,
        "approved_operation": planned_operation,
        "target_resource": target_resource,
        "expected_previous_digest": expected_previous_digest,
        "approval_decision": decision,
        "approval_reason": str(approval_input.get("approval_reason") or ""),
        "explicit_approval": explicit_approval,
        "explicit_denial": explicit_denial,
        "problems": problems,
    }


def validate_runtime_mutation_approval_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_mutation_approval_request(record)
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

    approval_input_ok = evaluation["explicit_approval"] or evaluation["explicit_denial"]
    chain_problems = [problem for problem in problems if problem != "explicit_denial"]
    approval_status = "denied"
    if "read_evidence_expired" in problems:
        approval_status = "expired"
    elif "read_evidence_revoked" in problems:
        approval_status = "revoked"
    elif not problems and evaluation["explicit_approval"]:
        approval_status = "approved"
    elif approval_input_ok:
        approval_status = "denied"

    readiness = approval_status == "approved"

    return {
        "schema": RUNTIME_MUTATION_APPROVAL_GATE_SCHEMA,
        "valid": readiness,
        "mutation_approval_request_id": record.get("mutation_approval_request_id"),
        "runtime_session_id": evaluation["runtime_session_id"],
        "execution_lease_id": evaluation["execution_lease_id"],
        "capability_grant_id": evaluation["capability_grant_id"],
        "executor_binding_id": evaluation["executor_binding_id"],
        "source_read_verification_id": evaluation["source_read_verification_id"],
        "write_plan_id": evaluation["write_plan_id"],
        "approval_status": approval_status,
        "approved_operation": evaluation["approved_operation"],
        "target_resource": evaluation["target_resource"],
        "expected_previous_digest": evaluation["expected_previous_digest"],
        "approval_reason": evaluation["approval_reason"] if readiness else "",
        "denial_reason": "none" if readiness else ";".join(problems or ["explicit_denial"]),
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "approval_record_created": approval_input_ok or bool(chain_problems),
        "mutation_readiness_allowed": readiness,
        "filesystem_mutation_performed": False,
        "file_write_performed": False,
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


def build_runtime_mutation_approval_record(request: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(request)
    validation = validate_runtime_mutation_approval_request(record)
    approval_decision = _as_mapping(record.get("approval_input")).get("decision", "")
    approval = {
        "mutation_approval_id": _approval_id(
            str(record.get("mutation_approval_request_id")),
            str(validation.get("runtime_session_id")),
            str(validation.get("write_plan_id")),
            str(approval_decision),
        ),
        "write_plan_id": validation["write_plan_id"],
        "runtime_session_id": validation["runtime_session_id"],
        "approval_status": validation["approval_status"],
        "approved_operation": validation["approved_operation"],
        "target_resource": validation["target_resource"],
        "expected_previous_digest": validation["expected_previous_digest"],
        "approval_reason": validation["approval_reason"],
        "denial_reason": validation["denial_reason"],
        "rollback_required": validation["approval_status"] == "approved",
        "audit_projection": {},
        "supported_statuses": list(MUTATION_APPROVAL_STATUSES),
        "source_read_verification_id": validation["source_read_verification_id"],
        "execution_lease_id": validation["execution_lease_id"],
        "capability_grant_id": validation["capability_grant_id"],
        "executor_binding_id": validation["executor_binding_id"],
        "mutation_readiness_allowed": validation["mutation_readiness_allowed"],
        "approval_record_only": True,
        "filesystem_mutation_performed": False,
        "file_write_performed": False,
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
    approval["audit_projection"] = build_runtime_mutation_approval_audit_projection(
        approval
    )
    return approval


def build_runtime_mutation_approval_audit_projection(
    approval_record: dict[str, Any] | None,
) -> dict[str, Any]:
    approval = _as_mapping(approval_record)
    return {
        "projection": "runtime_mutation_approval_gate_audit",
        "projection_only": True,
        "mutation_approval_id": approval.get("mutation_approval_id"),
        "write_plan_id": approval.get("write_plan_id"),
        "runtime_session_id": approval.get("runtime_session_id"),
        "approval_status": approval.get("approval_status", "denied"),
        "target_resource": approval.get("target_resource"),
        "approved_operation": approval.get("approved_operation"),
        "mutation_readiness_allowed": bool(
            approval.get("mutation_readiness_allowed", False)
        ),
        "rollback_required": bool(approval.get("rollback_required", False)),
        "approval_record_only": True,
        "filesystem_mutation_performed": False,
        "file_write_performed": False,
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


def expire_runtime_mutation_approval(
    approval_record: dict[str, Any],
    *,
    reason: str = "approval_expired",
) -> dict[str, Any]:
    approval = _as_mapping(approval_record)
    approval["approval_status"] = "expired"
    approval["denial_reason"] = reason
    approval["approval_reason"] = ""
    approval["mutation_readiness_allowed"] = False
    approval["rollback_required"] = False
    approval["audit_projection"] = build_runtime_mutation_approval_audit_projection(
        approval
    )
    return approval


def revoke_runtime_mutation_approval(
    approval_record: dict[str, Any],
    *,
    reason: str,
) -> dict[str, Any]:
    approval = _as_mapping(approval_record)
    approval["approval_status"] = "revoked"
    approval["denial_reason"] = reason
    approval["approval_reason"] = ""
    approval["mutation_readiness_allowed"] = False
    approval["rollback_required"] = False
    approval["audit_projection"] = build_runtime_mutation_approval_audit_projection(
        approval
    )
    return approval


def can_runtime_mutation_approval_authorize_readiness(
    approval_record: dict[str, Any],
) -> dict[str, Any]:
    approval = _as_mapping(approval_record)
    status = approval.get("approval_status", "denied")
    return {
        "mutation_approval_id": approval.get("mutation_approval_id"),
        "write_plan_id": approval.get("write_plan_id"),
        "approval_status": status,
        "mutation_readiness_allowed": status == "approved",
        "mutation_execution_allowed": False,
        "blocked": status != "approved",
        "blocked_reason": "none" if status == "approved" else f"approval_{status}",
        "filesystem_mutation_performed": False,
        "subprocess_started": False,
        "shell_started": False,
    }


def build_runtime_mutation_approval_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_mutation_approval_request(request)
    approval = build_runtime_mutation_approval_record(request)

    return {
        "audit_schema": RUNTIME_MUTATION_APPROVAL_GATE_SCHEMA + ".audit",
        "decision": "reserved_runtime_mutation_approval_gate_record_only",
        "mutation_approval_request_id": validation.get(
            "mutation_approval_request_id"
        ),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "source_read_verification_id": validation.get("source_read_verification_id"),
        "write_plan_id": validation.get("write_plan_id"),
        "request_valid": validation["valid"],
        "approval_record": approval,
        "audit_projection": build_runtime_mutation_approval_audit_projection(approval),
        "mutation_readiness_allowed": validation["mutation_readiness_allowed"],
        "filesystem_mutation_performed": False,
        "file_write_performed": False,
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


def build_runtime_mutation_approval_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_runtime_mutation_approval_audit_record(request)
    approval = _as_mapping(audit.get("approval_record"))

    return {
        "seal": "runtime_mutation_approval_gate_bundle",
        "schema": RUNTIME_MUTATION_APPROVAL_GATE_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_MUTATION_APPROVAL_RECORDS_ONLY_ZERO_MUTATION",
        "next_package": 1297,
        "mutation_approval_id": approval.get("mutation_approval_id"),
        "write_plan_id": approval.get("write_plan_id"),
        "approval_status": approval.get("approval_status"),
        "audit_decision": audit["decision"],
        "approval_record_only": True,
        "filesystem_mutation_performed": False,
        "file_write_performed": False,
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
    "RUNTIME_MUTATION_APPROVAL_GATE_SCHEMA",
    "AUTHORIZED_MUTATION_APPROVAL_DECISION",
    "DENIED_MUTATION_APPROVAL_DECISION",
    "MUTATION_APPROVAL_STATUSES",
    "REQUIRED_MUTATION_APPROVAL_FIELDS",
    "MUTATION_APPROVAL_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_runtime_mutation_approval_request",
    "validate_runtime_mutation_approval_request",
    "build_runtime_mutation_approval_record",
    "build_runtime_mutation_approval_audit_projection",
    "expire_runtime_mutation_approval",
    "revoke_runtime_mutation_approval",
    "can_runtime_mutation_approval_authorize_readiness",
    "build_runtime_mutation_approval_audit_record",
    "build_runtime_mutation_approval_milestone_seal",
]
