from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any


RUNTIME_CONTROLLED_READ_EXECUTION_SCHEMA = "zero.runtime.controlled_read_execution.v1"

READ_EXECUTION_STATUSES = ("blocked", "succeeded", "failed")

REQUIRED_READ_EXECUTION_FIELDS = (
    "read_execution_request_id",
    "runtime_session_id",
    "execution_lease",
    "capability_grant",
    "executor_binding",
    "tool_boundary",
    "tool_invocation",
    "read_adapter",
    "workspace_root",
    "audit_required",
)

READ_EXECUTION_LOCKS = {
    "direct_filesystem_access_allowed": False,
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
    "self_start_allowed": False,
    "background_loop_allowed": False,
}

REQUIRED_BLOCKERS = (
    "runtime_session_id_required",
    "active_execution_lease_required",
    "active_capability_grant_required",
    "active_executor_binding_required",
    "active_tool_boundary_required",
    "active_tool_invocation_required",
    "active_read_adapter_required",
    "adapter_only_read_required",
    "scope_validation_required",
    "resource_ownership_required",
    "immutable_record_required",
    "direct_filesystem_access_locked",
    "write_locked",
    "append_locked",
    "delete_locked",
    "rename_locked",
    "chmod_locked",
    "mutation_locked",
    "subprocess_locked",
    "shell_locked",
    "network_locked",
    "task_execution_locked",
    "autonomy_locked",
    "self_start_locked",
    "background_loop_locked",
)


def _as_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _missing_required_fields(record: dict[str, Any]) -> list[str]:
    return [field for field in REQUIRED_READ_EXECUTION_FIELDS if field not in record]


def _unlock_attempts(boundaries: dict[str, Any]) -> list[str]:
    return [
        key
        for key, expected in READ_EXECUTION_LOCKS.items()
        if boundaries.get(key, expected) is not expected
    ]


def _read_execution_id(
    request_id: str,
    read_adapter_id: str,
    requested_resource: str,
) -> str:
    return f"read-execution::{read_adapter_id}::{requested_resource}::{request_id}"


def build_runtime_controlled_read_execution_request(
    *,
    read_execution_request_id: str,
    runtime_session_id: str | None = None,
    execution_lease: dict[str, Any] | None = None,
    capability_grant: dict[str, Any] | None = None,
    executor_binding: dict[str, Any] | None = None,
    tool_boundary: dict[str, Any] | None = None,
    tool_invocation: dict[str, Any] | None = None,
    read_adapter: dict[str, Any] | None = None,
    workspace_root: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": RUNTIME_CONTROLLED_READ_EXECUTION_SCHEMA,
        "read_execution_request_id": read_execution_request_id,
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
        "tool_boundary": deepcopy(tool_boundary) if tool_boundary is not None else {},
        "tool_invocation": (
            deepcopy(tool_invocation) if tool_invocation is not None else {}
        ),
        "read_adapter": deepcopy(read_adapter) if read_adapter is not None else {},
        "workspace_root": workspace_root,
        "boundary_locks": deepcopy(READ_EXECUTION_LOCKS),
        "audit_required": True,
        "blockers": list(REQUIRED_BLOCKERS),
        "non_mainline_issue_reporting_required": True,
    }


def _evaluate_read_execution_request(record: dict[str, Any]) -> dict[str, Any]:
    session_id = record.get("runtime_session_id")
    lease = _as_mapping(record.get("execution_lease"))
    grant = _as_mapping(record.get("capability_grant"))
    binding = _as_mapping(record.get("executor_binding"))
    boundary = _as_mapping(record.get("tool_boundary"))
    invocation = _as_mapping(record.get("tool_invocation"))
    adapter = _as_mapping(record.get("read_adapter"))

    lease_id = lease.get("lease_id")
    capability_grant_id = grant.get("capability_grant_id")
    executor_binding_id = binding.get("executor_binding_id")
    tool_boundary_id = boundary.get("tool_boundary_id")
    tool_invocation_id = invocation.get("tool_invocation_id")
    read_adapter_id = adapter.get("read_adapter_id")
    requested_resource = adapter.get("requested_resource")
    ownership = _as_mapping(adapter.get("resource_ownership"))
    scope = _as_mapping(adapter.get("read_scope_model"))

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
    active_binding = (
        bool(executor_binding_id)
        and binding.get("runtime_session_id") == session_id
        and binding.get("execution_lease_id") == lease_id
        and binding.get("capability_grant_id") == capability_grant_id
        and binding.get("binding_status") == "bound"
    )
    active_boundary = (
        bool(tool_boundary_id)
        and boundary.get("runtime_session_id") == session_id
        and boundary.get("execution_lease_id") == lease_id
        and boundary.get("capability_grant_id") == capability_grant_id
        and boundary.get("executor_binding_id") == executor_binding_id
        and boundary.get("tool_boundary_status") == "admitted"
        and boundary.get("admission_granted") is True
    )
    active_invocation = (
        bool(tool_invocation_id)
        and invocation.get("runtime_session_id") == session_id
        and invocation.get("execution_lease_id") == lease_id
        and invocation.get("capability_grant_id") == capability_grant_id
        and invocation.get("executor_binding_id") == executor_binding_id
        and invocation.get("tool_boundary_id") == tool_boundary_id
        and invocation.get("invocation_status") == "approved"
    )
    active_adapter = (
        bool(read_adapter_id)
        and adapter.get("runtime_session_id") == session_id
        and adapter.get("execution_lease_id") == lease_id
        and adapter.get("capability_grant_id") == capability_grant_id
        and adapter.get("executor_binding_id") == executor_binding_id
        and adapter.get("tool_boundary_id") == tool_boundary_id
        and adapter.get("tool_invocation_id") == tool_invocation_id
        and adapter.get("read_status") == "planned"
    )
    ownership_verified = (
        ownership.get("owner_session_id") == session_id
        and ownership.get("ownership_verified") is True
    )
    scope_valid = (
        bool(requested_resource)
        and scope.get("resource_in_scope") is True
        and scope.get("controlled_read_allowed") is True
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
    if not active_boundary:
        problems.append("inactive_tool_boundary")
    if not active_invocation:
        problems.append("inactive_tool_invocation")
    if not read_adapter_id:
        problems.append("missing_read_adapter")
    elif not active_adapter:
        problems.append("inactive_read_adapter")
    if not ownership_verified:
        problems.append("resource_ownership_unverified")
    if not scope_valid:
        problems.append("read_scope_invalid")

    return {
        "runtime_session_id": session_id,
        "execution_lease_id": lease_id,
        "capability_grant_id": capability_grant_id,
        "executor_binding_id": executor_binding_id,
        "tool_boundary_id": tool_boundary_id,
        "tool_invocation_id": tool_invocation_id,
        "read_adapter_id": read_adapter_id,
        "requested_resource": requested_resource,
        "problems": problems,
    }


def validate_runtime_controlled_read_execution_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    record = _as_mapping(request)
    missing = _missing_required_fields(record)
    blockers = _as_list(record.get("blockers"))
    missing_blockers = [b for b in REQUIRED_BLOCKERS if b not in blockers]
    unlocks = _unlock_attempts(_as_mapping(record.get("boundary_locks")))
    evaluation = _evaluate_read_execution_request(record)
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
        "schema": RUNTIME_CONTROLLED_READ_EXECUTION_SCHEMA,
        "valid": not problems,
        "read_execution_request_id": record.get("read_execution_request_id"),
        "runtime_session_id": evaluation["runtime_session_id"],
        "execution_lease_id": evaluation["execution_lease_id"],
        "capability_grant_id": evaluation["capability_grant_id"],
        "executor_binding_id": evaluation["executor_binding_id"],
        "tool_boundary_id": evaluation["tool_boundary_id"],
        "tool_invocation_id": evaluation["tool_invocation_id"],
        "read_adapter_id": evaluation["read_adapter_id"],
        "requested_resource": evaluation["requested_resource"],
        "status": "accepted_controlled_read_request" if not problems else "blocked",
        "problems": problems,
        "missing_required_fields": missing,
        "missing_required_blockers": missing_blockers,
        "unlock_attempts": unlocks,
        "read_allowed": not problems,
        "file_write_performed": False,
        "append_performed": False,
        "delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "mutation_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "self_start_performed": False,
        "background_loop_started": False,
        "audit_required": True,
    }


def _resolve_adapter_resource(workspace_root: str, requested_resource: str) -> Path:
    root = Path(workspace_root).resolve()
    resource = requested_resource
    if resource.startswith("workspace://"):
        resource = resource[len("workspace://") :]
    candidate = (root / resource).resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError("resource_outside_workspace")
    return candidate


def execute_runtime_controlled_read(
    request: dict[str, Any],
) -> MappingProxyType:
    validation = validate_runtime_controlled_read_execution_request(request)
    if not validation["read_allowed"]:
        return MappingProxyType(
            build_runtime_controlled_read_execution_record(
                request,
                execution_status="failed",
                content=b"",
                failure_reason=";".join(validation["problems"]),
            )
        )

    record = _as_mapping(request)
    try:
        resource_path = _resolve_adapter_resource(
            str(record.get("workspace_root")),
            str(validation["requested_resource"]),
        )
        with open(resource_path, "rb") as handle:
            content = handle.read()
        execution = build_runtime_controlled_read_execution_record(
            request,
            execution_status="succeeded",
            content=content,
            failure_reason=None,
            resource_path=str(resource_path),
        )
    except Exception as exc:  # pragma: no cover - exact exception type is environment-dependent.
        execution = build_runtime_controlled_read_execution_record(
            request,
            execution_status="failed",
            content=b"",
            failure_reason=str(exc),
        )
    return MappingProxyType(execution)


def build_runtime_controlled_read_execution_record(
    request: dict[str, Any],
    *,
    execution_status: str,
    content: bytes,
    failure_reason: str | None,
    resource_path: str | None = None,
) -> dict[str, Any]:
    record = _as_mapping(request)
    evaluation = _evaluate_read_execution_request(record)
    requested_resource = str(evaluation["requested_resource"])
    read_adapter_id = str(evaluation["read_adapter_id"])
    execution_id = _read_execution_id(
        str(record.get("read_execution_request_id")),
        read_adapter_id,
        requested_resource,
    )
    digest = sha256(content).hexdigest() if execution_status == "succeeded" else None
    content_metadata = {
        "content_length": len(content) if execution_status == "succeeded" else 0,
        "resource_reference": requested_resource,
        "resource_path": resource_path,
        "content_included": False,
        "immutable": True,
    }
    execution = {
        "read_execution_id": execution_id,
        "read_adapter_id": read_adapter_id,
        "requested_resource": requested_resource,
        "execution_status": execution_status,
        "content_digest": digest,
        "content_metadata": content_metadata,
        "failure_reason": failure_reason,
        "audit_projection": {},
        "failure_ownership": {
            "failure_owner": "runtime_controlled_read_execution",
            "failure_recorded": failure_reason is not None,
            "failure_reason": failure_reason,
        },
        "read_replay_record": {
            "replay_type": "controlled_read_digest_replay",
            "read_execution_id": execution_id,
            "content_digest": digest,
            "requested_resource": requested_resource,
            "content_included": False,
            "immutable": True,
        },
        "immutable_record": True,
        "adapter_only_read": True,
        "direct_filesystem_access_performed": False,
        "file_write_performed": False,
        "append_performed": False,
        "delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "mutation_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "self_start_performed": False,
        "background_loop_started": False,
    }
    execution["audit_projection"] = build_runtime_controlled_read_audit_projection(
        execution
    )
    return execution


def build_runtime_controlled_read_audit_projection(
    read_execution_record: dict[str, Any] | None,
) -> dict[str, Any]:
    execution = _as_mapping(read_execution_record)
    return {
        "projection": "runtime_controlled_read_execution_audit",
        "projection_only": True,
        "read_execution_id": execution.get("read_execution_id"),
        "read_adapter_id": execution.get("read_adapter_id"),
        "requested_resource": execution.get("requested_resource"),
        "execution_status": execution.get("execution_status", "blocked"),
        "content_digest": execution.get("content_digest"),
        "content_metadata": execution.get("content_metadata"),
        "failure_reason": execution.get("failure_reason"),
        "read_replay_record": execution.get("read_replay_record"),
        "direct_filesystem_access_performed": False,
        "file_write_performed": False,
        "append_performed": False,
        "delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "mutation_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "self_start_performed": False,
        "background_loop_started": False,
    }


def build_runtime_controlled_read_audit_record(
    request: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_runtime_controlled_read_execution_request(request)
    execution = execute_runtime_controlled_read(request) if validation["read_allowed"] else None

    return {
        "audit_schema": RUNTIME_CONTROLLED_READ_EXECUTION_SCHEMA + ".audit",
        "decision": "reserved_runtime_controlled_read_execution_only",
        "read_execution_request_id": validation.get("read_execution_request_id"),
        "read_adapter_id": validation.get("read_adapter_id"),
        "requested_resource": validation.get("requested_resource"),
        "request_valid": validation["valid"],
        "read_allowed": validation["read_allowed"],
        "read_execution_record": execution,
        "audit_projection": build_runtime_controlled_read_audit_projection(execution),
        "direct_filesystem_access_performed": False,
        "file_write_performed": False,
        "append_performed": False,
        "delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "mutation_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "self_start_performed": False,
        "background_loop_started": False,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
        "non_mainline_issues": validation["problems"],
    }


def build_runtime_controlled_read_milestone_seal(
    request: dict[str, Any],
) -> dict[str, Any]:
    audit = build_runtime_controlled_read_audit_record(request)

    return {
        "seal": "runtime_controlled_read_execution_bundle",
        "schema": RUNTIME_CONTROLLED_READ_EXECUTION_SCHEMA,
        "closed": True,
        "final_decision": "GO_FOR_CONTROLLED_READ_EXECUTION_ONLY_ZERO_MODIFICATION",
        "next_package": 1273,
        "read_adapter_id": audit.get("read_adapter_id"),
        "requested_resource": audit.get("requested_resource"),
        "read_allowed": audit["read_allowed"],
        "audit_decision": audit["decision"],
        "file_write_performed": False,
        "append_performed": False,
        "delete_performed": False,
        "rename_performed": False,
        "chmod_performed": False,
        "mutation_performed": False,
        "subprocess_started": False,
        "shell_started": False,
        "network_performed": False,
        "task_executed": False,
        "autonomy_started": False,
        "self_start_performed": False,
        "background_loop_started": False,
        "all_modification_surfaces_locked": True,
        "audit_required": True,
        "non_mainline_issue_reporting_required": True,
    }


__all__ = [
    "RUNTIME_CONTROLLED_READ_EXECUTION_SCHEMA",
    "READ_EXECUTION_STATUSES",
    "REQUIRED_READ_EXECUTION_FIELDS",
    "READ_EXECUTION_LOCKS",
    "REQUIRED_BLOCKERS",
    "build_runtime_controlled_read_execution_request",
    "validate_runtime_controlled_read_execution_request",
    "execute_runtime_controlled_read",
    "build_runtime_controlled_read_execution_record",
    "build_runtime_controlled_read_audit_projection",
    "build_runtime_controlled_read_audit_record",
    "build_runtime_controlled_read_milestone_seal",
]
