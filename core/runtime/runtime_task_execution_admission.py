from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


RUNTIME_TASK_EXECUTION_ADMISSION_SCHEMA = (
    "zero.runtime.task_execution_admission.v1"
)

TASK_ADMISSION_STATUSES = ("admitted", "denied", "expired", "revoked")

SUPPORTED_TASK_TYPES = (
    "read_task",
    "write_task",
    "mutation_task",
    "recovery_task",
)

REQUIRED_TASK_ADMISSION_FIELDS = (
    "task_admission_request_id",
    "runtime_session_id",
    "execution_lease",
    "capability_grant",
    "executor_binding",
    "tool_boundary",
    "tool_invocation",
    "requested_task_id",
    "requested_task_type",
    "authorization_input",
    "audit_required",
)

TASK_ADMISSION_LOCKS = {
    "task_execution_allowed": False,
    "subprocess_allowed": False,
    "shell_allowed": False,
    "network_allowed": False,
    "uncontrolled_mutation_allowed": False,
    "autonomy_allowed": False,
    "self_start_allowed": False,
    "background_loop_allowed": False,
}

AUTHORIZED_TASK_ADMISSION_DECISION = "AUTHORIZE_TASK_ADMISSION_RECORD_ONLY"


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_TASK_ADMISSION_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in TASK_ADMISSION_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _task_admission_id(
    *,
    request_id: str,
    session_id: str,
    lease_id: str,
    grant_id: str,
    binding_id: str,
    tool_boundary_id: str,
    tool_invocation_id: str,
    task_id: str,
    task_type: str,
) -> str:
    fragment = _stable_fragment(
        {
            "request_id": request_id,
            "session_id": session_id,
            "lease_id": lease_id,
            "grant_id": grant_id,
            "binding_id": binding_id,
            "tool_boundary_id": tool_boundary_id,
            "tool_invocation_id": tool_invocation_id,
            "task_id": task_id,
            "task_type": task_type,
        }
    )
    return f"task-admission::{session_id}::{task_id}::{fragment}"


def build_runtime_task_execution_admission_request(
    *,
    task_admission_request_id: str,
    runtime_session_id: str | None = None,
    execution_lease: dict[str, Any] | None = None,
    capability_grant: dict[str, Any] | None = None,
    executor_binding: dict[str, Any] | None = None,
    tool_boundary: dict[str, Any] | None = None,
    tool_invocation: dict[str, Any] | None = None,
    requested_task_id: str | None = None,
    requested_task_type: str = "read_task",
    mutation_recovery: dict[str, Any] | None = None,
    evidence_freshness: dict[str, Any] | None = None,
    authorization_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_TASK_EXECUTION_ADMISSION_SCHEMA,
        "task_admission_request_id": task_admission_request_id,
        "runtime_session_id": runtime_session_id,
        "execution_lease": _as_mapping(execution_lease),
        "capability_grant": _as_mapping(capability_grant),
        "executor_binding": _as_mapping(executor_binding),
        "tool_boundary": _as_mapping(tool_boundary),
        "tool_invocation": _as_mapping(tool_invocation),
        "requested_task_id": requested_task_id,
        "requested_task_type": requested_task_type,
        "mutation_recovery": _as_mapping(mutation_recovery),
        "evidence_freshness": (
            _as_mapping(evidence_freshness)
            if evidence_freshness is not None
            else {"stale_evidence_detected": False}
        ),
        "authorization_input": (
            _as_mapping(authorization_input)
            if authorization_input is not None
            else {
                "decision": "NO_GO",
                "explicit_task_admission_authorization": False,
                "authorize_task_admission_record": False,
            }
        ),
        "boundary_locks": deepcopy(TASK_ADMISSION_LOCKS),
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


def _evaluate_task_admission_request(record: dict[str, Any]) -> dict[str, Any]:
    session_id = record.get("runtime_session_id")
    lease = _as_mapping(record.get("execution_lease"))
    grant = _as_mapping(record.get("capability_grant"))
    binding = _as_mapping(record.get("executor_binding"))
    boundary = _as_mapping(record.get("tool_boundary"))
    invocation = _as_mapping(record.get("tool_invocation"))
    recovery = _as_mapping(record.get("mutation_recovery"))
    freshness = _as_mapping(record.get("evidence_freshness"))
    authorization = _as_mapping(record.get("authorization_input"))
    granted_capabilities = _as_mapping(grant.get("granted_capabilities"))

    lease_id = lease.get("lease_id")
    grant_id = grant.get("capability_grant_id")
    binding_id = binding.get("executor_binding_id")
    tool_boundary_id = boundary.get("tool_boundary_id")
    tool_invocation_id = invocation.get("tool_invocation_id")
    requested_task_id = record.get("requested_task_id")
    requested_task_type = record.get("requested_task_type")

    active_lease = (
        bool(lease_id)
        and lease.get("runtime_session_id") == session_id
        and lease.get("lease_status") == "granted"
    )
    active_grant = (
        bool(grant_id)
        and grant.get("owner_session_id") == session_id
        and grant.get("owner_lease_id") == lease_id
        and grant.get("grant_status") == "granted"
    )
    active_binding = (
        bool(binding_id)
        and binding.get("runtime_session_id") == session_id
        and binding.get("execution_lease_id") == lease_id
        and binding.get("capability_grant_id") == grant_id
        and binding.get("binding_status") == "bound"
    )
    admitted_boundary = (
        bool(tool_boundary_id)
        and boundary.get("runtime_session_id") == session_id
        and boundary.get("execution_lease_id") == lease_id
        and boundary.get("capability_grant_id") == grant_id
        and boundary.get("executor_binding_id") == binding_id
        and boundary.get("tool_boundary_status") == "admitted"
        and boundary.get("admission_granted") is True
    )
    approved_invocation = (
        bool(tool_invocation_id)
        and invocation.get("runtime_session_id") == session_id
        and invocation.get("execution_lease_id") == lease_id
        and invocation.get("capability_grant_id") == grant_id
        and invocation.get("executor_binding_id") == binding_id
        and invocation.get("tool_boundary_id") == tool_boundary_id
        and invocation.get("invocation_status") == "approved"
        and invocation.get("actual_tool_executed") is False
    )
    authorized = (
        authorization.get("decision") == AUTHORIZED_TASK_ADMISSION_DECISION
        and authorization.get("explicit_task_admission_authorization") is True
        and authorization.get("authorize_task_admission_record") is True
    )
    recovery_ready = (
        bool(recovery.get("mutation_recovery_id"))
        and recovery.get("recovery_status") in {"planned", "restored"}
        and _as_mapping(recovery.get("audit_projection")).get(
            "ownership_chain_validated"
        )
        is True
        and _as_mapping(recovery.get("audit_projection")).get(
            "rollback_integrity_verified"
        )
        is True
    )
    stale_evidence = (
        freshness.get("stale_evidence_detected") is True
        or freshness.get("evidence_status") in {"stale", "expired", "revoked"}
        or invocation.get("invocation_status") in {"expired", "revoked", "failed"}
        or boundary.get("tool_boundary_status") in {"expired", "revoked"}
        or lease.get("lease_status") in {"expired", "revoked"}
        or grant.get("grant_status") in {"expired", "revoked"}
        or binding.get("binding_status") in {"expired", "revoked"}
    )

    problems: list[str] = []
    if not session_id:
        problems.append("invalid_runtime_session_id")
    if not active_lease:
        problems.append("inactive_execution_lease")
    if not active_grant:
        problems.append("inactive_capability_grant")
    if not active_binding:
        problems.append("inactive_executor_binding")
    if not tool_boundary_id:
        problems.append("missing_tool_boundary")
    elif not admitted_boundary:
        problems.append("tool_boundary_not_admitted")
    if not tool_invocation_id:
        problems.append("missing_tool_invocation")
    elif not approved_invocation:
        problems.append("tool_invocation_not_approved")
    if requested_task_type not in SUPPORTED_TASK_TYPES:
        problems.append("unsupported_task_type")
    if not requested_task_id:
        problems.append("invalid_requested_task_id")
    if not authorized:
        problems.append("task_admission_authorization_missing")
    if stale_evidence:
        problems.append("stale_evidence")
    if requested_task_type == "mutation_task" and not recovery_ready:
        problems.append("mutation_recovery_readiness_missing")
    if active_grant and granted_capabilities.get("task_admission_access") is False:
        problems.append("task_admission_capability_denied")

    return {
        "runtime_session_id": session_id,
        "execution_lease_id": lease_id,
        "capability_grant_id": grant_id,
        "executor_binding_id": binding_id,
        "tool_boundary_id": tool_boundary_id,
        "tool_invocation_id": tool_invocation_id,
        "requested_task_id": requested_task_id,
        "requested_task_type": requested_task_type,
        "recovery_required": requested_task_type == "mutation_task",
        "recovery_ready": recovery_ready,
        "stale_evidence": stale_evidence,
        "problems": problems,
    }


def validate_runtime_task_execution_admission_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_task_admission_request(record)
    problems = list(evaluation["problems"])
    if missing:
        problems.append("missing_required_fields")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if record.get("audit_required") is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required") is not True:
        problems.append("non_mainline_issue_reporting_not_required")

    return {
        "schema": RUNTIME_TASK_EXECUTION_ADMISSION_SCHEMA,
        "valid": not problems,
        "task_admission_request_id": record.get("task_admission_request_id"),
        "runtime_session_id": evaluation["runtime_session_id"],
        "execution_lease_id": evaluation["execution_lease_id"],
        "capability_grant_id": evaluation["capability_grant_id"],
        "executor_binding_id": evaluation["executor_binding_id"],
        "tool_boundary_id": evaluation["tool_boundary_id"],
        "tool_invocation_id": evaluation["tool_invocation_id"],
        "requested_task_id": evaluation["requested_task_id"],
        "requested_task_type": evaluation["requested_task_type"],
        "admission_status": "admitted" if not problems else "denied",
        "admission_allowed": not problems,
        "denial_reason": "none" if not problems else ";".join(problems),
        "recovery_required": evaluation["recovery_required"],
        "recovery_ready": evaluation["recovery_ready"],
        "problems": problems,
        "missing_required_fields": missing,
        "unlock_attempts": unlocks,
        "task_executed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "uncontrolled_mutation_performed": False,
        "autonomy_started": False,
        "self_start_performed": False,
        "background_loop_started": False,
    }


def build_runtime_task_execution_admission_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_task_execution_admission_request(request)
    task_admission_id = _task_admission_id(
        request_id=str(validation.get("task_admission_request_id")),
        session_id=str(validation.get("runtime_session_id")),
        lease_id=str(validation.get("execution_lease_id")),
        grant_id=str(validation.get("capability_grant_id")),
        binding_id=str(validation.get("executor_binding_id")),
        tool_boundary_id=str(validation.get("tool_boundary_id")),
        tool_invocation_id=str(validation.get("tool_invocation_id")),
        task_id=str(validation.get("requested_task_id")),
        task_type=str(validation.get("requested_task_type")),
    )
    record = {
        "task_admission_id": task_admission_id,
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "tool_boundary_id": validation.get("tool_boundary_id"),
        "tool_invocation_id": validation.get("tool_invocation_id"),
        "requested_task_id": validation.get("requested_task_id"),
        "requested_task_type": validation.get("requested_task_type"),
        "admission_status": validation["admission_status"],
        "denial_reason": validation["denial_reason"],
        "recovery_required": validation["recovery_required"],
        "audit_projection": {},
        "supported_task_types": list(SUPPORTED_TASK_TYPES),
        "supported_statuses": list(TASK_ADMISSION_STATUSES),
        "record_only": True,
        "task_executed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "uncontrolled_mutation_performed": False,
        "autonomy_started": False,
        "self_start_performed": False,
        "background_loop_started": False,
    }
    record["audit_projection"] = build_runtime_task_execution_admission_audit_projection(
        record
    )
    return record


def expire_runtime_task_execution_admission(
    admission_record: dict[str, Any],
    *,
    reason: str = "task_admission_expired",
) -> dict[str, Any]:
    record = _as_mapping(admission_record)
    record["admission_status"] = "expired"
    record["denial_reason"] = reason
    record["task_executed"] = False
    record["audit_projection"] = build_runtime_task_execution_admission_audit_projection(
        record
    )
    return record


def revoke_runtime_task_execution_admission(
    admission_record: dict[str, Any],
    *,
    reason: str = "task_admission_revoked",
) -> dict[str, Any]:
    record = _as_mapping(admission_record)
    record["admission_status"] = "revoked"
    record["denial_reason"] = reason
    record["task_executed"] = False
    record["audit_projection"] = build_runtime_task_execution_admission_audit_projection(
        record
    )
    return record


def can_runtime_task_execute(admission_record: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(admission_record)
    return {
        "task_admission_id": record.get("task_admission_id"),
        "admission_status": record.get("admission_status", "denied"),
        "can_execute": False,
        "blocked": True,
        "blocked_reason": "task_execution_disabled",
        "task_executed": False,
        "subprocess_allowed": False,
        "shell_allowed": False,
        "network_allowed": False,
        "uncontrolled_mutation_allowed": False,
        "autonomy_allowed": False,
        "self_start_allowed": False,
        "background_loop_allowed": False,
    }


def build_runtime_task_execution_admission_audit_projection(
    admission_record: dict[str, Any] | None,
) -> dict[str, Any]:
    record = _as_mapping(admission_record)
    return {
        "projection": "runtime_task_execution_admission_audit",
        "projection_only": True,
        "task_admission_id": record.get("task_admission_id"),
        "runtime_session_id": record.get("runtime_session_id"),
        "execution_lease_id": record.get("execution_lease_id"),
        "capability_grant_id": record.get("capability_grant_id"),
        "executor_binding_id": record.get("executor_binding_id"),
        "tool_boundary_id": record.get("tool_boundary_id"),
        "tool_invocation_id": record.get("tool_invocation_id"),
        "requested_task_id": record.get("requested_task_id"),
        "requested_task_type": record.get("requested_task_type"),
        "admission_status": record.get("admission_status", "denied"),
        "denial_reason": record.get("denial_reason", "not_evaluated"),
        "recovery_required": bool(record.get("recovery_required", False)),
        "admitted_record_only": record.get("admission_status") == "admitted",
        "task_executed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "uncontrolled_mutation_performed": False,
        "autonomy_started": False,
        "self_start_performed": False,
        "background_loop_started": False,
    }


def build_runtime_task_execution_admission_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_task_execution_admission_request(request)
    admission = build_runtime_task_execution_admission_record(request)
    return {
        "audit_schema": RUNTIME_TASK_EXECUTION_ADMISSION_SCHEMA + ".audit",
        "decision": "reserved_runtime_task_execution_admission_record_only",
        "task_admission_request_id": validation.get("task_admission_request_id"),
        "runtime_session_id": validation.get("runtime_session_id"),
        "execution_lease_id": validation.get("execution_lease_id"),
        "capability_grant_id": validation.get("capability_grant_id"),
        "executor_binding_id": validation.get("executor_binding_id"),
        "tool_boundary_id": validation.get("tool_boundary_id"),
        "tool_invocation_id": validation.get("tool_invocation_id"),
        "request_valid": validation["valid"],
        "task_admission_record": admission,
        "audit_projection": admission["audit_projection"],
        "task_executed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "uncontrolled_mutation_performed": False,
        "autonomy_started": False,
        "self_start_performed": False,
        "background_loop_started": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
        "non_mainline_issues": validation["problems"],
    }


def build_runtime_task_execution_admission_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_runtime_task_execution_admission_audit_record(request)
    admission = _as_mapping(audit.get("task_admission_record"))
    return {
        "seal": "runtime_task_execution_admission_bundle",
        "schema": RUNTIME_TASK_EXECUTION_ADMISSION_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_TASK_ADMISSION_RECORDS_ONLY_NO_TASK_EXECUTION",
        "task_admission_id": admission.get("task_admission_id"),
        "admission_status": admission.get("admission_status"),
        "requested_task_type": admission.get("requested_task_type"),
        "audit_decision": audit["decision"],
        "task_executed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "uncontrolled_mutation_performed": False,
        "autonomy_started": False,
        "self_start_performed": False,
        "background_loop_started": False,
        "forbidden_surfaces_locked": True,
        "audit_required": True,
    }


__all__ = [
    "RUNTIME_TASK_EXECUTION_ADMISSION_SCHEMA",
    "TASK_ADMISSION_STATUSES",
    "SUPPORTED_TASK_TYPES",
    "REQUIRED_TASK_ADMISSION_FIELDS",
    "TASK_ADMISSION_LOCKS",
    "AUTHORIZED_TASK_ADMISSION_DECISION",
    "build_runtime_task_execution_admission_request",
    "validate_runtime_task_execution_admission_request",
    "build_runtime_task_execution_admission_record",
    "expire_runtime_task_execution_admission",
    "revoke_runtime_task_execution_admission",
    "can_runtime_task_execute",
    "build_runtime_task_execution_admission_audit_projection",
    "build_runtime_task_execution_admission_audit_record",
    "build_runtime_task_execution_admission_milestone_seal",
]
