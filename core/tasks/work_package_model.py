from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping


WORK_PACKAGE_SCHEMA = "zero.work_package.runtime.v1"
WORK_PACKAGE_STATUSES = frozenset(
    {"queued", "running", "paused", "blocked", "completed", "failed", "cancelled"}
)
WORK_PACKAGE_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


@dataclass(frozen=True)
class WorkPackage:
    package_id: str
    title: str
    goal: str
    description: str
    target_files: tuple[str, ...]
    requirements: tuple[Any, ...]
    hard_boundary: Any
    non_mainline_issue_reporting: Any
    validation_commands: tuple[str, ...]
    completion_report_format: Any
    status: str
    created_at: str
    updated_at: str
    session_id: str
    task_id: str
    current_step: int = 0
    progress: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema: str = WORK_PACKAGE_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "package_id": self.package_id,
            "title": self.title,
            "goal": self.goal,
            "description": self.description,
            "target_files": list(self.target_files),
            "requirements": copy.deepcopy(list(self.requirements)),
            "hard_boundary": copy.deepcopy(self.hard_boundary),
            "non_mainline_issue_reporting": copy.deepcopy(self.non_mainline_issue_reporting),
            "validation_commands": list(self.validation_commands),
            "completion_report_format": copy.deepcopy(self.completion_report_format),
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "current_step": self.current_step,
            "progress": copy.deepcopy(self.progress),
            "warnings": list(self.warnings),
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkPackage":
        status = str(payload.get("status") or "")
        if status not in WORK_PACKAGE_STATUSES:
            raise ValueError(f"invalid_work_package_status:{status}")
        return cls(
            package_id=str(payload.get("package_id") or ""),
            title=str(payload.get("title") or ""),
            goal=str(payload.get("goal") or ""),
            description=str(payload.get("description") or ""),
            target_files=tuple(str(item) for item in payload.get("target_files") or []),
            requirements=tuple(copy.deepcopy(payload.get("requirements") or [])),
            hard_boundary=copy.deepcopy(payload.get("hard_boundary")),
            non_mainline_issue_reporting=copy.deepcopy(
                payload.get("non_mainline_issue_reporting")
            ),
            validation_commands=tuple(
                str(item) for item in payload.get("validation_commands") or []
            ),
            completion_report_format=copy.deepcopy(payload.get("completion_report_format")),
            status=status,
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            session_id=str(payload.get("session_id") or ""),
            task_id=str(payload.get("task_id") or ""),
            current_step=int(payload.get("current_step") or 0),
            progress=copy.deepcopy(
                payload.get("progress") if isinstance(payload.get("progress"), Mapping) else {}
            ),
            warnings=tuple(str(item) for item in payload.get("warnings") or []),
            metadata=copy.deepcopy(
                payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
            ),
            schema=str(payload.get("schema") or WORK_PACKAGE_SCHEMA),
        )


__all__ = [
    "WORK_PACKAGE_SCHEMA",
    "WORK_PACKAGE_STATUSES",
    "WORK_PACKAGE_TERMINAL_STATUSES",
    "WorkPackage",
]
