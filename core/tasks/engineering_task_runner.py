from __future__ import annotations

"""
ZERO Engineering Task Runner v1.

This module turns a real engineering task payload into a repeatable result
bundle while preserving the existing AER/work-package execution path.

Boundary:
- Payload normalization and result packaging only.
- No direct repository writes.
- No runtime dispatch.
- No allowlist changes.
- Execution stays in WorkPackageScheduler -> WorkPackageIntake -> run_repo_edit.
"""

import copy
from pathlib import Path
from typing import Any, Mapping

from core.planning.planner import Planner
from core.tasks.work_package_scheduler import WorkPackageScheduler


SCHEMA = "zero.engineering_task_runner.v1"
REQUIREMENT_SUMMARY_SCHEMA = "zero.engineering_task.requirement_summary.v1"
FINAL_BUNDLE_SCHEMA = "zero.engineering_task.result_bundle.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _normalize_relative_path(value: Any) -> str:
    return _clean_text(value).replace("\\", "/")


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _task_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    package = payload.get("package")
    if isinstance(package, Mapping):
        return dict(package)
    work_package = payload.get("work_package")
    if isinstance(work_package, Mapping):
        return dict(work_package)
    return dict(payload)


def _raw_edit_payloads(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    task = _task_payload(payload)
    edits = task.get("edits")
    if isinstance(edits, list):
        return [dict(item) for item in edits if isinstance(item, Mapping)]

    edit = task.get("edit")
    if isinstance(edit, list):
        return [dict(item) for item in edit if isinstance(item, Mapping)]
    if isinstance(edit, Mapping):
        return [dict(edit)]

    target_path = task.get("target_path") or task.get("path")
    operation = task.get("operation")
    if target_path or operation:
        edit_payload: dict[str, Any] = {
            "operation": _clean_text(operation, "write_file"),
            "target_path": _normalize_relative_path(target_path),
            "content": str(task.get("content") or ""),
        }
        verify_contains = _clean_text(task.get("verify_contains") or task.get("expect_contains"))
        if verify_contains:
            edit_payload["verify_contains"] = verify_contains
        return [edit_payload]

    return []


def build_requirement_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a compact operator-facing requirement summary."""

    task = _task_payload(payload)
    edits = _raw_edit_payloads(payload)
    target_files = [
        _normalize_relative_path(item.get("target_path") or item.get("path"))
        for item in edits
        if _normalize_relative_path(item.get("target_path") or item.get("path"))
    ]
    package_id = _clean_text(
        task.get("package_id") or task.get("task_id") or payload.get("task_id"),
        "engineering_task",
    )
    goal = _clean_text(task.get("goal") or task.get("title") or payload.get("goal"), package_id)
    acceptance = task.get("acceptance") or task.get("acceptance_criteria")
    if isinstance(acceptance, str):
        acceptance_items = [acceptance]
    elif isinstance(acceptance, list):
        acceptance_items = [str(item) for item in acceptance if str(item).strip()]
    else:
        acceptance_items = []

    return {
        "schema": REQUIREMENT_SUMMARY_SCHEMA,
        "package_id": package_id,
        "goal": goal,
        "mode": _clean_text(task.get("mode"), "execute"),
        "approval": bool(task.get("approval") or task.get("approved")),
        "target_files": target_files,
        "operation_count": len(edits),
        "acceptance": acceptance_items,
        "verification_expectations": [
            _clean_text(item.get("verify_contains") or item.get("expect_contains"))
            for item in edits
            if _clean_text(item.get("verify_contains") or item.get("expect_contains"))
        ],
    }


def _force_transactional_execute_payload(work_package: Mapping[str, Any], source_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Force execute tasks through the existing multi-edit transaction path."""

    package = copy.deepcopy(dict(work_package))
    if _clean_text(package.get("mode"), "execute") != "execute":
        return package
    if isinstance(package.get("edits"), list):
        return package

    raw_edits = _raw_edit_payloads(source_payload)
    if raw_edits:
        package["edits"] = raw_edits
        package.pop("edit", None)
    return package


def normalize_engineering_task_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a real engineering task into the existing work-package contract."""

    planner = Planner()
    normalized = planner.normalize_aer_execution_intent(dict(payload), user_input=_clean_text(payload.get("goal")))
    work_package = normalized.get("work_package") if isinstance(normalized, Mapping) else None
    if not isinstance(work_package, Mapping):
        raise ValueError("engineering_task_payload_did_not_normalize_to_work_package")

    work_package_payload = _force_transactional_execute_payload(work_package, payload)
    work_package_payload.pop("repo_root", None)
    return {
        "schema": "zero.engineering_task.normalized_payload.v1",
        "intent": "work_package",
        "work_package": work_package_payload,
        "normalizer": "Planner.normalize_aer_execution_intent",
        "transactional_execute_payload": isinstance(work_package_payload.get("edits"), list),
    }


def build_result_bundle(
    *,
    requirement_summary: Mapping[str, Any],
    normalized_payload: Mapping[str, Any],
    schedule_record: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose the complete engineering result bundle to the caller."""

    work_package_result = _as_mapping(schedule_record.get("result"))
    verification_result = _as_mapping(work_package_result.get("verification_result"))
    verification_set = _as_mapping(work_package_result.get("verification_set"))
    rollback_status = _as_mapping(work_package_result.get("rollback_status"))
    change_set = _as_mapping(work_package_result.get("change_set"))
    edit_plan = _as_mapping(work_package_result.get("edit_plan") or work_package_result.get("plan"))
    impact_analysis = _as_mapping(work_package_result.get("impact_analysis"))

    return {
        "schema": FINAL_BUNDLE_SCHEMA,
        "ok": bool(work_package_result.get("ok")),
        "status": str(schedule_record.get("status") or work_package_result.get("status") or ""),
        "package_id": str(work_package_result.get("package_id") or requirement_summary.get("package_id") or ""),
        "requirement_summary": dict(requirement_summary),
        "normalized_payload": dict(normalized_payload),
        "edit_plan": edit_plan,
        "impact_analysis": impact_analysis,
        "change_set": change_set,
        "execution_result": _as_mapping(work_package_result.get("execution_result")),
        "verification_result": verification_result,
        "verification_set": verification_set,
        "rollback_status": rollback_status,
        "rollback_performed": bool(work_package_result.get("rollback_performed")),
        "work_package_result": work_package_result,
        "scheduler_record": dict(schedule_record),
        "artifact_paths": {
            "audit_path": str(work_package_result.get("audit_path") or ""),
            "evidence_path": str(work_package_result.get("evidence_path") or ""),
            "result_path": str(work_package_result.get("result_path") or ""),
            "report_path": str(work_package_result.get("report_path") or ""),
        },
        "execution_path": {
            "schema": "zero.engineering_task.execution_path.v1",
            "existing_aer_work_package_path": "Planner.normalize_aer_execution_intent -> WorkPackageScheduler.submit -> submit_work_package",
            "existing_controlled_edit_path": "WorkPackageIntake._execute_controlled_multi_write -> _apply_controlled_repo_write -> run_repo_edit",
            "existing_change_set_bundle": bool(change_set),
            "existing_transaction_rollback_verification": True,
            "no_new_runtime_path": True,
            "direct_write_shortcut": False,
        },
    }


def run_engineering_task(
    payload: Mapping[str, Any],
    *,
    repo_root: str | Path,
) -> dict[str, Any]:
    """Run a real engineering task through ZERO's work-package path."""

    if not isinstance(payload, Mapping):
        raise ValueError("engineering_task_payload_must_be_mapping")

    requirement_summary = build_requirement_summary(payload)
    normalized_payload = normalize_engineering_task_payload(payload)
    work_package_payload = _as_mapping(normalized_payload.get("work_package"))
    scheduler = WorkPackageScheduler(repo_root=repo_root)
    schedule_record = scheduler.submit(work_package_payload, execute=True)
    result_bundle = build_result_bundle(
        requirement_summary=requirement_summary,
        normalized_payload=normalized_payload,
        schedule_record=schedule_record,
    )

    return {
        "schema": SCHEMA,
        "ok": bool(result_bundle.get("ok")),
        "mode": "engineering_task_runner",
        "package_id": result_bundle["package_id"],
        "requirement_summary": requirement_summary,
        "normalized_payload": normalized_payload,
        "result_bundle": result_bundle,
        "work_package_result": result_bundle["work_package_result"],
        "verification_result": result_bundle["verification_result"],
        "change_set": result_bundle["change_set"],
        "final_message": str(result_bundle["work_package_result"].get("final_message") or ""),
    }


__all__ = [
    "FINAL_BUNDLE_SCHEMA",
    "REQUIREMENT_SUMMARY_SCHEMA",
    "SCHEMA",
    "build_requirement_summary",
    "build_result_bundle",
    "normalize_engineering_task_payload",
    "run_engineering_task",
]
