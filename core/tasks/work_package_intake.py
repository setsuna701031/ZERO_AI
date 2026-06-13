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
from core.reports.engineering_report_contract import attach_engineering_report


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
    response = attach_engineering_report(response, report_type="work_package")

    evidence_payload = response.get("evidence")
    if not isinstance(evidence_payload, Mapping):
        evidence_payload = {
            "schema": "zero.work_package.execution_evidence.v1",
            "package_id": request.package_id,
            "mode": request.mode.value,
            "ok": bool(response.get("ok")),
            "blocked": bool(response.get("blocked", False)),
            "change_set": response.get("change_set"),
            "verification_set": response.get("verification_set"),
            "rollback_status": response.get("rollback_status"),
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
        "target_files": response.get("target_files"),
        "changed_files": response.get("changed_files"),
        "rollback_performed": response.get("rollback_performed"),
        "plan": response.get("plan"),
        "edit_plan": response.get("edit_plan"),
        "impact_analysis": response.get("impact_analysis"),
        "change_set": response.get("change_set"),
        "execution_result": response.get("execution_result"),
        "verification_result": response.get("verification_result"),
        "verification_set": response.get("verification_set"),
        "rollback_status": response.get("rollback_status"),
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
        "target_files": response.get("target_files"),
        "changed_files": response.get("changed_files"),
        "rollback_performed": response.get("rollback_performed"),
        "plan": response.get("plan"),
        "impact_analysis": response.get("impact_analysis"),
        "change_set": response.get("change_set"),
        "execution_result": response.get("execution_result"),
        "verification_result": response.get("verification_result"),
        "verification_set": response.get("verification_set"),
        "rollback_status": response.get("rollback_status"),
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


def _edit_verification_expectation(edit_payload: Mapping[str, Any], content: str) -> str:
    verification = edit_payload.get("verification")
    if isinstance(verification, Mapping):
        expected = str(verification.get("expect_contains") or verification.get("contains") or "")
    else:
        expected = str(edit_payload.get("verify_contains") or edit_payload.get("expect_contains") or "")
    return expected or content


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


def _module_for_path(path: str) -> str:
    normalized = _normalize_target_path(path)
    parts = [part for part in normalized.split("/") if part]
    if len(parts) >= 2 and parts[0] in {"core", "tests", "workspace"}:
        return "/".join(parts[:2])
    return parts[0] if parts else ""


def _risk_level_for_targets(target_files: list[str]) -> str:
    if any(_normalize_target_path(path).startswith("core/") for path in target_files):
        return "medium"
    if len(target_files) > 1:
        return "medium"
    return "low"


def _build_structured_edit_plan(
    *,
    request: WorkPackageRequest,
    planned_edits: list[Mapping[str, Any]],
) -> dict[str, Any]:
    files_to_modify: list[dict[str, Any]] = []
    for item in planned_edits:
        target_path = _normalize_target_path(str(item.get("target_path") or ""))
        operation = str(item.get("operation") or "write_file")
        expected = str(item.get("expected") or item.get("content") or "")
        files_to_modify.append(
            {
                "path": target_path,
                "operation": operation,
                "reason": str(item.get("reason") or f"{operation} requested by work package {request.package_id}"),
                "expected_effect": str(item.get("expected_effect") or f"{operation} updates {target_path}"),
                "verification_method": str(item.get("verification_method") or f"verify target content contains {expected!r}"),
            }
        )

    target_files = [item["path"] for item in files_to_modify if item.get("path")]
    return {
        "schema": "zero.work_package.structured_edit_plan.v1",
        "task_goal": request.title,
        "package_id": request.package_id,
        "mode": request.mode.value,
        "files_to_modify": files_to_modify,
        "target_files": target_files,
        "expected_effect": "controlled repo edit updates declared target files only",
        "verification_method": "content verification for each target followed by artifact finalization",
        "valid": bool(request.package_id and files_to_modify and all(item.get("path") for item in files_to_modify)),
    }


def _build_impact_analysis(
    *,
    request: WorkPackageRequest,
    edit_plan: Mapping[str, Any],
) -> dict[str, Any]:
    target_files = [str(path) for path in edit_plan.get("target_files") or []]
    affected_modules = sorted({module for module in (_module_for_path(path) for path in target_files) if module})
    affected_tests = sorted(
        {
            "tests/test_aer_controlled_repo_edit_phase3.py",
            "tests/test_aer_controlled_repo_edit_phase4.py",
            "tests/test_aer_controlled_repo_edit_phase2.py",
            "tests/test_work_package_controlled_core_write.py",
            "tests/test_work_package_controlled_workspace_execution.py",
        }
    )
    affected_contracts = sorted(
        {
            "work_package_contract",
            "work_package_scheduler_record",
            "controlled_repo_edit_result_package",
            "controlled_repo_edit_change_set_bundle",
            "rollback_transaction",
        }
    )
    return {
        "schema": "zero.work_package.impact_analysis.v1",
        "package_id": request.package_id,
        "affected_modules": affected_modules,
        "affected_tests": affected_tests,
        "affected_contracts": affected_contracts,
        "risk_level": _risk_level_for_targets(target_files),
        "valid": bool(affected_modules and affected_tests and affected_contracts),
    }


def _execution_paths() -> dict[str, Any]:
    return {
        "schema": "zero.work_package.execution_paths.v1",
        "existing_multi_file_transaction_path": "WorkPackageIntake._execute_controlled_multi_write -> _apply_controlled_repo_write -> run_repo_edit",
        "existing_rollback_path": "WorkPackageIntake._rollback_transaction_changes -> run_repo_edit",
        "existing_verification_path": "WorkPackageIntake._verify_target_content -> _multi_verification_result",
        "no_new_runtime_path": True,
        "work_package_contract_required": True,
    }


def _execution_result_package(
    *,
    ok: bool,
    status: str,
    reason: str,
    target_files: list[str],
    changed_files: list[str],
    edit_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "zero.work_package.execution_result.v1",
        "ok": bool(ok),
        "status": status,
        "reason": reason,
        "target_files": list(target_files),
        "changed_files": list(changed_files),
        "edit_results": [dict(item) for item in edit_results or []],
    }


def _rollback_status(rollback: Mapping[str, Any] | None = None) -> dict[str, Any]:
    rollback_payload = dict(rollback or {})
    return {
        "schema": "zero.work_package.rollback_status.v1",
        "ok": bool(rollback_payload.get("ok", True)),
        "rollback_performed": bool(rollback_payload.get("rollback_performed", False)),
        "rollback_results": list(rollback_payload.get("rollback_results") or []),
    }


def _verification_set(verification_result: Mapping[str, Any]) -> dict[str, Any]:
    target_results: list[dict[str, Any]] = []
    raw_targets = verification_result.get("targets")
    if isinstance(raw_targets, list):
        for item in raw_targets:
            if isinstance(item, Mapping):
                target_results.append(dict(item))
    else:
        target_results.append({"target_path": "", "verification": dict(verification_result)})
    return {
        "schema": "zero.work_package.verification_set.v1",
        "ok": bool(verification_result.get("ok")),
        "targets": target_results,
        "verification_result": dict(verification_result),
    }


def _change_set_operations(edit_plan: Mapping[str, Any], execution_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    edit_results_by_path: dict[str, Mapping[str, Any]] = {}
    for item in execution_result.get("edit_results") or []:
        if isinstance(item, Mapping):
            edit_results_by_path[str(item.get("target_path") or "")] = item
    for index, item in enumerate(edit_plan.get("files_to_modify") or [], start=1):
        if not isinstance(item, Mapping):
            continue
        path = _normalize_target_path(str(item.get("path") or ""))
        edit_result = edit_results_by_path.get(path, {})
        operations.append(
            {
                "index": index,
                "operation": str(item.get("operation") or ""),
                "target_path": path,
                "reason": str(item.get("reason") or ""),
                "expected_effect": str(item.get("expected_effect") or ""),
                "verification_method": str(item.get("verification_method") or ""),
                "executed": bool(edit_result),
                "ok": bool(edit_result.get("ok")) if isinstance(edit_result, Mapping) else False,
            }
        )
    return operations


def _result_summary(
    *,
    execution_result: Mapping[str, Any],
    verification_set: Mapping[str, Any],
    rollback: Mapping[str, Any],
) -> dict[str, Any]:
    ok = bool(execution_result.get("ok"))
    status = str(execution_result.get("status") or ("success" if ok else "failed"))
    changed_files = list(execution_result.get("changed_files") or [])
    target_files = list(execution_result.get("target_files") or [])
    return {
        "schema": "zero.work_package.change_set_result_summary.v1",
        "ok": ok,
        "status": status,
        "reason": str(execution_result.get("reason") or ""),
        "target_file_count": len(target_files),
        "changed_file_count": len(changed_files),
        "verification_ok": bool(verification_set.get("ok")),
        "rollback_performed": bool(rollback.get("rollback_performed")),
    }


def _build_change_set_bundle(
    *,
    request: WorkPackageRequest,
    edit_plan: Mapping[str, Any],
    impact_analysis: Mapping[str, Any],
    execution_result: Mapping[str, Any],
    verification_result: Mapping[str, Any],
    rollback_status: Mapping[str, Any],
) -> dict[str, Any]:
    files = [str(path) for path in edit_plan.get("target_files") or execution_result.get("target_files") or []]
    verification = _verification_set(verification_result)
    operations = _change_set_operations(edit_plan, execution_result)
    summary = _result_summary(
        execution_result=execution_result,
        verification_set=verification,
        rollback=rollback_status,
    )
    complete = bool(
        request.package_id
        and edit_plan.get("valid")
        and impact_analysis.get("valid")
        and files
        and operations
        and verification
        and rollback_status
        and execution_result
        and summary
    )
    return {
        "schema": "zero.work_package.change_set.v1",
        "change_set_id": f"change_set:{request.package_id}",
        "goal": request.title,
        "edit_plan": dict(edit_plan),
        "impact_analysis": dict(impact_analysis),
        "files": files,
        "operations": operations,
        "verification_set": verification,
        "rollback_status": dict(rollback_status),
        "execution_result": dict(execution_result),
        "result_summary": summary,
        "complete": complete,
        "successful": bool(execution_result.get("ok")) and bool(verification.get("ok")) and not bool(rollback_status.get("rollback_performed")),
    }


def _plan_is_valid(edit_plan: Mapping[str, Any], impact_analysis: Mapping[str, Any]) -> bool:
    return bool(edit_plan.get("valid") and impact_analysis.get("valid"))


def _planned_edit_from_plan(
    *,
    edit_plan: Any,
    payload: Mapping[str, Any],
    request: WorkPackageRequest,
) -> dict[str, Any]:
    target_path = _normalize_target_path(str(edit_plan.target_path))
    operation = str(edit_plan.operation)
    expected = _edit_verification_expectation(payload, str(edit_plan.content or ""))
    return {
        "operation": operation,
        "target_path": target_path,
        "content": str(edit_plan.content or ""),
        "expected": expected,
        "reason": request.instructions or request.title,
        "expected_effect": f"{operation} updates {target_path}",
        "verification_method": f"verify {target_path} contains {expected!r}",
    }


def _phase3_package_fields(
    *,
    request: WorkPackageRequest,
    edit_plan: Mapping[str, Any],
    impact_analysis: Mapping[str, Any],
    execution_result: Mapping[str, Any],
    verification_result: Mapping[str, Any],
    rollback_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rollback = _rollback_status(rollback_status)
    change_set = _build_change_set_bundle(
        request=request,
        edit_plan=edit_plan,
        impact_analysis=impact_analysis,
        execution_result=execution_result,
        verification_result=verification_result,
        rollback_status=rollback,
    )
    return {
        "plan": dict(edit_plan),
        "edit_plan": dict(edit_plan),
        "impact_analysis": dict(impact_analysis),
        "execution": _execution_paths(),
        "execution_result": dict(execution_result),
        "verification_result": dict(verification_result),
        "verification_set": dict(change_set["verification_set"]),
        "rollback_status": rollback,
        "rollback_performed": bool(rollback.get("rollback_performed")),
        "change_set": change_set,
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


def _controlled_edit_payloads(raw_payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    edits = raw_payload.get("edits")
    if isinstance(edits, list):
        return [edit for edit in edits if isinstance(edit, Mapping)]
    edit = raw_payload.get("edit")
    if isinstance(edit, list):
        return [item for item in edit if isinstance(item, Mapping)]
    if isinstance(edit, Mapping):
        return [edit]
    return [raw_payload]


def _rollback_transaction_changes(
    *,
    repo_root: Path,
    snapshots: Mapping[str, Mapping[str, Any]],
    changed_targets: list[str],
    instruction: str,
) -> dict[str, Any]:
    rollback_results: list[dict[str, Any]] = []
    ok = True

    for target_path in reversed(changed_targets):
        snapshot = snapshots.get(target_path)
        if not isinstance(snapshot, Mapping):
            continue
        if bool(snapshot.get("before_exists")):
            payload = {
                "file_path": target_path,
                "instruction": instruction,
                "mode": "replace_file",
                "new_content": str(snapshot.get("before_text") or ""),
            }
        else:
            payload = {
                "file_path": target_path,
                "instruction": instruction,
                "mode": "delete_file",
            }
        result = run_repo_edit(payload, repo_root=repo_root)
        result_ok = result.get("status") == "success" and bool(result.get("applied_to_workspace"))
        if not result_ok:
            ok = False
        rollback_results.append(
            {
                "target_path": target_path,
                "ok": bool(result_ok),
                "result": result,
            }
        )

    return {
        "ok": ok,
        "rollback_performed": bool(changed_targets),
        "rollback_results": rollback_results,
    }


def _multi_verification_result(per_target: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": "zero.work_package.multi_file_verification_result.v1",
        "ok": all(bool(item.get("verification", {}).get("ok")) for item in per_target),
        "targets": per_target,
    }


def _execute_controlled_multi_write(
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

    edit_payloads = _controlled_edit_payloads(raw_payload)
    if not edit_payloads:
        return _blocked_execute_response(
            repo_root=repo_root,
            request=request,
            reason="edits_required",
            approval_required=False,
            error="edits_required",
        )

    planned_edits: list[dict[str, Any]] = []
    for index, edit_payload in enumerate(edit_payloads, start=1):
        try:
            edit_plan = edit_plan_from_work_package_payload({"edit": edit_payload})
            target_path = _normalize_target_path(edit_plan.target_path)
            target = _repo_path(repo_root, target_path)
        except (WorkPackageExecutionRejected, ValueError) as exc:
            structured_plan = _build_structured_edit_plan(
                request=request,
                planned_edits=[
                    {
                        "operation": str(edit_payload.get("operation") or "unknown"),
                        "target_path": str(edit_payload.get("target_path") or edit_payload.get("path") or ""),
                        "content": str(edit_payload.get("content") or ""),
                        "expected": str(edit_payload.get("verify_contains") or edit_payload.get("expect_contains") or ""),
                        "reason": str(exc),
                        "expected_effect": "no edit executed",
                        "verification_method": "blocked before verification",
                    }
                ],
            )
            impact_analysis = _build_impact_analysis(request=request, edit_plan=structured_plan)
            return _blocked_execute_response(
                repo_root=repo_root,
                request=request,
                reason=str(exc),
                approval_required=False,
                error=str(exc),
                edit_plan=structured_plan,
                impact_analysis=impact_analysis,
            )

        proposed_item = _planned_edit_from_plan(edit_plan=edit_plan, payload=edit_payload, request=request)
        proposed_plan = _build_structured_edit_plan(request=request, planned_edits=[*planned_edits, proposed_item])
        proposed_impact = _build_impact_analysis(request=request, edit_plan=proposed_plan)
        if not _plan_is_valid(proposed_plan, proposed_impact):
            return _blocked_execute_response(
                repo_root=repo_root,
                request=request,
                reason="valid_edit_plan_required",
                approval_required=False,
                error="valid_edit_plan_required",
                edit_plan=proposed_plan,
                impact_analysis=proposed_impact,
            )

        allowed, policy_reason, guard = _controlled_write_policy(target_path)
        if not allowed:
            return _blocked_execute_response(
                repo_root=repo_root,
                request=request,
                reason=policy_reason,
                approval_required=False,
                error=policy_reason,
                edit_plan=proposed_plan,
                impact_analysis=proposed_impact,
            )
        planned_edits.append(
            {
                "index": index,
                "payload": edit_payload,
                "plan": edit_plan,
                "target_path": target_path,
                "target": target,
                "policy_reason": policy_reason,
                "guard": guard,
                "phase3_plan_item": proposed_item,
            }
        )

    target_files = [str(item["target_path"]) for item in planned_edits]
    structured_plan = _build_structured_edit_plan(
        request=request,
        planned_edits=[item["phase3_plan_item"] for item in planned_edits],
    )
    impact_analysis = _build_impact_analysis(request=request, edit_plan=structured_plan)
    if not _plan_is_valid(structured_plan, impact_analysis):
        return _blocked_execute_response(
            repo_root=repo_root,
            request=request,
            reason="valid_edit_plan_required",
            approval_required=False,
            error="valid_edit_plan_required",
            edit_plan=structured_plan,
            impact_analysis=impact_analysis,
        )
    snapshots: dict[str, dict[str, Any]] = {}
    for item in planned_edits:
        target_path = str(item["target_path"])
        target = item["target"]
        before_exists = target.exists() and target.is_file()
        snapshots[target_path] = {
            "before_exists": before_exists,
            "before_text": target.read_text(encoding="utf-8") if before_exists else "",
        }

    edit_results: list[dict[str, Any]] = []
    verification_targets: list[dict[str, Any]] = []
    changed_targets: list[str] = []
    failure_reason = ""

    for item in planned_edits:
        edit_plan = item["plan"]
        target_path = str(item["target_path"])
        try:
            write_result = _apply_controlled_repo_write(
                repo_root=repo_root,
                target_path=target_path,
                operation=edit_plan.operation,
                content=edit_plan.content,
                instruction=request.instructions or request.title,
            )
        except WorkPackageExecutionRejected as exc:
            write_result = {"ok": False, "error": str(exc)}

        changed = bool(write_result.get("before_text") != write_result.get("after_text"))
        if changed and target_path not in changed_targets:
            changed_targets.append(target_path)

        edit_record = {
            "index": item["index"],
            "operation": edit_plan.operation,
            "target_path": target_path,
            "ok": bool(write_result.get("ok")),
            "write_result": write_result,
        }
        edit_results.append(edit_record)

        if not bool(write_result.get("ok")):
            failure_reason = str(write_result.get("error") or f"edit_failed:{target_path}")
            break

        expected = _edit_verification_expectation(item["payload"], edit_plan.content)
        verification = _verify_target_content(target_path=item["target"], expected_text=expected)
        verification_targets.append(
            {
                "target_path": target_path,
                "verification": verification,
            }
        )
        edit_record["verification"] = verification

        if not bool(verification.get("ok")):
            failure_reason = "verification_failed"
            break

    verification_result = _multi_verification_result(verification_targets)
    if failure_reason and len(verification_targets) != len(planned_edits):
        verification_result["ok"] = False
        verification_result["reason"] = "transaction_incomplete"
    ok = not failure_reason and bool(verification_result.get("ok"))
    rollback = {"ok": True, "rollback_performed": False, "rollback_results": []}
    if not ok:
        rollback = _rollback_transaction_changes(
            repo_root=repo_root,
            snapshots=snapshots,
            changed_targets=changed_targets,
            instruction=f"rollback {request.package_id}",
        )

    final_changed_files = list(changed_targets) if ok else []
    evidence = {
        "schema": "zero.work_package.multi_file_controlled_write_evidence.v1",
        "package_id": request.package_id,
        "edit_plan": structured_plan,
        "impact_analysis": impact_analysis,
        "execution": _execution_paths(),
        "target_files": target_files,
        "edit_results": edit_results,
        "attempted_changed_files": list(changed_targets),
        "changed_files": final_changed_files,
        "rollback_performed": bool(rollback.get("rollback_performed")),
        "rollback": rollback,
        "verification_result": verification_result,
        "timestamp": time.time(),
        "approval": True,
        "guard": CONTROLLED_CORE_WRITE_GUARD_COMPAT,
    }

    report_lines = [
        f"# {request.title}",
        "",
        f"- Package ID: `{request.package_id}`",
        "- Mode: `execute`",
        "- Operation: `multi_file_controlled_write`",
        "- Approval: `true`",
        f"- Targets: `{', '.join(target_files)}`",
        f"- Changed files: `{', '.join(final_changed_files)}`",
        f"- Rollback performed: `{str(bool(rollback.get('rollback_performed'))).lower()}`",
        f"- Verification: `{str(bool(verification_result.get('ok'))).lower()}`",
        "",
        "## Evidence",
        "",
    ]
    for edit_record in edit_results:
        report_lines.append(
            f"- `{edit_record['target_path']}` `{edit_record['operation']}` ok=`{str(bool(edit_record['ok'])).lower()}`"
        )
    report_lines.append("")
    _write_report(repo_root, request.report_path, "\n".join(report_lines))

    response = _base_response(request)
    reason = "controlled_multi_file_write_completed" if ok else failure_reason or "multi_file_transaction_failed"
    execution_result = _execution_result_package(
        ok=bool(ok),
        status="success" if ok else "failed",
        reason=reason,
        target_files=target_files,
        changed_files=final_changed_files,
        edit_results=edit_results,
    )
    package_fields = _phase3_package_fields(
        request=request,
        edit_plan=structured_plan,
        impact_analysis=impact_analysis,
        execution_result=execution_result,
        verification_result=verification_result,
        rollback_status=rollback,
    )
    evidence["change_set"] = package_fields["change_set"]
    evidence["verification_set"] = package_fields["verification_set"]
    response.update(
        {
            "ok": bool(ok),
            "blocked": False,
            "approval_required": False,
            "reason": reason,
            "error": None if ok else reason,
            "target_files": target_files,
            "changed_files": final_changed_files,
            "edit_results": edit_results,
            "evidence": evidence,
            **package_fields,
        }
    )
    return response


def _blocked_execute_response(
    *,
    repo_root: Path,
    request: WorkPackageRequest,
    reason: str,
    approval_required: bool,
    error: str | None = None,
    edit_plan: Mapping[str, Any] | None = None,
    impact_analysis: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    public_reason = _public_block_reason(request, reason)
    public_error = public_reason if error is not None else None
    work_package_plan = build_work_package_plan(request)
    target_files = list(edit_plan.get("target_files") or request.scope_paths) if isinstance(edit_plan, Mapping) else list(request.scope_paths)
    if not isinstance(edit_plan, Mapping):
        edit_plan = _build_structured_edit_plan(
            request=request,
            planned_edits=[
                {
                    "operation": "blocked",
                    "target_path": path,
                    "content": "",
                    "expected": "",
                    "reason": public_reason,
                    "expected_effect": "no edit executed",
                    "verification_method": "blocked before verification",
                }
                for path in target_files
            ],
        )
    if not isinstance(impact_analysis, Mapping):
        impact_analysis = _build_impact_analysis(request=request, edit_plan=edit_plan)
    verification_result = {
        "schema": "zero.work_package.verification_result.v1",
        "ok": False,
        "reason": "blocked_before_verification",
    }
    execution_result = _execution_result_package(
        ok=False,
        status="blocked",
        reason=public_reason,
        target_files=target_files,
        changed_files=[],
    )
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
            "target_files": target_files,
            "changed_files": [],
            "work_package_plan": work_package_plan.to_dict(),
            **_phase3_package_fields(
                request=request,
                edit_plan=edit_plan,
                impact_analysis=impact_analysis,
                execution_result=execution_result,
                verification_result=verification_result,
                rollback_status=_rollback_status(),
            ),
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

    if isinstance(raw_payload.get("edits"), list):
        return _execute_controlled_multi_write(
            repo_root=repo_root,
            request=request,
            raw_payload=raw_payload,
        )

    try:
        edit_plan = edit_plan_from_work_package_payload(raw_payload)
    except WorkPackageExecutionRejected as exc:
        structured_plan = _build_structured_edit_plan(
            request=request,
            planned_edits=[
                {
                    "operation": str(edit_payload.get("operation") or "unknown") if isinstance(edit_payload, Mapping) else "unknown",
                    "target_path": str(edit_payload.get("target_path") or edit_payload.get("path") or "") if isinstance(edit_payload, Mapping) else "",
                    "content": str(edit_payload.get("content") or "") if isinstance(edit_payload, Mapping) else "",
                    "expected": _verification_expectation(raw_payload),
                    "reason": str(exc),
                    "expected_effect": "no edit executed",
                    "verification_method": "blocked before verification",
                }
            ],
        )
        impact_analysis = _build_impact_analysis(request=request, edit_plan=structured_plan)
        return _blocked_execute_response(
            repo_root=repo_root,
            request=request,
            reason=str(exc),
            approval_required=False,
            error=str(exc),
            edit_plan=structured_plan,
            impact_analysis=impact_analysis,
        )

    target_path = _normalize_target_path(edit_plan.target_path)
    structured_plan = _build_structured_edit_plan(
        request=request,
        planned_edits=[_planned_edit_from_plan(edit_plan=edit_plan, payload=raw_payload, request=request)],
    )
    impact_analysis = _build_impact_analysis(request=request, edit_plan=structured_plan)
    if not _plan_is_valid(structured_plan, impact_analysis):
        return _blocked_execute_response(
            repo_root=repo_root,
            request=request,
            reason="valid_edit_plan_required",
            approval_required=False,
            error="valid_edit_plan_required",
            edit_plan=structured_plan,
            impact_analysis=impact_analysis,
        )

    try:
        target = _repo_path(repo_root, target_path)
    except ValueError as exc:
        return _blocked_execute_response(
            repo_root=repo_root,
            request=request,
            reason=str(exc),
            approval_required=False,
            error=str(exc),
            edit_plan=structured_plan,
            impact_analysis=impact_analysis,
        )

    allowed, policy_reason, guard = _controlled_write_policy(target_path)
    if not allowed:
        return _blocked_execute_response(
            repo_root=repo_root,
            request=request,
            reason=policy_reason,
            approval_required=False,
            error=policy_reason,
            edit_plan=structured_plan,
            impact_analysis=impact_analysis,
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
            edit_plan=structured_plan,
            impact_analysis=impact_analysis,
        )

    if not bool(write_result.get("ok")):
        reason = str(write_result.get("error") or "controlled_repo_write_failed")
        return _blocked_execute_response(
            repo_root=repo_root,
            request=request,
            reason=reason,
            approval_required=False,
            error=reason,
            edit_plan=structured_plan,
            impact_analysis=impact_analysis,
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
        "edit_plan": structured_plan,
        "impact_analysis": impact_analysis,
        "execution": _execution_paths(),
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
    reason = _public_success_reason(guard=guard) if bool(verification_result["ok"]) else "verification_failed"
    changed_files = [target_path] if changed else []
    execution_result = _execution_result_package(
        ok=bool(verification_result["ok"]),
        status="success" if bool(verification_result["ok"]) else "failed",
        reason=reason,
        target_files=[target_path],
        changed_files=changed_files,
        edit_results=[
            {
                "operation": edit_plan.operation,
                "target_path": target_path,
                "ok": bool(write_result.get("ok")),
                "write_result": write_result,
            }
        ],
    )
    package_fields = _phase3_package_fields(
        request=request,
        edit_plan=structured_plan,
        impact_analysis=impact_analysis,
        execution_result=execution_result,
        verification_result=verification_result,
        rollback_status=_rollback_status(),
    )
    evidence["change_set"] = package_fields["change_set"]
    evidence["verification_set"] = package_fields["verification_set"]
    response.update(
        {
            "ok": bool(verification_result["ok"]),
            "blocked": False if bool(verification_result["ok"]) else True,
            "approval_required": False,
            "reason": reason,
            "error": None if bool(verification_result["ok"]) else "verification_failed",
            "target_file": target_path,
            "target_path": target_path,
            "evidence": evidence,
            "changed_files": changed_files,
            "legacy_edit_plan": edit_plan.to_dict(),
            **package_fields,
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
