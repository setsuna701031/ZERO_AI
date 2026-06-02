from __future__ import annotations

"""
ZERO Work Package Intake v6.4.

Mode enforcement:
- explore: read-only audit.
- plan: non-mutating plan report.
- execute: approval + execution guard + one controlled write policy.
- verify: non-mutating verification-mode report.

v6.4 consolidates workspace/core execute behavior behind one internal policy.
Legacy workspace reason strings are kept only as outward compatibility aliases
for existing readonly_audit execute callers; the actual allow/block decisions
are not duplicated.
"""

import time
import json
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


SCHEMA = "zero.work_package.intake_result.v6_4"

CONTROLLED_CORE_WRITE_GUARD = "controlled_core_write_v6_4"
CONTROLLED_CORE_WRITE_GUARD_COMPAT = "controlled_core_write_v6_3"
CONTROLLED_WORKSPACE_WRITE_GUARD = "workspace_only"


def _normalize_target_path(relative_path: str) -> str:
    return str(relative_path or "").replace("\\", "/")


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


def _write_json_artifact(repo_root: Path, relative_path: str, payload: Mapping[str, Any]) -> None:
    path = _repo_path(repo_root, relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _safe_artifact_id(package_id: str) -> str:
    safe = []
    for char in str(package_id or "work_package"):
        if char.isalnum() or char in ("-", "_", "."):
            safe.append(char)
        else:
            safe.append("_")
    cleaned = "".join(safe).strip("._-")
    return cleaned or "work_package"


def _artifact_paths(request: WorkPackageRequest) -> dict[str, str]:
    artifact_id = _safe_artifact_id(request.package_id)
    base = f"workspace/work_packages/artifacts/{artifact_id}"
    return {
        "audit_path": f"{base}_audit.json",
        "evidence_path": f"{base}_evidence.json",
        "result_path": f"{base}_result.json",
    }


def _base_response(request: WorkPackageRequest) -> dict[str, Any]:
    artifact_paths = _artifact_paths(request)
    return {
        "schema": SCHEMA,
        "package_id": request.package_id,
        "task_id": request.package_id,
        "kind": request.kind,
        "mode": request.mode.value,
        "execution_mode": request.mode.value,
        "report_path": request.report_path,
        "audit_path": artifact_paths["audit_path"],
        "evidence_path": artifact_paths["evidence_path"],
        "result_path": artifact_paths["result_path"],
        "mutation_allowed": request.mutation_allowed,
        "readonly": request.readonly,
    }


def _final_message(result: Mapping[str, Any]) -> str:
    if result.get("final_message"):
        return str(result.get("final_message") or "")
    if result.get("reason"):
        return str(result.get("reason") or "")
    if result.get("error"):
        return str(result.get("error") or "")
    if bool(result.get("ok")):
        return "work package completed"
    return "work package failed"


def _finalize_artifacts(repo_root: Path, request: WorkPackageRequest, response: dict[str, Any]) -> dict[str, Any]:
    status = "ok" if bool(response.get("ok")) else "failed"
    response.setdefault("status", status)
    response.setdefault("execution_mode", request.mode.value)
    response.setdefault("task_id", request.package_id)
    response["final_message"] = _final_message(response)

    evidence_payload = response.get("evidence")
    if not isinstance(evidence_payload, Mapping):
        evidence_payload = {
            "schema": "zero.work_package.execution_evidence.v1",
            "package_id": request.package_id,
            "mode": request.mode.value,
            "ok": bool(response.get("ok")),
            "blocked": bool(response.get("blocked", False)),
            "report_path": response.get("report_path"),
            "timestamp": time.time(),
        }

    audit_payload = {
        "schema": "zero.work_package.audit_record.v1",
        "package_id": request.package_id,
        "task_id": request.package_id,
        "mode": request.mode.value,
        "status": status,
        "ok": bool(response.get("ok")),
        "blocked": bool(response.get("blocked", False)),
        "reason": str(response.get("reason") or response.get("error") or ""),
        "report_path": response.get("report_path"),
        "evidence_path": response.get("evidence_path"),
        "result_path": response.get("result_path"),
        "timestamp": time.time(),
    }

    result_payload = {
        "schema": "zero.work_package.final_result.v1",
        "package_id": request.package_id,
        "task_id": request.package_id,
        "status": status,
        "ok": bool(response.get("ok")),
        "execution_mode": request.mode.value,
        "audit_path": response.get("audit_path"),
        "evidence_path": response.get("evidence_path"),
        "report_path": response.get("report_path"),
        "final_message": response["final_message"],
        "result": response,
    }

    _write_json_artifact(repo_root, str(response["evidence_path"]), evidence_payload)
    _write_json_artifact(repo_root, str(response["audit_path"]), audit_payload)
    _write_json_artifact(repo_root, str(response["result_path"]), result_payload)
    return response


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


def _controlled_write_policy(target_path: str) -> tuple[bool, str, str]:
    normalized = _normalize_target_path(target_path)

    if normalized.startswith("core/runtime/"):
        return False, "controlled_core_write_blocked:runtime", CONTROLLED_CORE_WRITE_GUARD_COMPAT

    if normalized.startswith("core/agent/"):
        return False, "controlled_core_write_blocked:agent", CONTROLLED_CORE_WRITE_GUARD_COMPAT

    if normalized == "core/tasks/scheduler.py":
        return False, "controlled_core_write_blocked:scheduler", CONTROLLED_CORE_WRITE_GUARD_COMPAT

    if normalized.startswith("tests/"):
        return False, "controlled_core_write_blocked:tests", CONTROLLED_CORE_WRITE_GUARD_COMPAT

    if normalized.startswith("core/tasks/work_package_") and normalized.endswith(".py"):
        return True, "controlled_core_write_allowed", CONTROLLED_CORE_WRITE_GUARD_COMPAT

    if normalized.startswith("workspace/"):
        return True, "controlled_workspace_write_allowed", CONTROLLED_WORKSPACE_WRITE_GUARD

    return False, "controlled_core_write_blocked:not_allowlisted", CONTROLLED_CORE_WRITE_GUARD_COMPAT


def _legacy_execute_alias_required(request: WorkPackageRequest) -> bool:
    return request.kind == "readonly_audit" and request.mode == WorkPackageMode.EXECUTE


def _public_block_reason(request: WorkPackageRequest, reason: str) -> str:
    """
    Keep one internal policy while preserving old readonly_audit execute output.

    The workspace execution tests still assert the older operator-facing reason
    strings. Core-write tests assert the v6.3 reason strings. This function is
    intentionally a presentation/compatibility alias only; it does not decide
    whether a write is allowed.
    """

    if not _legacy_execute_alias_required(request):
        return reason

    if reason.startswith("path_escapes_repo:"):
        return reason.replace("path_escapes_repo:", "path_must_not_escape_repo:", 1)

    if reason.startswith("controlled_core_write_blocked:"):
        blocked_area = reason.rsplit(":", 1)[-1]
        if blocked_area in {"runtime", "agent", "scheduler", "tests", "not_allowlisted"}:
            return f"blocked_target_prefix:core:{reason}"

    return reason


def _public_success_reason(*, guard: str) -> str:
    if guard == CONTROLLED_WORKSPACE_WRITE_GUARD:
        return "controlled_workspace_execution_completed"
    return "controlled_write_execution_completed"


def _blocked_execute_response(
    *,
    repo_root: Path,
    request: WorkPackageRequest,
    reason: str,
    approval_required: bool,
    error: str | None = None,
) -> dict[str, Any]:
    public_reason = _public_block_reason(request, reason)
    public_error = public_reason if error is not None else None
    plan = build_work_package_plan(request)
    _write_report(repo_root, request.report_path, _plan_report(request))
    response = _base_response(request)
    response.update(
        {
            "ok": False,
            "blocked": True,
            "approval_required": approval_required,
            "reason": public_reason,
            "plan": plan.to_dict(),
        }
    )
    if public_error is not None:
        response["error"] = public_error
    return response


def _execute_controlled_write(
    *,
    repo_root: Path,
    request: WorkPackageRequest,
    raw_payload: Mapping[str, Any],
) -> dict[str, Any]:
    if not request.approval:
        return _blocked_execute_response(
            repo_root=repo_root,
            request=request,
            reason="execute_requires_approval",
            approval_required=True,
        )

    try:
        edit_plan = edit_plan_from_work_package_payload(raw_payload)
    except WorkPackageExecutionRejected as exc:
        return _blocked_execute_response(
            repo_root=repo_root,
            request=request,
            reason=str(exc),
            approval_required=False,
            error=str(exc),
        )

    target_path = _normalize_target_path(edit_plan.target_path)

    try:
        target = _repo_path(repo_root, target_path)
    except ValueError as exc:
        return _blocked_execute_response(
            repo_root=repo_root,
            request=request,
            reason=str(exc),
            approval_required=False,
            error=str(exc),
        )

    allowed, policy_reason, guard = _controlled_write_policy(target_path)
    if not allowed:
        return _blocked_execute_response(
            repo_root=repo_root,
            request=request,
            reason=policy_reason,
            approval_required=False,
            error=policy_reason,
        )

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
                "approval_required": False,
                "reason": f"operation_not_allowed:{edit_plan.operation}",
                "error": f"operation_not_allowed:{edit_plan.operation}",
            }
        )
        return response

    after_text = target.read_text(encoding="utf-8")
    evidence = {
        "schema": "zero.work_package.controlled_write_execution_evidence.v6_3",
        "package_id": request.package_id,
        "operation": edit_plan.operation,
        "target_path": target_path,
        "before_exists": before_exists,
        "before_size": len(before_text),
        "after_size": len(after_text),
        "changed": before_text != after_text,
        "timestamp": time.time(),
        "approval": True,
        "guard": guard,
        "policy_reason": policy_reason,
    }

    report_lines = [
        f"# {request.title}",
        "",
        f"- Package ID: `{request.package_id}`",
        f"- Mode: `execute`",
        f"- Operation: `{edit_plan.operation}`",
        f"- Target: `{target_path}`",
        "- Approval: `true`",
        f"- Guard: `{guard}`",
        f"- Policy: `{policy_reason}`",
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
            "reason": _public_success_reason(guard=guard),
            "edit_plan": edit_plan.to_dict(),
            "evidence": evidence,
            "changed_files": [target_path] if evidence["changed"] else [],
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
        return _finalize_artifacts(root, request, response)

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
        return _finalize_artifacts(root, request, response)

    if request.mode == WorkPackageMode.EXECUTE:
        response = _execute_controlled_write(
            repo_root=root,
            request=request,
            raw_payload=raw_payload,
        )
        return _finalize_artifacts(root, request, response)

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
        return _finalize_artifacts(root, request, response)

    response = _base_response(request)
    response.update(
        {
            "ok": False,
            "error": f"unsupported_work_package_mode:{request.mode.value}",
        }
    )
    return _finalize_artifacts(root, request, response)


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
