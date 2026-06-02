from __future__ import annotations

"""
ZERO Work Package Edit Plan v6.1.

Edit plans are intentionally narrow. They describe controlled workspace writes
only and rely on work_package_execution_guard before execution.
"""

from dataclasses import dataclass
from typing import Any, Mapping

from core.tasks.work_package_execution_guard import validate_execute_request


SCHEMA = "zero.work_package.edit_plan.v6_1"

OPERATION_ALIASES = {
    "append": "append_file",
    "create": "create_file",
    "write": "write_file",
    "workspace_append": "append_file",
    "workspace_write": "write_file",
}


def normalize_edit_operation(operation: Any) -> str:
    text = str(operation or "").strip()
    return OPERATION_ALIASES.get(text, text)


@dataclass(frozen=True)
class WorkPackageEditPlan:
    operation: str
    target_path: str
    content: str = ""
    schema: str = SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "operation": self.operation,
            "target_path": self.target_path,
            "content": self.content,
        }


def build_edit_plan(payload: Mapping[str, Any]) -> WorkPackageEditPlan:
    """Build and validate a single controlled edit plan."""

    decision = validate_execute_request(payload)
    return WorkPackageEditPlan(
        operation=decision.operation,
        target_path=decision.target_path,
        content=str(payload.get("content") or ""),
    )


def edit_plan_from_work_package_payload(payload: Mapping[str, Any]) -> WorkPackageEditPlan:
    """Extract edit operation fields from a work package request payload."""

    edit = payload.get("edit")
    if isinstance(edit, Mapping):
        source = edit
    else:
        source = payload

    return build_edit_plan(
        {
            "operation": normalize_edit_operation(source.get("operation")),
            "target_path": source.get("target_path") or source.get("path"),
            "content": source.get("content") or "",
        }
    )


__all__ = [
    "SCHEMA",
    "WorkPackageEditPlan",
    "build_edit_plan",
    "edit_plan_from_work_package_payload",
]
