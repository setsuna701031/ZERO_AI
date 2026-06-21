from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from core.tasks.work_package_model import WorkPackage
from core.goals.goal_lineage_contract import (
    GOAL_LINEAGE_FIELDS,
    attach_goal_lineage,
    create_root_goal_lineage,
    extract_goal_lineage,
)


INTAKE_SCHEMA = "zero.work_package.runtime_intake.v1"
REQUIRED_FIELDS = ("title", "goal", "description", "target_files", "requirements")


class WorkPackageIntakeError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return copy.deepcopy(list(value))
    return [copy.deepcopy(value)]


def _text_list(value: Any) -> list[str]:
    return [str(item).strip() for item in _list(value) if str(item).strip()]


def _stable_package_id(payload: Mapping[str, Any]) -> str:
    explicit = str(payload.get("package_id") or "").strip()
    if explicit:
        return explicit
    identity = {
        key: copy.deepcopy(payload.get(key))
        for key in (
            "title",
            "goal",
            "description",
            "target_files",
            "requirements",
            "hard_boundary",
            "validation_commands",
        )
    }
    encoded = json.dumps(identity, sort_keys=True, ensure_ascii=False, default=str)
    return "wp-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def validate_package(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise WorkPackageIntakeError("work_package_payload_must_be_mapping")
    errors = [f"missing_required_field:{key}" for key in REQUIRED_FIELDS if key not in payload]
    warnings: list[str] = []
    if "hard_boundary" not in payload or payload.get("hard_boundary") in (None, "", [], {}):
        warnings.append("missing_hard_boundary")
    return {
        "schema": INTAKE_SCHEMA,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "contract_complete": not errors and not warnings,
    }


def normalize_package(payload: Mapping[str, Any]) -> dict[str, Any]:
    validation = validate_package(payload)
    if validation["errors"]:
        raise WorkPackageIntakeError(";".join(validation["errors"]))
    package_id = _stable_package_id(payload)
    explicit_lineage = bool(
        isinstance(payload.get("goal_lineage"), Mapping)
        or any(payload.get(field) for field in GOAL_LINEAGE_FIELDS if field != "goal_id")
    )
    lineage = (
        extract_goal_lineage(payload, require_complete=True, reject_conflicts=True)
        if explicit_lineage
        else create_root_goal_lineage(
            goal_id=str(payload.get("goal_id") or package_id),
            session_id=str(payload.get("session_id") or "") or None,
            runtime_session_id=str(payload.get("runtime_session_id") or "") or None,
        )
    )
    created_at = str(payload.get("created_at") or _now())
    return attach_goal_lineage({
        "package_id": package_id,
        "title": str(payload.get("title") or "").strip(),
        "goal": str(payload.get("goal") or "").strip(),
        "description": str(payload.get("description") or "").strip(),
        "target_files": _text_list(payload.get("target_files")),
        "requirements": _list(payload.get("requirements")),
        # Deliberately preserve absence. A warning is not a completed contract.
        "hard_boundary": copy.deepcopy(payload.get("hard_boundary")),
        "non_mainline_issue_reporting": copy.deepcopy(
            payload.get("non_mainline_issue_reporting")
        ),
        "validation_commands": _text_list(payload.get("validation_commands")),
        "completion_report_format": copy.deepcopy(payload.get("completion_report_format")),
        "status": "queued",
        "created_at": created_at,
        "updated_at": created_at,
        "session_id": lineage["session_id"],
        "runtime_session_id": lineage["runtime_session_id"],
        "task_id": str(payload.get("task_id") or f"task-{package_id}"),
        "current_step": int(payload.get("current_step") or 0),
        "progress": copy.deepcopy(
            payload.get("progress") if isinstance(payload.get("progress"), Mapping) else {}
        ),
        "warnings": list(validation["warnings"]),
        "metadata": {
            **copy.deepcopy(
                payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
            ),
            "intake_schema": INTAKE_SCHEMA,
            "contract_complete": validation["contract_complete"],
        },
    }, lineage)


def build_package_record(payload: Mapping[str, Any]) -> WorkPackage:
    return WorkPackage.from_dict(normalize_package(payload))


def submit_package(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build an intake record only; execution belongs to the runtime queue."""
    return build_package_record(payload).to_dict()


class WorkPackageIntake:
    """Formal non-executing intake surface."""

    validate_package = staticmethod(validate_package)
    normalize_package = staticmethod(normalize_package)
    build_package_record = staticmethod(build_package_record)
    submit_package = staticmethod(submit_package)


__all__ = [
    "INTAKE_SCHEMA",
    "WorkPackageIntake",
    "WorkPackageIntakeError",
    "build_package_record",
    "normalize_package",
    "submit_package",
    "validate_package",
]
