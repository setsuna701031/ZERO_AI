from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Mapping

from core.runtime.work_package_queue import work_package_execution_path


RUNTIME_DISPATCH_REQUEST_SCHEMA = "zero.work_package.runtime_dispatch_request.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _require_approved(execution_package: Mapping[str, Any]) -> dict[str, Any]:
    approved_proposal = _mapping(execution_package.get("approved_proposal"))
    approval = _mapping(approved_proposal.get("approval"))
    if not approval:
        raise PermissionError("proposal_approval_required")
    if approval.get("approved") is not True:
        raise PermissionError("proposal_approval_required")
    return approval


def execution_package_to_runtime_dispatch_request(
    execution_package: Mapping[str, Any],
    *,
    record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert an approved execution package into a dispatcher request only.

    The request targets the existing RuntimeDispatcher path. It deliberately
    carries no direct TaskRunner or StepExecutor invocation.
    """
    if not isinstance(execution_package, Mapping):
        raise TypeError("execution_package_must_be_mapping")
    approval = _require_approved(execution_package)
    queue_record = _mapping(record)
    package_id = str(execution_package.get("package_id") or queue_record.get("package_id") or "")
    if not package_id:
        raise ValueError("package_id_required")

    steps = copy.deepcopy(execution_package.get("executable_steps") or [])
    runtime_queue_item = _mapping(queue_record.get("runtime_queue_item"))
    if not runtime_queue_item:
        runtime_queue_item = {
            "package_id": package_id,
            "task_id": str(queue_record.get("task_id") or f"task-{package_id}"),
            "session_id": str(queue_record.get("session_id") or ""),
            "status": "queued",
            "lifecycle_state": str(queue_record.get("lifecycle_state") or "queued"),
            "steps": steps,
            "current_step_index": 0,
            "results": [],
            "runtime_owner": "RuntimeDispatcher",
            "taskrunner_required": True,
            "step_executor_endpoint_only": True,
            "direct_execution": False,
        }
    else:
        runtime_queue_item["steps"] = copy.deepcopy(runtime_queue_item.get("steps") or steps)
        runtime_queue_item.setdefault("runtime_owner", "RuntimeDispatcher")
        runtime_queue_item.setdefault("taskrunner_required", True)
        runtime_queue_item.setdefault("step_executor_endpoint_only", True)
        runtime_queue_item.setdefault("direct_execution", False)

    return {
        "schema": RUNTIME_DISPATCH_REQUEST_SCHEMA,
        "package_id": package_id,
        "task_id": str(runtime_queue_item.get("task_id") or queue_record.get("task_id") or f"task-{package_id}"),
        "session_id": str(runtime_queue_item.get("session_id") or queue_record.get("session_id") or ""),
        "approved_proposal": copy.deepcopy(execution_package.get("approved_proposal") or {}),
        "approval": approval,
        "runtime_endpoint": "RuntimeDispatcher.dispatch",
        "dispatch_method": "dispatch",
        "dispatch_args": {"package_id": package_id},
        "runtime_queue_item": runtime_queue_item,
        "executable_steps": steps,
        "validation_commands": copy.deepcopy(execution_package.get("validation_commands") or []),
        "mutation_allowed": bool(execution_package.get("mutation_allowed")),
        "required_operator_approval": bool(execution_package.get("required_operator_approval", True)),
        "non_mainline_reporting_enabled": bool(
            execution_package.get("non_mainline_reporting_enabled")
        ),
        "execution_path": work_package_execution_path(),
        "dispatch_payload_only": True,
        "direct_execution": False,
        "repo_mutation_performed_by_zero": False,
        "created_at": _now(),
    }


__all__ = [
    "RUNTIME_DISPATCH_REQUEST_SCHEMA",
    "execution_package_to_runtime_dispatch_request",
]
