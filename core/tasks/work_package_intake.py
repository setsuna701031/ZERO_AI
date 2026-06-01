from __future__ import annotations

"""
ZERO Work Package Intake v6.1.

Mode enforcement:
- explore: read-only audit.
- plan: non-mutating plan report.
- execute: approval + execution guard + controlled workspace write.
- verify: non-mutating verification-mode report.
"""

import time
from pathlib import Path
from typing import Any, Mapping

from core.tasks.work_package_audit_executor import execute_readonly_audit_package
from core.tasks.work_package_contract import (
    WorkPackageRequest,
    readonly_legacy_audit_package,
    validate_work_package_request,
)
from core.tasks.work_package_edit_plan import edit_plan_from_work_package_payload
from core.tasks.work_package_execution_guard import WorkPackageExecutionRejected
from core.tasks.work_package_mode import WorkPackageMode
from core.tasks.work_package_plan import build_work_package_plan


SCHEMA = "zero.work_package.intake_result.v6_1"


def _repo_path(repo_root: Path, relative_path: str) -> Path:
    root = repo_root.resolve()
    candidate = (root / relative_path).resolve()
    if root not in (candidate, *candidate.parents):
        raise ValueError(f"path_escapes_repo:{relative_path}")
    return candidate


def _write_report(repo_root: Path, relative_path: str, content: str) -> None:
    path = _repo_path(repo_root, relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _base_response(request: WorkPackageRequest) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "package_id": request.package_id,
        "kind": request.kind,
        "mode": request.mode.value,
        "report_path": request.report_path,
        "mutation_allowed": request.mutation_allowed,
        "readonly": request.readonly,
    }


def _plan_report(request: WorkPackageRequest) -> str:
    plan = build_work_package_plan(request)
    lines = [
        f"# {request.title}",
        "",
        f"- Package ID: `{request.package_id}`",
        f"- Mode: `{request.mode.value}`",
        f"- Mutation allowed: `{str(plan.mutation_allowed).lower()}`",
        f"- Approval required: `{str(plan.approval_required).lower()}`",
        f"- Blocked: `{str(plan.blocked).lower()}`",
        f"- Reason: `{plan.reason}`",
        "",
        "## Scope",
        "",
    ]
    for path in request.scope_paths:
        lines.append(f"- `{path}`")
    lines.extend(["", "## Planned actions", ""])
    for action in plan.actions:
        lines.append(f"- `{action}`")
    if request.instructions:
        lines.extend(["", "## Operator instructions", "", request.instructions])
    lines.append("")
    return "\n".join(lines)


def _execute_controlled_workspace_edit(
    *,
    repo_root: Path,
    request: WorkPackageRequest,
    raw_payload: Mapping[str, Any],
) -> dict[str, Any]:
    if not request.approval:
        plan = build_work_package_plan(request)
        _write_report(repo_root, request.report_path, _plan_report(request))
        response = _base_response(request)
        response.update(
            {
                "ok": False,
                "blocked": True,
                "approval_required": True,
                "reason": "execute_requires_approval",
                "plan": plan.to_dict(),
            }
        )
        return response

    try:
        edit_plan = edit_plan_from_work_package_payload(raw_payload)
    except WorkPackageExecutionRejected as exc:
        plan = build_work_package_plan(request)
        _write_report(repo_root, request.report_path, _plan_report(request))
        response = _base_response(request)
        response.update(
            {
                "ok": False,
                "blocked": True,
                "approval_required": False,
                "reason": str(exc),
                "plan": plan.to_dict(),
                "error": str(exc),
            }
        )
        return response

    target = _repo_path(repo_root, edit_plan.target_path)
    before_exists = target.exists()
    before_text = target.read_text(encoding="utf-8") if before_exists and target.is_file() else ""

    target.parent.mkdir(parents=True, exist_ok=True)
    if edit_plan.operation in {"create_file", "write_file"}:
        target.write_text(edit_plan.content, encoding="utf-8")
    elif edit_plan.operation == "append_file":
        with target.open("a", encoding="utf-8") as handle:
            handle.write(edit_plan.content)
    else:
        response = _base_response(request)
        response.update(
            {
                "ok": False,
                "blocked": True,
                "reason": f"operation_not_allowed:{edit_plan.operation}",
            }
        )
        return response

    after_text = target.read_text(encoding="utf-8")
    evidence = {
        "schema": "zero.work_package.controlled_workspace_execution_evidence.v6_1",
        "package_id": request.package_id,
        "operation": edit_plan.operation,
        "target_path": edit_plan.target_path,
        "before_exists": before_exists,
        "before_size": len(before_text),
        "after_size": len(after_text),
        "changed": before_text != after_text,
        "timestamp": time.time(),
        "approval": True,
        "guard": "workspace_only",
    }

    report_lines = [
        f"# {request.title}",
        "",
        f"- Package ID: `{request.package_id}`",
        f"- Mode: `execute`",
        f"- Operation: `{edit_plan.operation}`",
        f"- Target: `{edit_plan.target_path}`",
        "- Approval: `true`",
        "- Guard: `workspace_only`",
        f"- Changed: `{str(evidence['changed']).lower()}`",
        "",
        "## Evidence",
        "",
        f"- Before exists: `{str(before_exists).lower()}`",
        f"- Before size: `{evidence['before_size']}`",
        f"- After size: `{evidence['after_size']}`",
        "",
    ]
    _write_report(repo_root, request.report_path, "\n".join(report_lines))

    response = _base_response(request)
    response.update(
        {
            "ok": True,
            "blocked": False,
            "approval_required": False,
            "reason": "controlled_workspace_execution_completed",
            "edit_plan": edit_plan.to_dict(),
            "evidence": evidence,
            "changed_files": [edit_plan.target_path] if evidence["changed"] else [],
        }
    )
    return response


def submit_work_package(
    payload: Mapping[str, Any] | WorkPackageRequest,
    *,
    repo_root: str | Path,
) -> dict[str, Any]:
    """Validate and execute a work package according to mode."""

    root = Path(repo_root)

    if isinstance(payload, WorkPackageRequest):
        request = payload
        raw_payload: Mapping[str, Any] = request.to_dict()
    else:
        request = validate_work_package_request(payload)
        raw_payload = payload

    if request.mode == WorkPackageMode.EXPLORE:
        audit_result = execute_readonly_audit_package(repo_root=root, request=request)
        response = _base_response(request)
        response.update(
            {
                "ok": bool(audit_result.ok),
                "executor_schema": audit_result.schema,
                "scanned_paths": list(audit_result.scanned_paths),
                "missing_paths": list(audit_result.missing_paths),
                "finding_count": len(audit_result.findings),
                "result": audit_result.to_dict(),
            }
        )
        return response

    if request.mode == WorkPackageMode.PLAN:
        plan = build_work_package_plan(request)
        _write_report(root, request.report_path, _plan_report(request))
        response = _base_response(request)
        response.update(
            {
                "ok": True,
                "plan": plan.to_dict(),
                "finding_count": 0,
            }
        )
        return response

    if request.mode == WorkPackageMode.EXECUTE:
        return _execute_controlled_workspace_edit(
            repo_root=root,
            request=request,
            raw_payload=raw_payload,
        )

    if request.mode == WorkPackageMode.VERIFY:
        plan = build_work_package_plan(request)
        _write_report(root, request.report_path, _plan_report(request))
        response = _base_response(request)
        response.update(
            {
                "ok": True,
                "plan": plan.to_dict(),
                "finding_count": 0,
            }
        )
        return response

    response = _base_response(request)
    response.update(
        {
            "ok": False,
            "error": f"unsupported_work_package_mode:{request.mode.value}",
        }
    )
    return response


def submit_legacy_path_audit_package(
    *,
    repo_root: str | Path,
    scope_paths: list[str] | tuple[str, ...],
    report_path: str = "workspace/legacy_path_audit.md",
    instructions: str = "",
    mode: str | WorkPackageMode = WorkPackageMode.EXPLORE,
) -> dict[str, Any]:
    """Convenience entrypoint for the current ZERO hidden-path audit use case."""

    request = readonly_legacy_audit_package(
        scope_paths=scope_paths,
        report_path=report_path,
        instructions=instructions,
        mode=mode,
    )
    return submit_work_package(request, repo_root=repo_root)


__all__ = [
    "SCHEMA",
    "submit_legacy_path_audit_package",
    "submit_work_package",
]
