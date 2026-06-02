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
from core.repo_sandbox.tool import run_repo_edit


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
        "target_file": response.get("target_file") or response.get("target_path"),
        "verification_result": response.get("verification_result"),
        "audit_path": response.get("audit_path"),
        "evidence_path": response.get("evidence_path"),
        "result_path": response.get("result_path"),
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

    if normalized == "README.md":
        return True, "controlled_root_file_write_allowed", CONTROLLED_CORE_WRITE_GUARD_COMPAT

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


def _verification_expectation(raw_payload: Mapping[str, Any]) -> str:
    verification = raw_payload.get("verification")
    if isinstance(verification, Mapping):
        return str(verification.get("expect_contains") or verification.get("contains") or "")
    return str(raw_payload.get("verify_contains") or raw_payload.get("expect_contains") or "")


def _verify_target_content(*, target_path: Path, expected_text: str) -> dict[str, Any]:
    exists = target_path.exists() and target_path.is_file()
    actual_text = target_path.read_text(encoding="utf-8", errors="replace") if exists else ""
    if expected_text:
        matched = expected_text in actual_text
        reason = "expected_text_found" if matched else "expected_text_missing"
    else:
        matched = exists
        reason = "target_file_exists" if matched else "target_file_missing"
    return {
        "schema": "zero.work_package.verification_result.v1",
        "ok": bool(matched),
        "exists": bool(exists),
        "expect_contains": expected_text,
        "reason": reason,
        "actual_size": len(actual_text),
    }


def _apply_controlled_repo_write(
    *,
    repo_root: Path,
    target_path: str,
    operation: str,
    content: str,
    instruction: str,
) -> dict[str, Any]:
    target = _repo_path(repo_root, target_path)
    before_exists = target.exists()
    before_text = target.read_text(encoding="utf-8") if before_exists and target.is_file() else ""

    if before_exists:
        if operation == "append_file":
            payload = {
                "file_path": target_path,
                "instruction": instruction,
                "mode": "replace_file",
                "new_content": before_text + content,
            }
        elif operation in {"create_file", "write_file"}:
            payload = {
                "file_path": target_path,
                "instruction": instruction,
                "mode": "replace_file",
                "new_content": content,
            }
        else:
            raise WorkPackageExecutionRejected(f"operation_not_allowed:{operation}")

        tool_result = run_repo_edit(payload, repo_root=repo_root)
        after_text = target.read_text(encoding="utf-8") if target.exists() and target.is_file() else ""
        return {
            "ok": tool_result.get("status") == "success" and bool(tool_result.get("applied_to_workspace")),
            "status": tool_result.get("status"),
            "error": tool_result.get("error"),
            "before_exists": before_exists,
            "before_text": before_text,
            "after_text": after_text,
            "changed_files": list(tool_result.get("changed_files") or []),
            "controlled_repo_write": tool_result,
            "write_path": "repo_sandbox_tool",
        }

    if operation not in {"create_file", "write_file"}:
        raise WorkPackageExecutionRejected("append_target_must_exist")

    tool_result = run_repo_edit(
        {
            "file_path": target_path,
            "instruction": instruction,
            "mode": "create_file",
            "new_content": content,
        },
        repo_root=repo_root,
    )
    after_text = target.read_text(encoding="utf-8") if target.exists() and target.is_file() else ""
    ok = tool_result.get("status") == "success" and bool(tool_result.get("applied_to_workspace"))
    return {
        "ok": ok,
        "status": tool_result.get("status"),
        "error": tool_result.get("error"),
        "before_exists": before_exists,
        "before_text": before_text,
        "after_text": after_text,
        "changed_files": list(tool_result.get("changed_files") or []),
        "controlled_repo_write": tool_result,
        "write_path": "repo_sandbox_tool_create",
    }


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
            "target_file": request.scope_paths[0] if request.scope_paths else "",
            "target_path": request.scope_paths[0] if request.scope_paths else "",
            "verification_result": {
                "schema": "zero.work_package.verification_result.v1",
                "ok": False,
                "reason": "blocked_before_verification",
            },
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

    edit_payload = raw_payload.get("edit") if isinstance(raw_payload.get("edit"), Mapping) else raw_payload
    if isinstance(edit_payload, Mapping) and str(edit_payload.get("operation") or "").strip() == "summarize_action_items":
        return _execute_summary_action_items(
            repo_root=repo_root,
            request=request,
            raw_payload=raw_payload,
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

    try:
        write_result = _apply_controlled_repo_write(
            repo_root=repo_root,
            target_path=target_path,
            operation=edit_plan.operation,
            content=edit_plan.content,
            instruction=request.instructions or request.title,
        )
    except WorkPackageExecutionRejected as exc:
        return _blocked_execute_response(
            repo_root=repo_root,
            request=request,
            reason=str(exc),
            approval_required=False,
            error=str(exc),
        )

    if not bool(write_result.get("ok")):
        reason = str(write_result.get("error") or "controlled_repo_write_failed")
        return _blocked_execute_response(
            repo_root=repo_root,
            request=request,
            reason=reason,
            approval_required=False,
            error=reason,
        )

    before_exists = bool(write_result.get("before_exists"))
    before_text = str(write_result.get("before_text") or "")
    after_text = str(write_result.get("after_text") or "")
    verify_expected = _verification_expectation(raw_payload) or edit_plan.content
    verification_result = _verify_target_content(target_path=target, expected_text=verify_expected)
    changed = before_text != after_text
    evidence = {
        "schema": "zero.work_package.controlled_write_execution_evidence.v6_3",
        "package_id": request.package_id,
        "operation": edit_plan.operation,
        "target_path": target_path,
        "before_exists": before_exists,
        "before_size": len(before_text),
        "after_size": len(after_text),
        "changed": changed,
        "timestamp": time.time(),
        "approval": True,
        "guard": guard,
        "policy_reason": policy_reason,
        "write_path": str(write_result.get("write_path") or ""),
        "controlled_repo_write": write_result.get("controlled_repo_write"),
        "verification_result": verification_result,
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
        f"- Verification: `{str(verification_result['ok']).lower()}`",
        "",
        "## Evidence",
        "",
        f"- Before exists: `{str(before_exists).lower()}`",
        f"- Before size: `{evidence['before_size']}`",
        f"- After size: `{evidence['after_size']}`",
        f"- Verification reason: `{verification_result['reason']}`",
        "",
    ]
    _write_report(repo_root, request.report_path, "\n".join(report_lines))

    response = _base_response(request)
    response.update(
        {
            "ok": bool(verification_result["ok"]),
            "blocked": False if bool(verification_result["ok"]) else True,
            "approval_required": False,
            "reason": _public_success_reason(guard=guard) if bool(verification_result["ok"]) else "verification_failed",
            "error": None if bool(verification_result["ok"]) else "verification_failed",
            "target_file": target_path,
            "target_path": target_path,
            "verification_result": verification_result,
            "edit_plan": edit_plan.to_dict(),
            "evidence": evidence,
            "changed_files": [target_path] if changed else [],
        }
    )
    return response


def _summary_text(source_text: str) -> str:
    cleaned = " ".join(str(source_text or "").split())
    if not cleaned:
        return "Summary: input was empty.\n"
    return f"Summary: {cleaned}\n"


def _action_items_text(source_text: str) -> str:
    text = str(source_text or "").strip()
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        marker_index = stripped.lower().find("action:")
        if marker_index >= 0:
            action = stripped[marker_index + len("action:"):].strip()
            if action:
                items.append(action.rstrip("."))
    if not items:
        items.append("Review the generated summary and confirm next steps")
    return "\n".join(f"- {item}" for item in items) + "\n"


def _execute_summary_action_items(
    *,
    repo_root: Path,
    request: WorkPackageRequest,
    raw_payload: Mapping[str, Any],
) -> dict[str, Any]:
    edit = raw_payload.get("edit") if isinstance(raw_payload.get("edit"), Mapping) else raw_payload
    source_path = _normalize_target_path(str(edit.get("source_path") or edit.get("input_path") or ""))
    summary_path = _normalize_target_path(str(edit.get("summary_path") or ""))
    action_items_path = _normalize_target_path(str(edit.get("action_items_path") or ""))

    if not source_path:
        return _blocked_execute_response(
            repo_root=repo_root,
            request=request,
            reason="source_path_required",
            approval_required=False,
            error="source_path_required",
        )

    try:
        source = _repo_path(repo_root, source_path)
        summary_target = _repo_path(repo_root, summary_path)
        action_target = _repo_path(repo_root, action_items_path)
    except ValueError as exc:
        return _blocked_execute_response(
            repo_root=repo_root,
            request=request,
            reason=str(exc),
            approval_required=False,
            error=str(exc),
        )

    if not source.is_file():
        return _blocked_execute_response(
            repo_root=repo_root,
            request=request,
            reason=f"source_path_not_found:{source_path}",
            approval_required=False,
            error=f"source_path_not_found:{source_path}",
        )

    for output_path in (summary_path, action_items_path):
        allowed, policy_reason, _guard = _controlled_write_policy(output_path)
        if not allowed:
            return _blocked_execute_response(
                repo_root=repo_root,
                request=request,
                reason=policy_reason,
                approval_required=False,
                error=policy_reason,
            )

    source_text = source.read_text(encoding="utf-8")
    outputs = {
        summary_path: _summary_text(source_text),
        action_items_path: _action_items_text(source_text),
    }
    before: dict[str, dict[str, Any]] = {}
    changed_files: list[str] = []

    for relative_path, content in outputs.items():
        target = summary_target if relative_path == summary_path else action_target
        before_exists = target.exists()
        before_text = target.read_text(encoding="utf-8") if before_exists and target.is_file() else ""
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        after_text = target.read_text(encoding="utf-8")
        before[relative_path] = {
            "before_exists": before_exists,
            "before_size": len(before_text),
            "after_size": len(after_text),
            "changed": before_text != after_text,
        }
        if before_text != after_text:
            changed_files.append(relative_path)

    evidence = {
        "schema": "zero.work_package.summary_action_items_evidence.v1",
        "package_id": request.package_id,
        "operation": "summarize_action_items",
        "source_path": source_path,
        "summary_path": summary_path,
        "action_items_path": action_items_path,
        "source_size": len(source_text),
        "outputs": before,
        "changed_files": list(changed_files),
        "timestamp": time.time(),
        "approval": True,
        "guard": CONTROLLED_WORKSPACE_WRITE_GUARD,
        "policy_reason": "controlled_workspace_write_allowed",
    }

    report_lines = [
        f"# {request.title}",
        "",
        f"- Package ID: `{request.package_id}`",
        "- Mode: `execute`",
        "- Operation: `summarize_action_items`",
        f"- Source: `{source_path}`",
        f"- Summary: `{summary_path}`",
        f"- Action items: `{action_items_path}`",
        "- Approval: `true`",
        f"- Guard: `{CONTROLLED_WORKSPACE_WRITE_GUARD}`",
        "- Policy: `controlled_workspace_write_allowed`",
        "",
        "## Evidence",
        "",
        f"- Source size: `{len(source_text)}`",
        f"- Changed files: `{', '.join(changed_files)}`",
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
            "edit_plan": {
                "schema": "zero.work_package.document_task_plan.v1",
                "operation": "summarize_action_items",
                "source_path": source_path,
                "summary_path": summary_path,
                "action_items_path": action_items_path,
            },
            "evidence": evidence,
            "changed_files": changed_files,
            "result": {
                "summary_path": summary_path,
                "action_items_path": action_items_path,
                "summary": outputs[summary_path],
                "action_items": outputs[action_items_path],
            },
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
