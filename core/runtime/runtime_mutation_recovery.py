from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any


RUNTIME_MUTATION_RECOVERY_SCHEMA = "zero.runtime.mutation_recovery.v1"

MUTATION_RECOVERY_STATUSES = ("planned", "restored", "failed", "denied")

REQUIRED_MUTATION_RECOVERY_FIELDS = (
    "mutation_execution_id",
    "mutation_execution_record",
    "rollback_record",
    "rollback_source",
    "workspace_root",
    "before_digest",
    "after_digest",
    "mutation_ownership_evidence",
    "recovery_reason",
)

RECOVERY_LOCKS = {
    "arbitrary_write_allowed": False,
    "arbitrary_delete_allowed": False,
    "rename_allowed": False,
    "chmod_allowed": False,
    "shell_allowed": False,
    "subprocess_allowed": False,
    "network_allowed": False,
    "executor_task_execution_allowed": False,
    "autonomy_allowed": False,
    "background_loop_allowed": False,
}


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _digest_bytes(content: bytes) -> str:
    return sha256(content).hexdigest()


def _stable_fragment(parts: dict[str, Any]) -> str:
    encoded = repr(sorted((str(k), str(v)) for k, v in parts.items()))
    return sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _recovery_id(mutation_execution_id: str, before_digest: str, after_digest: str) -> str:
    fragment = _stable_fragment(
        {
            "mutation_execution_id": mutation_execution_id,
            "before_digest": before_digest,
            "after_digest": after_digest,
        }
    )
    return f"mutation-recovery::{mutation_execution_id}::{fragment}"


def _payload_content(source: dict[str, Any]) -> bytes:
    if "before_content_bytes" in source and isinstance(source.get("before_content_bytes"), bytes):
        return bytes(source["before_content_bytes"])
    if "before_content" in source and source.get("before_content") is not None:
        return str(source.get("before_content")).encode("utf-8")
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


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_MUTATION_RECOVERY_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in RECOVERY_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _evaluate_recovery_request(request: dict[str, Any]) -> dict[str, Any]:
    mutation_execution_id = request.get("mutation_execution_id")
    execution = _as_mapping(request.get("mutation_execution_record"))
    rollback = _as_mapping(request.get("rollback_record"))
    rollback_source = _as_mapping(request.get("rollback_source"))
    ownership = _as_mapping(request.get("mutation_ownership_evidence"))
    before_digest = request.get("before_digest")
    after_digest = request.get("after_digest")
    target_resource = execution.get("target_resource")
    rollback_operation = rollback.get("operation")
    source_target = rollback_source.get("target_resource", target_resource)

    problems: list[str] = []
    if not execution:
        problems.append("mutation_record_missing")
    if not rollback:
        problems.append("rollback_record_missing")
    if not rollback_source:
        problems.append("rollback_source_missing")
    if not mutation_execution_id:
        problems.append("mutation_execution_id_missing")
    if execution and mutation_execution_id != execution.get("mutation_execution_id"):
        problems.append("mutation_execution_id_mismatch")
    if rollback and mutation_execution_id != rollback.get("mutation_execution_id"):
        problems.append("rollback_mutation_execution_id_mismatch")
    if execution and execution.get("execution_status") != "succeeded":
        problems.append("mutation_execution_not_succeeded")
    if execution and execution.get("controlled_mutation_executor_used") is not True:
        problems.append("controlled_mutation_execution_missing")
    if execution and execution.get("atomic_mutation_path") is not True:
        problems.append("atomic_mutation_path_missing")
    if not ownership or ownership.get("ownership_verified") is not True:
        problems.append("mutation_ownership_invalid")
    if ownership and execution:
        if ownership.get("mutation_approval_id") != execution.get("mutation_approval_id"):
            problems.append("ownership_approval_mismatch")
    if rollback and rollback.get("rollback_ready") is not True:
        problems.append("rollback_not_ready")
    if rollback and rollback.get("rollback_executed") is True:
        problems.append("rollback_already_executed")
    if execution and before_digest != execution.get("before_digest"):
        problems.append("execution_before_digest_mismatch")
    if execution and after_digest != execution.get("after_digest"):
        problems.append("execution_after_digest_mismatch")
    if rollback and before_digest != rollback.get("before_digest"):
        problems.append("rollback_before_digest_mismatch")
    if rollback and after_digest != rollback.get("after_digest"):
        problems.append("rollback_after_digest_mismatch")
    if rollback and rollback.get("target_resource") != target_resource:
        problems.append("rollback_target_mismatch")
    if rollback_source and source_target != target_resource:
        problems.append("rollback_source_target_mismatch")
    if rollback_operation not in {"restore_before_digest", "remove_created_resource"}:
        problems.append("rollback_operation_forbidden")

    source_content = _payload_content(rollback_source)
    source_digest = rollback_source.get("before_digest") or _digest_bytes(source_content)
    if rollback_operation == "restore_before_digest" and source_digest != before_digest:
        problems.append("rollback_source_digest_mismatch")

    return {
        "valid": not problems,
        "mutation_execution_id": mutation_execution_id,
        "target_resource": target_resource,
        "rollback_operation": rollback_operation,
        "before_digest": before_digest,
        "after_digest": after_digest,
        "source_digest": source_digest,
        "problems": problems,
    }


def build_runtime_mutation_recovery_request(
    *,
    mutation_execution_id: str,
    mutation_execution_record: dict[str, Any] | None = None,
    rollback_record: dict[str, Any] | None = None,
    rollback_source: dict[str, Any] | None = None,
    workspace_root: str | None = None,
    before_digest: str | None = None,
    after_digest: str | None = None,
    mutation_ownership_evidence: dict[str, Any] | None = None,
    recovery_reason: str = "controlled mutation recovery",
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_MUTATION_RECOVERY_SCHEMA,
        "mutation_execution_id": mutation_execution_id,
        "mutation_execution_record": _as_mapping(mutation_execution_record),
        "rollback_record": _as_mapping(rollback_record),
        "rollback_source": _as_mapping(rollback_source),
        "workspace_root": workspace_root,
        "before_digest": before_digest,
        "after_digest": after_digest,
        "mutation_ownership_evidence": _as_mapping(mutation_ownership_evidence),
        "recovery_reason": recovery_reason,
        "boundary_locks": deepcopy(RECOVERY_LOCKS),
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


def validate_runtime_mutation_recovery_request(request: dict[str, Any]) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_recovery_request(record)
    problems = list(evaluation["problems"])
    if missing:
        problems.append("missing_required_fields")
    if unlocks:
        problems.append("boundary_unlock_attempt")
    if record.get("audit_required", True) is not True:
        problems.append("audit_not_required")
    if record.get("non_mainline_issue_reporting_required", True) is not True:
        problems.append("non_mainline_issue_reporting_not_required")
    return {
        "schema": RUNTIME_MUTATION_RECOVERY_SCHEMA,
        "valid": not problems,
        "mutation_execution_id": evaluation["mutation_execution_id"],
        "target_resource": evaluation["target_resource"],
        "rollback_operation": evaluation["rollback_operation"],
        "before_digest": evaluation["before_digest"],
        "after_digest": evaluation["after_digest"],
        "source_digest": evaluation["source_digest"],
        "recovery_allowed": not problems,
        "recovery_status": "planned" if not problems else "denied",
        "failure_reason": None if not problems else ";".join(problems),
        "problems": problems,
        "missing_required_fields": missing,
        "unlock_attempts": unlocks,
        "arbitrary_write_performed": False,
        "arbitrary_delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "shell_started": False,
        "subprocess_started": False,
        "network_performed": False,
        "executor_task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
    }


def build_runtime_mutation_recovery_record(request: dict[str, Any]) -> dict[str, Any]:
    validation = validate_runtime_mutation_recovery_request(request)
    record = _as_mapping(request)
    recovery = {
        "mutation_recovery_id": _recovery_id(
            str(validation.get("mutation_execution_id")),
            str(validation.get("before_digest")),
            str(validation.get("after_digest")),
        ),
        "mutation_execution_id": validation.get("mutation_execution_id"),
        "rollback_source": _as_mapping(record.get("rollback_source")),
        "recovery_status": validation["recovery_status"],
        "restored_digest": None,
        "recovery_reason": record.get("recovery_reason"),
        "failure_reason": validation["failure_reason"],
        "audit_projection": {},
        "target_resource": validation.get("target_resource"),
        "rollback_operation": validation.get("rollback_operation"),
        "before_digest": validation.get("before_digest"),
        "after_digest": validation.get("after_digest"),
        "arbitrary_write_performed": False,
        "arbitrary_delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "shell_started": False,
        "subprocess_started": False,
        "network_performed": False,
        "executor_task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
    }
    recovery["audit_projection"] = build_runtime_mutation_recovery_audit_projection(
        recovery,
        validation=validation,
    )
    return recovery


def execute_runtime_mutation_recovery(request: dict[str, Any]) -> dict[str, Any]:
    validation = validate_runtime_mutation_recovery_request(request)
    recovery = build_runtime_mutation_recovery_record(request)
    if not validation["recovery_allowed"]:
        return recovery

    record = _as_mapping(request)
    rollback_source = _as_mapping(record.get("rollback_source"))
    target_resource = str(validation["target_resource"])
    operation = str(validation["rollback_operation"])

    try:
        target = _resolve_target(str(record.get("workspace_root")), target_resource)
        current_digest = _digest_bytes(target.read_bytes()) if target.exists() else sha256(b"").hexdigest()
        if current_digest != validation["after_digest"]:
            recovery["recovery_status"] = "failed"
            recovery["failure_reason"] = "current_digest_not_mutation_after_digest"
            recovery["audit_projection"] = build_runtime_mutation_recovery_audit_projection(
                recovery,
                validation=validation,
            )
            return recovery

        if operation == "restore_before_digest":
            content = _payload_content(rollback_source)
            if _digest_bytes(content) != validation["before_digest"]:
                recovery["recovery_status"] = "failed"
                recovery["failure_reason"] = "restore_content_digest_mismatch"
                recovery["audit_projection"] = build_runtime_mutation_recovery_audit_projection(
                    recovery,
                    validation=validation,
                )
                return recovery
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            restored_digest = _digest_bytes(target.read_bytes())
        elif operation == "remove_created_resource":
            if target.exists():
                target.unlink()
            restored_digest = sha256(b"").hexdigest()
        else:
            recovery["recovery_status"] = "denied"
            recovery["failure_reason"] = "rollback_operation_forbidden"
            recovery["audit_projection"] = build_runtime_mutation_recovery_audit_projection(
                recovery,
                validation=validation,
            )
            return recovery

        recovery["restored_digest"] = restored_digest
        recovery["recovery_status"] = (
            "restored" if restored_digest == validation["before_digest"] else "failed"
        )
        recovery["failure_reason"] = (
            None
            if recovery["recovery_status"] == "restored"
            else "restored_digest_mismatch"
        )
    except Exception as exc:
        recovery["recovery_status"] = "failed"
        recovery["failure_reason"] = str(exc)

    recovery["audit_projection"] = build_runtime_mutation_recovery_audit_projection(
        recovery,
        validation=validation,
    )
    return recovery


def build_runtime_mutation_recovery_audit_projection(
    recovery_record: dict[str, Any] | None,
    *,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recovery = _as_mapping(recovery_record)
    validated = _as_mapping(validation)
    valid = bool(validated.get("valid", recovery.get("recovery_status") in {"planned", "restored"}))
    return {
        "projection": "runtime_mutation_recovery_audit",
        "projection_only": True,
        "mutation_recovery_id": recovery.get("mutation_recovery_id"),
        "mutation_execution_id": recovery.get("mutation_execution_id"),
        "target_resource": recovery.get("target_resource"),
        "recovery_status": recovery.get("recovery_status"),
        "restored_digest": recovery.get("restored_digest"),
        "rollback_integrity_verified": valid,
        "ownership_chain_validated": valid,
        "recovery_audit_evidence": True,
        "unrelated_resource_modified": False,
        "arbitrary_write_performed": False,
        "arbitrary_delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "shell_started": False,
        "subprocess_started": False,
        "network_performed": False,
        "executor_task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
    }


def build_runtime_mutation_recovery_audit_record(request: dict[str, Any]) -> dict[str, Any]:
    recovery = build_runtime_mutation_recovery_record(request)
    return {
        "audit_schema": RUNTIME_MUTATION_RECOVERY_SCHEMA + ".audit",
        "decision": "reserved_runtime_mutation_recovery",
        "mutation_execution_id": recovery.get("mutation_execution_id"),
        "mutation_recovery_id": recovery.get("mutation_recovery_id"),
        "recovery_record": recovery,
        "audit_projection": recovery["audit_projection"],
        "arbitrary_write_performed": False,
        "arbitrary_delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "shell_started": False,
        "subprocess_started": False,
        "network_performed": False,
        "executor_task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


def build_runtime_mutation_recovery_milestone_seal(request: dict[str, Any]) -> dict[str, Any]:
    audit = build_runtime_mutation_recovery_audit_record(request)
    recovery = _as_mapping(audit.get("recovery_record"))
    return {
        "seal": "runtime_mutation_recovery_bundle",
        "schema": RUNTIME_MUTATION_RECOVERY_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_CONTROLLED_MUTATION_RECOVERY_ONLY",
        "mutation_execution_id": recovery.get("mutation_execution_id"),
        "mutation_recovery_id": recovery.get("mutation_recovery_id"),
        "recovery_status": recovery.get("recovery_status"),
        "rollback_integrity_verified": recovery["audit_projection"][
            "rollback_integrity_verified"
        ],
        "ownership_chain_validated": recovery["audit_projection"][
            "ownership_chain_validated"
        ],
        "forbidden_surfaces_locked": True,
        "arbitrary_write_performed": False,
        "arbitrary_delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "shell_started": False,
        "subprocess_started": False,
        "network_performed": False,
        "executor_task_executed": False,
        "autonomy_started": False,
        "background_loop_started": False,
    }


__all__ = [
    "RUNTIME_MUTATION_RECOVERY_SCHEMA",
    "MUTATION_RECOVERY_STATUSES",
    "REQUIRED_MUTATION_RECOVERY_FIELDS",
    "RECOVERY_LOCKS",
    "build_runtime_mutation_recovery_request",
    "validate_runtime_mutation_recovery_request",
    "build_runtime_mutation_recovery_record",
    "execute_runtime_mutation_recovery",
    "build_runtime_mutation_recovery_audit_projection",
    "build_runtime_mutation_recovery_audit_record",
    "build_runtime_mutation_recovery_milestone_seal",
]
