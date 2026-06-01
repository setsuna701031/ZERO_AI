from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "zero.work_package.execution_guard.v6_2"

ALLOWED_WORKSPACE_PREFIX = "workspace/"
ALLOWED_CORE_PREFIX = "core/tasks/work_package_"
ALLOWED_OPERATIONS = frozenset({"create_file", "write_file", "append_file"})
BLOCKED_PREFIXES = (
    "core/agent/",
    "core/runtime/",
    "core/tasks/scheduler.py",
    "tests/",
    "runtime/",
    ".git/",
    "docs/",
)


class WorkPackageExecutionRejected(PermissionError):
    pass


@dataclass(frozen=True)
class ExecutionGuardDecision:
    ok: bool
    operation: str
    target_path: str
    reason: str
    schema: str = SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema": self.schema,
            "operation": self.operation,
            "target_path": self.target_path,
            "reason": self.reason,
        }


def normalize_relative_target(path: Any) -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text:
        raise WorkPackageExecutionRejected("target_path_required")

    candidate = Path(text)
    if candidate.is_absolute():
        raise WorkPackageExecutionRejected("absolute_paths_are_not_allowed")

    parts = candidate.parts
    if any(part in ("..", "") for part in parts):
        raise WorkPackageExecutionRejected("path_must_not_escape_repo")

    normalized = "/".join(parts)
    if not normalized:
        raise WorkPackageExecutionRejected("target_path_required")

    return normalized


def _is_workspace_target(target_path: str) -> bool:
    return target_path.startswith(ALLOWED_WORKSPACE_PREFIX) and target_path != "workspace/"


def _is_allowlisted_core_target(target_path: str) -> bool:
    if not target_path.startswith(ALLOWED_CORE_PREFIX):
        return False
    if not target_path.endswith(".py"):
        return False
    return target_path.count("/") == 2


def validate_execute_target(path: str) -> bool:
    try:
        decision = validate_execute_request({"operation": "write_file", "target_path": path})
        return bool(decision.ok)
    except WorkPackageExecutionRejected:
        return False


def validate_execute_request(payload: Mapping[str, Any]) -> ExecutionGuardDecision:
    if not isinstance(payload, Mapping):
        raise WorkPackageExecutionRejected("execute_payload_must_be_mapping")

    operation = str(payload.get("operation") or "").strip()
    if operation not in ALLOWED_OPERATIONS:
        raise WorkPackageExecutionRejected(f"operation_not_allowed:{operation or 'missing'}")

    target_path = normalize_relative_target(payload.get("target_path") or payload.get("path"))

    for blocked in BLOCKED_PREFIXES:
        if target_path == blocked.rstrip("/") or target_path.startswith(blocked):
            raise WorkPackageExecutionRejected(f"blocked_target_prefix:{blocked.rstrip('/')}")

    if _is_workspace_target(target_path):
        return ExecutionGuardDecision(
            ok=True,
            operation=operation,
            target_path=target_path,
            reason="workspace_target_allowed",
        )

    if _is_allowlisted_core_target(target_path):
        return ExecutionGuardDecision(
            ok=True,
            operation=operation,
            target_path=target_path,
            reason="allowlisted_core_work_package_target_allowed",
        )

    raise WorkPackageExecutionRejected("target_not_in_execute_allowlist")


__all__ = [
    "ALLOWED_CORE_PREFIX",
    "ALLOWED_OPERATIONS",
    "ALLOWED_WORKSPACE_PREFIX",
    "BLOCKED_PREFIXES",
    "ExecutionGuardDecision",
    "SCHEMA",
    "WorkPackageExecutionRejected",
    "normalize_relative_target",
    "validate_execute_request",
    "validate_execute_target",
]
