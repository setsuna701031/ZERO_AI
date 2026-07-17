from __future__ import annotations

from copy import deepcopy
from typing import Any


RUNTIME_READ_REPLAY_VERIFICATION_SCHEMA = "zero.runtime.read_replay_verification.v1"

REPLAY_VERIFICATION_STATUSES = ("verified", "mismatch", "expired", "invalid")

REQUIRED_REPLAY_VERIFICATION_FIELDS = (
    "replay_verification_request_id",
    "read_evidence",
    "current_digest",
    "verification_timestamp",
    "audit_required",
)

REPLAY_VERIFICATION_LOCKS = {
    "write_allowed": False,
    "mutation_allowed": False,
    "subprocess_allowed": False,
    "shell_allowed": False,
    "network_allowed": False,
    "executor_action_allowed": False,
    "autonomy_allowed": False,
    "background_loop_allowed": False,
    "resource_read_allowed": False,
}

REQUIRED_BLOCKERS = (
    "read_execution_id_required",
    "immutable_read_evidence_required",
    "content_digest_required",
    "content_metadata_required",
    "evidence_ownership_required",
    "verification_timestamp_required",
    "replay_audit_required",
    "no_resource_read_allowed",
    "write_locked",
    "mutation_locked",
    "subprocess_locked",
    "shell_locked",
    "network_locked",
    "executor_action_locked",
    "autonomy_locked",
    "background_loop_locked",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_REPLAY_VERIFICATION_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in REPLAY_VERIFICATION_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _verification_id(request_id: str, read_execution_id: str) -> str:
    return f"read-replay-verification::{read_execution_id}::{request_id}"


def build_runtime_read_replay_verification_request(
    *,
    replay_verification_request_id: str,
    read_evidence: dict[str, Any] | None = None,
    current_digest: str | None = None,
    verification_timestamp: str = "deterministic-tick-0",
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_READ_REPLAY_VERIFICATION_SCHEMA,
        "replay_verification_request_id": replay_verification_request_id,
        "read_evidence": deepcopy(read_evidence) if read_evidence is not None else {},
        "current_digest": current_digest,
        "verification_timestamp": verification_timestamp,
        "boundary_locks": deepcopy(REPLAY_VERIFICATION_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def _evaluate_replay_verification(record: dict[str, Any]) -> dict[str, Any]:
    evidence = _as_mapping(record.get("read_evidence"))
    read_execution_id = evidence.get("read_execution_id")
    original_digest = evidence.get("content_digest")
    current_digest = record.get("current_digest")
    metadata = _as_mapping(evidence.get("content_metadata"))
    ownership = _as_mapping(evidence.get("evidence_ownership"))
    verification_timestamp = record.get("verification_timestamp")
    status = evidence.get("execution_status")

    problems: list[str] = []
    if not read_execution_id:
        problems.append("missing_read_evidence")
    if status != "succeeded":
        problems.append("invalid_read_execution")
    if evidence.get("immutable_record") is not True:
        problems.append("immutable_read_evidence_missing")
    if not original_digest:
        problems.append("content_digest_missing")
    if not metadata or metadata.get("immutable") is not True:
        problems.append("content_metadata_invalid")
    if ownership.get("evidence_owner") != "runtime_controlled_read_execution":
        problems.append("evidence_ownership_invalid")
    if metadata.get("expired") is True or evidence.get("evidence_expired") is True:
        problems.append("read_evidence_expired")
    if not current_digest:
        problems.append("current_digest_missing")
    if not verification_timestamp:
        problems.append("verification_timestamp_missing")

    if problems:
        verification_status = (
            "expired" if "read_evidence_expired" in problems else "invalid"
        )
        mismatch_reason = ";".join(problems)
    elif original_digest == current_digest:
        verification_status = "verified"
        mismatch_reason = "none"
    else:
        verification_status = "mismatch"
        mismatch_reason = "content_digest_changed"

    return {
        "read_execution_id": read_execution_id,
        "original_digest": original_digest,
        "current_digest": current_digest,
        "verification_status": verification_status,
        "mismatch_reason": mismatch_reason,
        "problems": problems,
        "verification_timestamp": verification_timestamp,
        "mutation_readiness_allowed": verification_status == "verified",
    }


def validate_runtime_read_replay_verification_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_replay_verification(record)

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
        "schema": RUNTIME_READ_REPLAY_VERIFICATION_SCHEMA,
        "valid": not problems and evaluation["verification_status"] == "verified",
        "replay_verification_request_id": record.get("replay_verification_request_id"),
        "read_execution_id": evaluation["read_execution_id"],
        "verification_status": evaluation["verification_status"],
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "mutation_readiness_allowed": evaluation["mutation_readiness_allowed"],
        "resource_read_performed": False,
        "write_performed": False,
        "mutation_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "executor_action_performed": False,
        "autonomy_started": False,
        "background_loop_started": False,
        "audit_required": True,
    }


def build_runtime_read_replay_verification_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    evaluation = _evaluate_replay_verification(record)
    request_id = str(record.get("replay_verification_request_id"))
    read_execution_id = str(evaluation["read_execution_id"])
    verification_record = {
        "replay_verification_id": _verification_id(request_id, read_execution_id),
        "read_execution_id": evaluation["read_execution_id"],
        "original_digest": evaluation["original_digest"],
        "current_digest": evaluation["current_digest"],
        "verification_status": evaluation["verification_status"],
        "mismatch_reason": evaluation["mismatch_reason"],
        "audit_projection": {},
        "supported_statuses": list(REPLAY_VERIFICATION_STATUSES),
        "stale_read_detected": evaluation["verification_status"] == "mismatch",
        "evidence_ownership": _as_mapping(
            _as_mapping(record.get("read_evidence")).get("evidence_ownership")
        ),
        "verification_timestamp": evaluation["verification_timestamp"],
        "mutation_readiness_allowed": evaluation["mutation_readiness_allowed"],
        "resource_read_performed": False,
        "write_performed": False,
        "mutation_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "executor_action_performed": False,
        "autonomy_started": False,
        "background_loop_started": False,
    }
    verification_record["audit_projection"] = (
        build_runtime_read_replay_verification_audit_projection(verification_record)
    )
    return verification_record


def build_runtime_read_replay_verification_audit_projection(
    verification_record: dict[str, Any] | None,
) -> dict[str, Any]:
    record = _as_mapping(verification_record)
    return {
        "projection": "runtime_read_replay_verification_audit",
        "projection_only": True,
        "replay_verification_id": record.get("replay_verification_id"),
        "read_execution_id": record.get("read_execution_id"),
        "verification_status": record.get("verification_status", "invalid"),
        "mismatch_reason": record.get("mismatch_reason", "missing_verification"),
        "stale_read_detected": bool(record.get("stale_read_detected", False)),
        "mutation_readiness_allowed": bool(
            record.get("mutation_readiness_allowed", False)
        ),
        "verification_timestamp": record.get("verification_timestamp"),
        "resource_read_performed": False,
        "write_performed": False,
        "mutation_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "executor_action_performed": False,
        "autonomy_started": False,
        "background_loop_started": False,
    }


def build_runtime_read_replay_verification_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_read_replay_verification_request(request)
    verification = build_runtime_read_replay_verification_record(request)

    return {
        "audit_schema": RUNTIME_READ_REPLAY_VERIFICATION_SCHEMA + ".audit",
        "decision": "reserved_runtime_read_replay_verification_only",
        "replay_verification_request_id": validation.get(
            "replay_verification_request_id"
        ),
        "read_execution_id": validation.get("read_execution_id"),
        "request_valid": validation["valid"],
        "verification_record": verification,
        "audit_projection": build_runtime_read_replay_verification_audit_projection(
            verification
        ),
        "resource_read_performed": False,
        "write_performed": False,
        "mutation_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "executor_action_performed": False,
        "autonomy_started": False,
        "background_loop_started": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
        "non_mainline_issues": validation["problems"],
    }


def build_runtime_read_replay_verification_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_runtime_read_replay_verification_audit_record(request)
    verification = _as_mapping(audit.get("verification_record"))

    return {
        "seal": "runtime_read_replay_verification_bundle",
        "schema": RUNTIME_READ_REPLAY_VERIFICATION_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_READ_REPLAY_VERIFICATION_BEFORE_FUTURE_MUTATION",
        "next_package": 1281,
        "read_execution_id": audit.get("read_execution_id"),
        "verification_status": verification.get("verification_status"),
        "mutation_readiness_allowed": verification.get("mutation_readiness_allowed"),
        "audit_decision": audit["decision"],
        "resource_read_performed": False,
        "write_performed": False,
        "mutation_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "executor_action_performed": False,
        "autonomy_started": False,
        "background_loop_started": False,
        "all_effect_surfaces_locked": True,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


__all__ = [
    "RUNTIME_READ_REPLAY_VERIFICATION_SCHEMA",
    "REPLAY_VERIFICATION_STATUSES",
    "REQUIRED_REPLAY_VERIFICATION_FIELDS",
    "REPLAY_VERIFICATION_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_runtime_read_replay_verification_request",
    "validate_runtime_read_replay_verification_request",
    "build_runtime_read_replay_verification_record",
    "build_runtime_read_replay_verification_audit_projection",
    "build_runtime_read_replay_verification_audit_record",
    "build_runtime_read_replay_verification_milestone_seal",
]
