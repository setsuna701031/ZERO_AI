from __future__ import annotations

"""
ZERO Work Package Execution Guard v6.1.

This guard is the authority boundary for work-package execute mode.

v6.1 policy:
- Only workspace/ relative targets are writable.
- Absolute paths are rejected.
- Parent traversal is rejected.
- Core/runtime/tests/.git paths are rejected.
- Only create_file / write_file / append_file are allowed.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "zero.work_package.execution_guard.v6_1"

ALLOWED_WORKSPACE_PREFIX = "workspace/"
ALLOWED_OPERATIONS = frozenset({"create_file", "write_file", "append_file"})
BLOCKED_PREFIXES = (
    "core/",
    "tests/",
    "runtime/",
    ".git/",
    "docs/",
)


class WorkPackageExecutionRejected(PermissionError):
    """Raised when execute mode violates the work-package guard."""


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

    if target_path != "workspace" and not target_path.startswith(ALLOWED_WORKSPACE_PREFIX):
        raise WorkPackageExecutionRejected("target_must_be_under_workspace")

    if target_path == "workspace":
        raise WorkPackageExecutionRejected("target_must_be_file_under_workspace")

    return ExecutionGuardDecision(
        ok=True,
        operation=operation,
        target_path=target_path,
        reason="workspace_target_allowed",
    )


__all__ = [
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
