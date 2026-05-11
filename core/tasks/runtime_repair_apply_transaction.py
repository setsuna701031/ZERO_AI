from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Dict, List, Mapping, Optional

from core.tasks.runtime_state_hygiene import freeze_runtime_export


def build_runtime_repair_apply_transaction(
    patch_preview: Any,
    *,
    operator: str = "",
    dry_run: bool = True,
    transaction_id: str = "",
) -> Dict[str, Any]:
    """Build a read-only staged apply transaction from a patch preview.

    This layer does not write files, apply patches, execute commands, schedule
    tasks, or mutate the supplied preview. It only turns an approved preview into
    a transaction record that a later executor gate can review.
    """
    safe_preview = patch_preview if isinstance(patch_preview, Mapping) else {}

    task_id = _first_nonempty(safe_preview.get("task_id"))
    proposal_id = _first_nonempty(safe_preview.get("proposal_id"))
    target_path = _first_nonempty(safe_preview.get("target_path"))
    diff_text = _first_nonempty(safe_preview.get("diff"))
    preview_allowed = bool(safe_preview.get("preview_allowed", False))
    apply_allowed = bool(safe_preview.get("apply_allowed", False))

    blocked_reasons: List[str] = []
    if not preview_allowed:
        blocked_reasons.append("patch_preview_not_allowed")
    if not target_path:
        blocked_reasons.append("target_path_missing")
    if not diff_text:
        blocked_reasons.append("diff_missing")
    if apply_allowed:
        blocked_reasons.append("unexpected_apply_allowed_in_preview_layer")

    transaction_status = "staged" if not blocked_reasons else "blocked"
    resolved_transaction_id = _first_nonempty(
        transaction_id,
        _build_transaction_id(
            task_id=task_id,
            proposal_id=proposal_id,
            target_path=target_path,
            diff_text=diff_text,
        ),
    )

    staged_patch = {
        "target_path": target_path,
        "diff_hash": _sha256(diff_text),
        "diff_line_count": int(safe_preview.get("diff_line_count") or 0),
        "added_lines": int(safe_preview.get("added_lines") or 0),
        "removed_lines": int(safe_preview.get("removed_lines") or 0),
        "apply_allowed": False,
        "write_allowed": False,
        "execution_allowed": False,
    }

    rollback_plan = {
        "required": transaction_status == "staged",
        "snapshot_required": transaction_status == "staged",
        "snapshot_status": "not_created",
        "rollback_available": False,
        "restore_allowed": False,
        "reason": "rollback snapshot must be created by a later read/write gate before apply",
    }

    return {
        "ok": True,
        "transaction_id": resolved_transaction_id,
        "transaction_status": transaction_status,
        "task_id": task_id,
        "proposal_id": proposal_id,
        "operator": str(operator or "").strip(),
        "dry_run": bool(dry_run),
        "staged": transaction_status == "staged",
        "blocked_reasons": _unique(blocked_reasons),
        "staged_patch": staged_patch,
        "staged_patches": [staged_patch] if target_path else [],
        "rollback_plan": rollback_plan,
        "mutation_allowed": False,
        "apply_allowed": False,
        "write_allowed": False,
        "execution_allowed": False,
        "schedule_allowed": False,
        "allowed_next_action": "create_rollback_snapshot" if transaction_status == "staged" else "inspect_transaction_block",
        "human_summary": _build_summary(
            status=transaction_status,
            transaction_id=resolved_transaction_id,
            target_path=target_path,
            blocked_reasons=blocked_reasons,
        ),
        "created_at_unix": time.time(),
        "raw_patch_preview": freeze_runtime_export(patch_preview),
    }


def build_runtime_repair_apply_transactions(
    patch_previews: Any,
    *,
    operator: str = "",
    dry_run: bool = True,
) -> List[Dict[str, Any]]:
    if isinstance(patch_previews, list):
        return [
            build_runtime_repair_apply_transaction(
                item,
                operator=operator,
                dry_run=dry_run,
            )
            for item in patch_previews
        ]
    return [
        build_runtime_repair_apply_transaction(
            patch_previews,
            operator=operator,
            dry_run=dry_run,
        )
    ]


def summarize_runtime_repair_apply_transaction(transaction: Any) -> Dict[str, Any]:
    safe = transaction if isinstance(transaction, Mapping) else {}

    staged_patches = safe.get("staged_patches")
    if not isinstance(staged_patches, list):
        staged_patches = []

    return {
        "transaction_id": _first_nonempty(safe.get("transaction_id")),
        "transaction_status": _first_nonempty(safe.get("transaction_status"), "unknown"),
        "task_id": _first_nonempty(safe.get("task_id")),
        "proposal_id": _first_nonempty(safe.get("proposal_id")),
        "staged_patch_count": len(staged_patches),
        "mutation_allowed": bool(safe.get("mutation_allowed", False)),
        "apply_allowed": bool(safe.get("apply_allowed", False)),
        "write_allowed": bool(safe.get("write_allowed", False)),
        "execution_allowed": bool(safe.get("execution_allowed", False)),
        "schedule_allowed": bool(safe.get("schedule_allowed", False)),
        "allowed_next_action": _first_nonempty(safe.get("allowed_next_action")),
        "blocked_reasons": _string_list(safe.get("blocked_reasons"), fallback=[]),
    }


def preflight_runtime_repair_apply_transaction(
    transaction: Any,
    *,
    workspace_root: Any = "",
    allowed_roots: Any = None,
) -> Dict[str, Any]:
    """Check whether a staged repair transaction is ready for a later executor.

    This is intentionally read-only. It does not write target files, apply
    patches, execute commands, mutate scheduler state, or modify the supplied
    transaction record.
    """
    safe = transaction if isinstance(transaction, Mapping) else {}
    blockers: List[str] = []
    warnings: List[str] = []

    transaction_id = _first_nonempty(safe.get("transaction_id"))
    required_fields = ["transaction_id", "task_id", "operations", "created_at", "status"]
    for field in required_fields:
        if field == "operations":
            if not isinstance(safe.get(field), list) or not safe.get(field):
                blockers.append("missing_required_field:operations")
            continue
        if not _first_nonempty(safe.get(field)):
            blockers.append(f"missing_required_field:{field}")

    status = _first_nonempty(safe.get("status"))
    if status == "aborted":
        blockers.append("transaction_aborted")
    elif status and status != "staged":
        warnings.append(f"unexpected_transaction_status:{status}")

    operation_items = safe.get("operations")
    if not isinstance(operation_items, list):
        operation_items = []

    workspace_boundary = _resolve_boundary_root(workspace_root)
    allowed_boundaries = _resolve_allowed_boundaries(
        workspace_boundary=workspace_boundary,
        allowed_roots=allowed_roots if allowed_roots is not None else safe.get("allowed_roots"),
    )

    for index, operation in enumerate(operation_items):
        if not isinstance(operation, Mapping):
            blockers.append(f"invalid_operation:{index}:not_mapping")
            continue

        op_type = _first_nonempty(operation.get("op_type"))
        target_path = _first_nonempty(operation.get("target_path"))
        if not op_type:
            blockers.append(f"invalid_operation:{index}:op_type_missing")
        if not target_path:
            blockers.append(f"invalid_operation:{index}:target_path_missing")
        elif not _target_path_is_allowed(
            target_path,
            workspace_boundary=workspace_boundary,
            allowed_boundaries=allowed_boundaries,
        ):
            blockers.append(f"invalid_operation:{index}:unsafe_target_path")

        if not _operation_has_payload(operation):
            blockers.append(f"invalid_operation:{index}:payload_missing")

    return {
        "ok": not blockers,
        "blockers": _unique(blockers),
        "warnings": _unique(warnings),
        "transaction_id": transaction_id,
        "checked_at": _utc_timestamp(),
    }


def abort_runtime_repair_apply_transaction(
    transaction: Any,
    *,
    reason: Any = "",
    preflight_result: Any = None,
) -> Dict[str, Any]:
    """Return an aborted copy of a transaction record without deleting history."""
    safe = dict(transaction) if isinstance(transaction, Mapping) else {}
    abort_reason = _first_nonempty(reason)
    preflight = preflight_result if isinstance(preflight_result, Mapping) else {}
    blockers = _string_list(preflight.get("blockers"), fallback=[])
    if not abort_reason and blockers:
        abort_reason = "; ".join(blockers)
    if not abort_reason:
        abort_reason = "transaction_aborted"

    safe["status"] = "aborted"
    safe["transaction_status"] = "aborted"
    safe["staged"] = False
    safe["abort_reason"] = abort_reason
    safe["reason"] = abort_reason
    safe["aborted_at"] = _utc_timestamp()
    safe["allowed_next_action"] = "inspect_transaction_abort"
    safe["apply_allowed"] = False
    safe["write_allowed"] = False
    safe["execution_allowed"] = False
    safe["schedule_allowed"] = False
    return safe


def build_runtime_repair_apply_plan(transaction: Any) -> Dict[str, Any]:
    """Build a dry-run preview of files and operations a transaction would affect."""
    safe = transaction if isinstance(transaction, Mapping) else {}
    operation_items = safe.get("operations")
    if not isinstance(operation_items, list):
        operation_items = []

    operation_preview: List[Dict[str, Any]] = []
    affected_files: List[str] = []
    for operation in operation_items:
        if not isinstance(operation, Mapping):
            continue

        op_type = _first_nonempty(operation.get("op_type"))
        target_path = _first_nonempty(operation.get("target_path"))
        normalized_path = _normalize_display_path(target_path)
        if normalized_path:
            affected_files.append(normalized_path)

        operation_preview.append(
            {
                "op_type": op_type,
                "target_path": normalized_path,
                "mode": _first_nonempty(operation.get("mode"), "dry_run"),
                "summary": _operation_plan_summary(op_type),
            }
        )

    preflight = preflight_runtime_repair_apply_transaction(transaction)
    warnings = _unique(
        _string_list(preflight.get("blockers"), fallback=[])
        + _string_list(preflight.get("warnings"), fallback=[])
    )

    return {
        "transaction_id": _first_nonempty(safe.get("transaction_id")),
        "operation_count": len(operation_items),
        "affected_files": sorted(_unique(affected_files)),
        "operation_preview": operation_preview,
        "warnings": warnings,
        "ready": bool(preflight.get("ok", False)),
        "generated_at": _utc_timestamp(),
    }


def apply_runtime_repair_transaction_sandbox(transaction: Any) -> Dict[str, Any]:
    """Apply a transaction to an isolated temporary sandbox only.

    The real workspace and target files are never touched, commands are never
    executed, and failed simulations remove their temporary sandbox.
    """
    safe = transaction if isinstance(transaction, Mapping) else {}
    transaction_id = _first_nonempty(safe.get("transaction_id"))
    started_at = _utc_timestamp()
    sandbox_root = Path(tempfile.mkdtemp(prefix="runtime_repair_sandbox_")).resolve()
    snapshot_root = Path(tempfile.mkdtemp(prefix="runtime_repair_snapshot_")).resolve()
    applied_operations: List[Dict[str, Any]] = []
    failed_operation: Optional[Dict[str, Any]] = None
    rollback_performed = False
    before_snapshot: Dict[str, Dict[str, Any]] = {}
    after_snapshot: Dict[str, Dict[str, Any]] = {}

    try:
        _seed_sandbox_files(safe.get("sandbox_files"), sandbox_root=sandbox_root)
        before_snapshot = _snapshot_sandbox(sandbox_root)
        _copy_directory_state(sandbox_root, snapshot_root)
        preflight = preflight_runtime_repair_apply_transaction(
            transaction,
            workspace_root=sandbox_root,
        )
        if not preflight.get("ok", False):
            failed_operation = {
                "index": None,
                "op_type": "preflight",
                "target_path": "",
                "reason": "; ".join(_string_list(preflight.get("blockers"), fallback=[])),
            }
            raise RuntimeError(failed_operation["reason"])

        operation_items = safe.get("operations")
        if not isinstance(operation_items, list):
            operation_items = []

        for index, operation in enumerate(operation_items):
            if not isinstance(operation, Mapping):
                failed_operation = {
                    "index": index,
                    "op_type": "",
                    "target_path": "",
                    "reason": "operation_not_mapping",
                }
                raise RuntimeError("operation_not_mapping")

            try:
                applied = _apply_sandbox_operation(
                    operation,
                    index=index,
                    sandbox_root=sandbox_root,
                )
            except Exception as exc:
                failed_operation = {
                    "index": index,
                    "op_type": _first_nonempty(operation.get("op_type")),
                    "target_path": _normalize_display_path(operation.get("target_path")),
                    "reason": str(exc),
                }
                raise
            applied_operations.append(applied)

        after_snapshot = _snapshot_sandbox(sandbox_root)
        return {
            "transaction_id": transaction_id,
            "applied_operations": applied_operations,
            "failed_operation": None,
            "sandbox_path": str(sandbox_root),
            "before_snapshot": before_snapshot,
            "after_snapshot": after_snapshot,
            "success": True,
            "rollback_performed": False,
            "started_at": started_at,
            "completed_at": _utc_timestamp(),
        }
    except Exception:
        _restore_directory_state(snapshot_root, sandbox_root)
        after_snapshot = _snapshot_sandbox(sandbox_root)
        rollback_performed = True
        shutil.rmtree(sandbox_root, ignore_errors=True)
        return {
            "transaction_id": transaction_id,
            "applied_operations": applied_operations,
            "failed_operation": failed_operation,
            "sandbox_path": str(sandbox_root),
            "before_snapshot": before_snapshot,
            "after_snapshot": after_snapshot,
            "success": False,
            "rollback_performed": rollback_performed,
            "started_at": started_at,
            "completed_at": _utc_timestamp(),
        }
    finally:
        shutil.rmtree(snapshot_root, ignore_errors=True)


def build_runtime_repair_commit_preview(result: Any) -> Dict[str, Any]:
    """Build a commit-style preview from sandbox-only apply snapshots."""
    safe = result if isinstance(result, Mapping) else {}
    before_snapshot = safe.get("before_snapshot")
    after_snapshot = safe.get("after_snapshot")
    if not isinstance(before_snapshot, Mapping):
        before_snapshot = {}
    if not isinstance(after_snapshot, Mapping):
        after_snapshot = {}

    applied_operations = safe.get("applied_operations")
    if not isinstance(applied_operations, list):
        applied_operations = []

    failed_operation = safe.get("failed_operation")
    rollback_applied = bool(safe.get("rollback_performed", False))
    operation_by_path = _operation_type_by_path(applied_operations)
    changed_files = _changed_files_from_snapshots(
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        operation_by_path=operation_by_path,
    )
    operation_results = _commit_operation_results(
        applied_operations=applied_operations,
        failed_operation=failed_operation if isinstance(failed_operation, Mapping) else None,
        rollback_applied=rollback_applied,
    )

    return {
        "transaction_id": _first_nonempty(safe.get("transaction_id")),
        "changed_files": changed_files,
        "diff_summary": {
            "total_files_changed": len(changed_files),
            "writes": sum(1 for item in changed_files if item["operation_type"] == "write_file"),
            "patches": sum(1 for item in changed_files if item["operation_type"] == "patch_file"),
            "deletes": sum(1 for item in changed_files if item["operation_type"] == "delete_file"),
            "failures": 0 if bool(safe.get("success", False)) else 1,
            "rollback": rollback_applied,
        },
        "operation_results": operation_results,
        "preview_ready": bool(safe.get("success", False)) and not rollback_applied,
        "generated_at": _utc_timestamp(),
    }


def build_runtime_repair_review_request(preview: Any) -> Dict[str, Any]:
    """Build a pending human review request from a commit preview."""
    safe = preview if isinstance(preview, Mapping) else {}
    changed_files = safe.get("changed_files")
    if not isinstance(changed_files, list):
        changed_files = []
    diff_summary = safe.get("diff_summary")
    if not isinstance(diff_summary, Mapping):
        diff_summary = {}

    risk_level = _review_risk_level(changed_files=changed_files, diff_summary=diff_summary)
    reasons = _review_reasons(
        changed_files=changed_files,
        diff_summary=diff_summary,
        preview_ready=bool(safe.get("preview_ready", False)),
        risk_level=risk_level,
    )

    return {
        "transaction_id": _first_nonempty(safe.get("transaction_id")),
        "review_required": True,
        "review_status": "pending",
        "changed_files": changed_files,
        "diff_summary": dict(diff_summary),
        "risk_level": risk_level,
        "reasons": reasons,
        "commit_allowed": False,
        "created_at": _utc_timestamp(),
    }


def approve_runtime_repair_review(
    request: Any,
    reviewer: Any,
    note: Any = "",
) -> Dict[str, Any]:
    safe = request if isinstance(request, Mapping) else {}
    risk_level = _first_nonempty(safe.get("risk_level"))
    blocked = risk_level == "blocked" or _diff_has_failure(safe.get("diff_summary"))
    approved = not blocked

    return {
        "transaction_id": _first_nonempty(safe.get("transaction_id")),
        "review_id": _first_nonempty(safe.get("review_id"), _build_review_id(safe)),
        "review_status": "approved" if approved else "blocked",
        "approved_by": _first_nonempty(reviewer),
        "approved_at": _utc_timestamp() if approved else "",
        "note": _first_nonempty(note),
        "changed_files": freeze_runtime_export(safe.get("changed_files", [])),
        "diff_summary": freeze_runtime_export(safe.get("diff_summary", {})),
        "risk_level": _first_nonempty(safe.get("risk_level")),
        "commit_allowed": approved,
    }


def reject_runtime_repair_review(
    request: Any,
    reviewer: Any,
    reason: Any = "",
) -> Dict[str, Any]:
    safe = request if isinstance(request, Mapping) else {}
    return {
        "transaction_id": _first_nonempty(safe.get("transaction_id")),
        "review_id": _first_nonempty(safe.get("review_id"), _build_review_id(safe)),
        "review_status": "rejected",
        "rejected_by": _first_nonempty(reviewer),
        "rejected_at": _utc_timestamp(),
        "reason": _first_nonempty(reason),
        "changed_files": freeze_runtime_export(safe.get("changed_files", [])),
        "diff_summary": freeze_runtime_export(safe.get("diff_summary", {})),
        "risk_level": _first_nonempty(safe.get("risk_level")),
        "commit_allowed": False,
    }


def issue_runtime_repair_commit_token(
    review_result: Any,
    *,
    ttl_seconds: int = 600,
) -> Dict[str, Any]:
    """Issue an in-memory commit authorization token from an approved review."""
    safe = review_result if isinstance(review_result, Mapping) else {}
    transaction_id = _first_nonempty(safe.get("transaction_id"))
    review_status = _first_nonempty(safe.get("review_status"))
    commit_allowed = bool(safe.get("commit_allowed", False))
    approved_by = _first_nonempty(safe.get("approved_by"))
    issued_unix = time.time()
    ttl = max(0, int(ttl_seconds or 0))
    token_status = "active" if review_status == "approved" and commit_allowed else "revoked"

    return {
        "transaction_id": transaction_id,
        "token_id": _build_commit_token_id(
            transaction_id=transaction_id,
            approved_by=approved_by,
            issued_unix=issued_unix,
        ),
        "issued_at": _unix_to_utc_timestamp(issued_unix),
        "expires_at": _unix_to_utc_timestamp(issued_unix + ttl),
        "issued_at_unix": issued_unix,
        "expires_at_unix": issued_unix + ttl,
        "approved_by": approved_by,
        "commit_authorized": token_status == "active",
        "token_status": token_status,
        "reason": "" if token_status == "active" else "review_not_approved",
    }


def validate_runtime_repair_commit_token(token: Any) -> Dict[str, Any]:
    safe = token if isinstance(token, Mapping) else {}
    token_status = _first_nonempty(safe.get("token_status"))
    expired = _commit_token_expired(safe)
    revoked = token_status == "revoked"
    consumed = token_status == "consumed"
    active = token_status == "active"

    reason = "valid"
    if not active:
        reason = f"token_{token_status or 'invalid'}"
    if expired:
        reason = "token_expired"
    if revoked:
        reason = "token_revoked"
    if consumed:
        reason = "token_consumed"

    valid = active and not expired and not revoked and not consumed and bool(safe.get("commit_authorized", False))
    return {
        "valid": valid,
        "reason": reason,
        "expired": expired,
        "revoked": revoked,
        "consumable": valid,
    }


def consume_runtime_repair_commit_token(token: Any) -> Dict[str, Any]:
    safe = dict(token) if isinstance(token, Mapping) else {}
    validation = validate_runtime_repair_commit_token(safe)
    if not validation["valid"]:
        safe["commit_authorized"] = False
        return safe

    safe["token_status"] = "consumed"
    safe["commit_authorized"] = False
    safe["consumed_at"] = _utc_timestamp()
    return safe


def revoke_runtime_repair_commit_token(token: Any, reason: Any = "") -> Dict[str, Any]:
    safe = dict(token) if isinstance(token, Mapping) else {}
    safe["token_status"] = "revoked"
    safe["commit_authorized"] = False
    safe["revoked_at"] = _utc_timestamp()
    safe["reason"] = _first_nonempty(reason, "token_revoked")
    return safe


def create_runtime_repair_commit_intent(
    transaction: Any,
    review_result: Any,
    token: Any,
) -> Dict[str, Any]:
    """Create an immutable commit intent record without committing anything."""
    safe_transaction = transaction if isinstance(transaction, Mapping) else {}
    safe_review = review_result if isinstance(review_result, Mapping) else {}
    safe_token = token if isinstance(token, Mapping) else {}

    token_validation = validate_runtime_repair_commit_token(safe_token)
    review_status = _first_nonempty(safe_review.get("review_status"))
    transaction_id = _first_nonempty(
        safe_transaction.get("transaction_id"),
        safe_review.get("transaction_id"),
        safe_token.get("transaction_id"),
    )
    changed_files = freeze_runtime_export(safe_review.get("changed_files", []))
    diff_summary = freeze_runtime_export(safe_review.get("diff_summary", {}))
    review_id = _first_nonempty(
        safe_review.get("review_id"),
        _build_review_id(safe_review),
    )

    issues: List[str] = []
    if review_status != "approved" or not bool(safe_review.get("commit_allowed", False)):
        issues.append("review_not_approved")
    if not token_validation["valid"]:
        issues.append(f"token_invalid:{token_validation['reason']}")

    immutable_fields = {
        "transaction_id": transaction_id,
        "token_id": _first_nonempty(safe_token.get("token_id")),
        "review_id": review_id,
        "changed_files": changed_files,
        "diff_summary": diff_summary,
    }

    intent_status = "pending_commit" if not issues else "invalid"
    intent_id = _build_commit_intent_id(immutable_fields=immutable_fields)
    return {
        "intent_id": intent_id,
        "transaction_id": transaction_id,
        "review_id": review_id,
        "token_id": immutable_fields["token_id"],
        "created_at": _utc_timestamp(),
        "created_by": _first_nonempty(safe_review.get("approved_by")),
        "changed_files": changed_files,
        "diff_summary": diff_summary,
        "intent_status": intent_status,
        "immutable_fields": immutable_fields,
        "immutable_digest": _immutable_digest(immutable_fields),
        "review_status": review_status,
        "commit_allowed": bool(safe_review.get("commit_allowed", False)),
        "token_snapshot": freeze_runtime_export(safe_token),
        "issues": _unique(issues),
    }


def validate_runtime_repair_commit_intent(intent: Any) -> Dict[str, Any]:
    safe = intent if isinstance(intent, Mapping) else {}
    issues: List[str] = []

    immutable_ok = _intent_immutable_fields_ok(safe)
    if not immutable_ok:
        issues.append("immutable_fields_modified")

    token_validation = validate_runtime_repair_commit_token(safe.get("token_snapshot"))
    if not token_validation["valid"]:
        issues.append(f"token_invalid:{token_validation['reason']}")

    if _first_nonempty(safe.get("review_status")) != "approved" or not bool(safe.get("commit_allowed", False)):
        issues.append("review_not_approved")
    if _first_nonempty(safe.get("intent_status")) != "pending_commit":
        issues.append(f"intent_status:{_first_nonempty(safe.get('intent_status'), 'unknown')}")

    unique_issues = _unique(issues)
    return {
        "valid": not unique_issues,
        "immutable_ok": immutable_ok,
        "commit_ready": not unique_issues,
        "issues": unique_issues,
    }


def open_runtime_repair_commit_session(
    intent: Any,
    *,
    ttl_seconds: int = 300,
) -> Dict[str, Any]:
    safe = intent if isinstance(intent, Mapping) else {}
    intent_validation = validate_runtime_repair_commit_intent(safe)
    started_unix = time.time()
    ttl = max(0, int(ttl_seconds or 0))
    lease_status = "active" if intent_validation["commit_ready"] else "revoked"

    return {
        "session_id": _build_commit_session_id(
            intent_id=_first_nonempty(safe.get("intent_id")),
            token_id=_first_nonempty(safe.get("token_id")),
            lease_started_unix=started_unix,
        ),
        "transaction_id": _first_nonempty(safe.get("transaction_id")),
        "intent_id": _first_nonempty(safe.get("intent_id")),
        "token_id": _first_nonempty(safe.get("token_id")),
        "lease_started_at": _unix_to_utc_timestamp(started_unix),
        "lease_expires_at": _unix_to_utc_timestamp(started_unix + ttl),
        "lease_started_at_unix": started_unix,
        "lease_expires_at_unix": started_unix + ttl,
        "lease_status": lease_status,
        "execution_allowed": lease_status == "active",
        "intent_snapshot": freeze_runtime_export(safe),
        "issues": [] if lease_status == "active" else intent_validation["issues"],
    }


def validate_runtime_repair_commit_session(session: Any) -> Dict[str, Any]:
    safe = session if isinstance(session, Mapping) else {}
    issues: List[str] = []
    lease_status = _first_nonempty(safe.get("lease_status"))
    lease_expired = _commit_session_expired(safe)
    lease_active = lease_status == "active" and not lease_expired

    intent_validation = validate_runtime_repair_commit_intent(safe.get("intent_snapshot"))
    if not intent_validation["commit_ready"]:
        issues.extend(f"intent:{issue}" for issue in intent_validation["issues"])
    if lease_status != "active":
        issues.append(f"lease_status:{lease_status or 'unknown'}")
    if lease_expired:
        issues.append("lease_expired")

    unique_issues = _unique(issues)
    execution_allowed = lease_active and intent_validation["commit_ready"] and bool(safe.get("execution_allowed", False))
    return {
        "valid": execution_allowed and not unique_issues,
        "lease_active": lease_active,
        "execution_allowed": execution_allowed and not unique_issues,
        "issues": unique_issues,
    }


def consume_runtime_repair_commit_session(session: Any) -> Dict[str, Any]:
    safe = dict(session) if isinstance(session, Mapping) else {}
    validation = validate_runtime_repair_commit_session(safe)
    if not validation["valid"]:
        safe["execution_allowed"] = False
        return safe

    safe["lease_status"] = "consumed"
    safe["execution_allowed"] = False
    safe["consumed_at"] = _utc_timestamp()
    return safe


def revoke_runtime_repair_commit_session(session: Any, reason: Any = "") -> Dict[str, Any]:
    safe = dict(session) if isinstance(session, Mapping) else {}
    safe["lease_status"] = "revoked"
    safe["execution_allowed"] = False
    safe["revoked_at"] = _utc_timestamp()
    safe["reason"] = _first_nonempty(reason, "lease_revoked")
    return safe


def final_precheck_runtime_repair_commit(
    transaction: Any,
    preview: Any,
    review: Any,
    token: Any,
    intent: Any,
    session: Any,
) -> Dict[str, Any]:
    safe_transaction = transaction if isinstance(transaction, Mapping) else {}
    safe_preview = preview if isinstance(preview, Mapping) else {}
    safe_review = review if isinstance(review, Mapping) else {}
    safe_token = token if isinstance(token, Mapping) else {}
    safe_intent = intent if isinstance(intent, Mapping) else {}
    safe_session = session if isinstance(session, Mapping) else {}

    transaction_id = _first_nonempty(
        safe_transaction.get("transaction_id"),
        safe_preview.get("transaction_id"),
        safe_review.get("transaction_id"),
        safe_token.get("transaction_id"),
        safe_intent.get("transaction_id"),
        safe_session.get("transaction_id"),
    )
    issues: List[str] = []
    for label, record in (
        ("preview", safe_preview),
        ("review", safe_review),
        ("token", safe_token),
        ("intent", safe_intent),
        ("session", safe_session),
    ):
        if _first_nonempty(record.get("transaction_id")) != transaction_id:
            issues.append(f"transaction_id_mismatch:{label}")

    if _first_nonempty(safe_review.get("review_status")) != "approved":
        issues.append("review_not_approved")
    if not bool(safe_review.get("commit_allowed", False)):
        issues.append("commit_not_allowed_by_review")

    token_validation = validate_runtime_repair_commit_token(safe_token)
    if not token_validation["valid"]:
        issues.append(f"token_invalid:{token_validation['reason']}")

    intent_validation = validate_runtime_repair_commit_intent(safe_intent)
    if not intent_validation["valid"]:
        issues.extend(f"intent:{issue}" for issue in intent_validation["issues"])

    session_validation = validate_runtime_repair_commit_session(safe_session)
    if not session_validation["valid"]:
        issues.extend(f"session:{issue}" for issue in session_validation["issues"])
    if not bool(safe_session.get("execution_allowed", False)):
        issues.append("session_execution_not_allowed")

    preview_changed_files = freeze_runtime_export(safe_preview.get("changed_files", []))
    intent_changed_files = freeze_runtime_export(safe_intent.get("changed_files", []))
    preview_diff_summary = freeze_runtime_export(safe_preview.get("diff_summary", {}))
    intent_diff_summary = freeze_runtime_export(safe_intent.get("diff_summary", {}))
    if preview_changed_files != intent_changed_files:
        issues.append("changed_files_mismatch")
    if preview_diff_summary != intent_diff_summary:
        issues.append("diff_summary_mismatch")
    if not _intent_immutable_fields_ok(safe_intent):
        issues.append("immutable_digest_modified")

    consistency_digest = _commit_consistency_digest(
        transaction_id=transaction_id,
        changed_files=preview_changed_files,
        diff_summary=preview_diff_summary,
        token_id=_first_nonempty(safe_token.get("token_id")),
        intent_id=_first_nonempty(safe_intent.get("intent_id")),
        session_id=_first_nonempty(safe_session.get("session_id")),
    )
    unique_issues = _unique(issues)
    return {
        "transaction_id": transaction_id,
        "precheck_ok": not unique_issues,
        "commit_ready": not unique_issues,
        "issues": unique_issues,
        "checked_at": _utc_timestamp(),
        "consistency_digest": consistency_digest,
    }


def commit_runtime_repair_transaction_temp_workspace(
    transaction: Any,
    preview: Any,
    precheck: Any,
    session: Any,
) -> Dict[str, Any]:
    """Commit a repair transaction into an isolated temporary workspace only."""
    safe_transaction = transaction if isinstance(transaction, Mapping) else {}
    safe_precheck = precheck if isinstance(precheck, Mapping) else {}
    safe_session = session if isinstance(session, Mapping) else {}
    transaction_id = _first_nonempty(
        safe_transaction.get("transaction_id"),
        safe_precheck.get("transaction_id"),
        safe_session.get("transaction_id"),
    )
    started_at = _utc_timestamp()

    precheck_ok = bool(safe_precheck.get("precheck_ok", False))
    commit_ready = bool(safe_precheck.get("commit_ready", False))
    session_validation = validate_runtime_repair_commit_session(safe_session)
    if not precheck_ok or not commit_ready or not session_validation["valid"]:
        reason_parts: List[str] = []
        if not precheck_ok:
            reason_parts.append("precheck_failed")
        if not commit_ready:
            reason_parts.append("commit_not_ready")
        if not session_validation["valid"]:
            reason_parts.extend(session_validation["issues"])
        return {
            "transaction_id": transaction_id,
            "commit_id": "",
            "temp_workspace_path": "",
            "committed_files": [],
            "commit_success": False,
            "failed_operation": {
                "index": None,
                "op_type": "precheck",
                "target_path": "",
                "reason": "; ".join(_unique(reason_parts)),
            },
            "rollback_performed": False,
            "session_consumed": False,
            "started_at": started_at,
            "completed_at": _utc_timestamp(),
        }

    temp_workspace = Path(tempfile.mkdtemp(prefix="runtime_repair_commit_")).resolve()
    snapshot_root = Path(tempfile.mkdtemp(prefix="runtime_repair_commit_snapshot_")).resolve()
    applied_operations: List[Dict[str, Any]] = []
    failed_operation: Optional[Dict[str, Any]] = None
    rollback_performed = False

    try:
        _seed_sandbox_files(safe_transaction.get("sandbox_files"), sandbox_root=temp_workspace)
        _copy_directory_state(temp_workspace, snapshot_root)
        operation_items = safe_transaction.get("operations")
        if not isinstance(operation_items, list):
            operation_items = []

        for index, operation in enumerate(operation_items):
            if not isinstance(operation, Mapping):
                failed_operation = {
                    "index": index,
                    "op_type": "",
                    "target_path": "",
                    "reason": "operation_not_mapping",
                }
                raise RuntimeError("operation_not_mapping")
            try:
                applied_operations.append(
                    _apply_sandbox_operation(
                        operation,
                        index=index,
                        sandbox_root=temp_workspace,
                    )
                )
            except Exception as exc:
                failed_operation = {
                    "index": index,
                    "op_type": _first_nonempty(operation.get("op_type")),
                    "target_path": _normalize_display_path(operation.get("target_path")),
                    "reason": str(exc),
                }
                raise

        consumed_session = consume_runtime_repair_commit_session(safe_session)
        session_consumed = _first_nonempty(consumed_session.get("lease_status")) == "consumed"
        committed_files = sorted(_unique([
            _normalize_display_path(operation.get("target_path"))
            for operation in applied_operations
        ]))
        return {
            "transaction_id": transaction_id,
            "commit_id": _build_temp_commit_id(
                transaction_id=transaction_id,
                session_id=_first_nonempty(safe_session.get("session_id")),
                committed_files=committed_files,
            ),
            "temp_workspace_path": str(temp_workspace),
            "committed_files": committed_files,
            "commit_success": True,
            "failed_operation": None,
            "rollback_performed": False,
            "session_consumed": session_consumed,
            "started_at": started_at,
            "completed_at": _utc_timestamp(),
        }
    except Exception:
        _restore_directory_state(snapshot_root, temp_workspace)
        rollback_performed = True
        shutil.rmtree(temp_workspace, ignore_errors=True)
        return {
            "transaction_id": transaction_id,
            "commit_id": "",
            "temp_workspace_path": str(temp_workspace),
            "committed_files": [],
            "commit_success": False,
            "failed_operation": failed_operation,
            "rollback_performed": rollback_performed,
            "session_consumed": False,
            "started_at": started_at,
            "completed_at": _utc_timestamp(),
        }
    finally:
        shutil.rmtree(snapshot_root, ignore_errors=True)


def build_runtime_repair_commit_artifact(
    transaction: Any,
    preview: Any,
    review: Any,
    token: Any,
    intent: Any,
    session: Any,
    precheck: Any,
    commit_result: Any,
) -> Dict[str, Any]:
    safe_preview = preview if isinstance(preview, Mapping) else {}
    safe_review = review if isinstance(review, Mapping) else {}
    safe_token = token if isinstance(token, Mapping) else {}
    safe_intent = intent if isinstance(intent, Mapping) else {}
    safe_session = session if isinstance(session, Mapping) else {}
    safe_precheck = precheck if isinstance(precheck, Mapping) else {}
    safe_commit = commit_result if isinstance(commit_result, Mapping) else {}

    transaction_id = _first_nonempty(
        safe_commit.get("transaction_id"),
        safe_precheck.get("transaction_id"),
        safe_intent.get("transaction_id"),
        safe_review.get("transaction_id"),
    )
    changed_files = _sorted_changed_files(safe_preview.get("changed_files", safe_intent.get("changed_files", [])))
    diff_summary = freeze_runtime_export(safe_preview.get("diff_summary", safe_intent.get("diff_summary", {})))
    core_fields = {
        "transaction_id": transaction_id,
        "commit_id": _first_nonempty(safe_commit.get("commit_id")),
        "review_id": _first_nonempty(safe_review.get("review_id"), safe_intent.get("review_id")),
        "token_id": _first_nonempty(safe_token.get("token_id"), safe_intent.get("token_id")),
        "intent_id": _first_nonempty(safe_intent.get("intent_id")),
        "session_id": _first_nonempty(safe_session.get("session_id")),
        "consistency_digest": _first_nonempty(safe_precheck.get("consistency_digest")),
        "changed_files": changed_files,
        "diff_summary": diff_summary,
        "commit_success": bool(safe_commit.get("commit_success", False)),
        "rollback_performed": bool(safe_commit.get("rollback_performed", False)),
    }
    immutable_digest = _immutable_digest(core_fields)
    return {
        "artifact_id": _build_commit_artifact_id(core_fields=core_fields),
        **core_fields,
        "created_at": _utc_timestamp(),
        "immutable_digest": immutable_digest,
        "immutable_fields": freeze_runtime_export(core_fields),
        "transaction_snapshot": freeze_runtime_export(transaction),
        "review_snapshot": freeze_runtime_export(review),
        "token_snapshot": freeze_runtime_export(token),
        "intent_snapshot": freeze_runtime_export(intent),
        "session_snapshot": freeze_runtime_export(session),
        "preview_snapshot": freeze_runtime_export(preview),
        "precheck_snapshot": freeze_runtime_export(precheck),
        "commit_snapshot": freeze_runtime_export(commit_result),
    }


def validate_runtime_repair_commit_artifact(artifact: Any) -> Dict[str, Any]:
    safe = artifact if isinstance(artifact, Mapping) else {}
    issues: List[str] = []
    immutable_fields = safe.get("immutable_fields")
    if not isinstance(immutable_fields, Mapping):
        immutable_ok = False
    else:
        immutable_ok = True
        for field in (
            "transaction_id",
            "commit_id",
            "review_id",
            "token_id",
            "intent_id",
            "session_id",
            "consistency_digest",
            "changed_files",
            "diff_summary",
            "commit_success",
            "rollback_performed",
        ):
            if freeze_runtime_export(safe.get(field)) != freeze_runtime_export(immutable_fields.get(field)):
                immutable_ok = False
                break
    if not immutable_ok:
        issues.append("immutable_fields_modified")

    digest_ok = isinstance(immutable_fields, Mapping) and _first_nonempty(safe.get("immutable_digest")) == _immutable_digest(immutable_fields)
    if not digest_ok:
        issues.append("immutable_digest_mismatch")

    return {
        "valid": immutable_ok and digest_ok,
        "immutable_ok": immutable_ok,
        "digest_ok": digest_ok,
        "issues": _unique(issues),
    }


def build_runtime_repair_audit_bundle(artifact: Any) -> Dict[str, Any]:
    safe = artifact if isinstance(artifact, Mapping) else {}
    artifact_snapshot = _artifact_public_snapshot(safe)
    bundle = {
        "artifact_snapshot": artifact_snapshot,
        "review_snapshot": freeze_runtime_export(safe.get("review_snapshot", {})),
        "token_snapshot": freeze_runtime_export(safe.get("token_snapshot", {})),
        "intent_snapshot": freeze_runtime_export(safe.get("intent_snapshot", {})),
        "session_snapshot": freeze_runtime_export(safe.get("session_snapshot", {})),
        "preview_snapshot": freeze_runtime_export(safe.get("preview_snapshot", {})),
        "commit_snapshot": freeze_runtime_export(safe.get("commit_snapshot", {})),
    }
    bundle["bundle_digest"] = _immutable_digest(bundle)
    return bundle


def replay_runtime_repair_commit_artifact(artifact: Any) -> Dict[str, Any]:
    safe = artifact if isinstance(artifact, Mapping) else {}
    started_at = _utc_timestamp()
    replay_workspace = Path(tempfile.mkdtemp(prefix="runtime_repair_replay_")).resolve()
    snapshot_root = Path(tempfile.mkdtemp(prefix="runtime_repair_replay_snapshot_")).resolve()
    replay_success = False
    replay_changed_files: List[Any] = []
    replay_diff_summary: Dict[str, Any] = {}

    try:
        transaction_snapshot = safe.get("transaction_snapshot")
        if not isinstance(transaction_snapshot, Mapping):
            raise ValueError("transaction_snapshot_missing")
        _seed_sandbox_files(transaction_snapshot.get("sandbox_files"), sandbox_root=replay_workspace)
        before_snapshot = _snapshot_sandbox(replay_workspace)
        _copy_directory_state(replay_workspace, snapshot_root)

        operation_items = transaction_snapshot.get("operations")
        if not isinstance(operation_items, list):
            raise ValueError("operations_missing")
        applied_operations: List[Dict[str, Any]] = []
        for index, operation in enumerate(operation_items):
            if not isinstance(operation, Mapping):
                raise ValueError("operation_not_mapping")
            applied_operations.append(
                _apply_sandbox_operation(
                    operation,
                    index=index,
                    sandbox_root=replay_workspace,
                )
            )

        after_snapshot = _snapshot_sandbox(replay_workspace)
        operation_by_path = _operation_type_by_path(applied_operations)
        replay_changed_files = _changed_files_from_snapshots(
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            operation_by_path=operation_by_path,
        )
        replay_diff_summary = _diff_summary_from_changed_files(
            changed_files=replay_changed_files,
            failures=0,
            rollback=False,
        )
        replay_success = True
        return {
            "replay_id": _build_replay_id(
                artifact_id=_first_nonempty(safe.get("artifact_id")),
                replay_digest=_replay_digest(
                    changed_files=replay_changed_files,
                    diff_summary=replay_diff_summary,
                    rollback_performed=False,
                ),
            ),
            "artifact_id": _first_nonempty(safe.get("artifact_id")),
            "replay_workspace": str(replay_workspace),
            "replay_success": replay_success,
            "replay_changed_files": replay_changed_files,
            "replay_diff_summary": replay_diff_summary,
            "replay_digest": _replay_digest(
                changed_files=replay_changed_files,
                diff_summary=replay_diff_summary,
                rollback_performed=False,
            ),
            "started_at": started_at,
            "completed_at": _utc_timestamp(),
        }
    except Exception:
        _restore_directory_state(snapshot_root, replay_workspace)
        shutil.rmtree(replay_workspace, ignore_errors=True)
        replay_diff_summary = _diff_summary_from_changed_files(
            changed_files=[],
            failures=1,
            rollback=True,
        )
        return {
            "replay_id": _build_replay_id(
                artifact_id=_first_nonempty(safe.get("artifact_id")),
                replay_digest=_replay_digest(
                    changed_files=[],
                    diff_summary=replay_diff_summary,
                    rollback_performed=True,
                ),
            ),
            "artifact_id": _first_nonempty(safe.get("artifact_id")),
            "replay_workspace": str(replay_workspace),
            "replay_success": False,
            "replay_changed_files": [],
            "replay_diff_summary": replay_diff_summary,
            "replay_digest": _replay_digest(
                changed_files=[],
                diff_summary=replay_diff_summary,
                rollback_performed=True,
            ),
            "started_at": started_at,
            "completed_at": _utc_timestamp(),
        }
    finally:
        shutil.rmtree(snapshot_root, ignore_errors=True)


def verify_runtime_repair_reproducibility(
    artifact: Any,
    replay_result: Any,
) -> Dict[str, Any]:
    safe_artifact = artifact if isinstance(artifact, Mapping) else {}
    safe_replay = replay_result if isinstance(replay_result, Mapping) else {}
    expected_changed_files = _sorted_changed_files(safe_artifact.get("changed_files", []))
    replay_changed_files = _sorted_changed_files(safe_replay.get("replay_changed_files", []))
    expected_diff_summary = freeze_runtime_export(safe_artifact.get("diff_summary", {}))
    replay_diff_summary = freeze_runtime_export(safe_replay.get("replay_diff_summary", {}))
    expected_digest = _replay_digest(
        changed_files=expected_changed_files,
        diff_summary=expected_diff_summary,
        rollback_performed=bool(safe_artifact.get("rollback_performed", False)),
    )
    replay_digest = _first_nonempty(safe_replay.get("replay_digest"))

    changed_files_match = expected_changed_files == replay_changed_files
    diff_summary_match = expected_diff_summary == replay_diff_summary
    digest_match = expected_digest == replay_digest
    rollback_match = bool(safe_artifact.get("rollback_performed", False)) == bool(replay_diff_summary.get("rollback", False))

    issues: List[str] = []
    if not changed_files_match:
        issues.append("changed_files_mismatch")
    if not diff_summary_match:
        issues.append("diff_summary_mismatch")
    if not digest_match:
        issues.append("digest_mismatch")
    if not rollback_match:
        issues.append("rollback_state_mismatch")
    if not bool(safe_replay.get("replay_success", False)):
        issues.append("replay_failed")

    return {
        "reproducible": not issues,
        "changed_files_match": changed_files_match,
        "diff_summary_match": diff_summary_match,
        "digest_match": digest_match,
        "issues": _unique(issues),
    }


def create_runtime_repair_lineage_node(artifact: Any) -> Dict[str, Any]:
    safe = artifact if isinstance(artifact, Mapping) else {}
    artifact_id = _first_nonempty(safe.get("artifact_id"))
    parent_artifact_id = _first_nonempty(safe.get("parent_artifact_id"))
    lineage_type = _first_nonempty(
        safe.get("lineage_type"),
        "original" if not parent_artifact_id else "derived",
    )
    root_artifact_id = _first_nonempty(
        safe.get("root_artifact_id"),
        artifact_id if not parent_artifact_id else "",
    )
    lineage_depth = int(safe.get("lineage_depth") or (0 if not parent_artifact_id else 1))
    immutable_fields = {
        "artifact_id": artifact_id,
        "parent_artifact_id": parent_artifact_id,
        "root_artifact_id": root_artifact_id,
        "lineage_depth": lineage_depth,
        "lineage_type": lineage_type,
    }
    return {
        "lineage_id": _build_lineage_id(immutable_fields=immutable_fields),
        **immutable_fields,
        "created_at": _utc_timestamp(),
        "immutable_fields": freeze_runtime_export(immutable_fields),
        "immutable_digest": _immutable_digest(immutable_fields),
    }


def build_runtime_repair_lineage_graph(nodes: Any) -> Dict[str, Any]:
    safe_nodes = [node for node in nodes if isinstance(node, Mapping)] if isinstance(nodes, list) else []
    sorted_nodes = sorted(
        [freeze_runtime_export(node) for node in safe_nodes],
        key=lambda node: (_first_nonempty(node.get("root_artifact_id")), int(node.get("lineage_depth") or 0), _first_nonempty(node.get("artifact_id"))),
    )
    node_by_artifact = {
        _first_nonempty(node.get("artifact_id")): node
        for node in sorted_nodes
        if _first_nonempty(node.get("artifact_id"))
    }
    root_artifact_id = _first_nonempty(
        *[
            node.get("artifact_id")
            for node in sorted_nodes
            if not _first_nonempty(node.get("parent_artifact_id"))
        ],
        *[node.get("root_artifact_id") for node in sorted_nodes],
    )
    lineage_paths = [
        _lineage_path_for_node(node, node_by_artifact)
        for node in sorted_nodes
    ]
    replay_chain = [
        _first_nonempty(node.get("artifact_id"))
        for node in sorted_nodes
        if _first_nonempty(node.get("lineage_type")) == "replay"
    ]
    rollback_chain = [
        _first_nonempty(node.get("artifact_id"))
        for node in sorted_nodes
        if _first_nonempty(node.get("lineage_type")) == "rollback"
    ]
    graph_core = {
        "root_artifact_id": root_artifact_id,
        "nodes": sorted_nodes,
        "lineage_paths": lineage_paths,
        "replay_chain": replay_chain,
        "rollback_chain": rollback_chain,
    }
    return {
        "root_artifact_id": root_artifact_id,
        "node_count": len(sorted_nodes),
        "lineage_paths": lineage_paths,
        "replay_chain": replay_chain,
        "rollback_chain": rollback_chain,
        "nodes": sorted_nodes,
        "graph_digest": _immutable_digest(graph_core),
    }


def validate_runtime_repair_lineage_graph(graph: Any) -> Dict[str, Any]:
    safe = graph if isinstance(graph, Mapping) else {}
    nodes = safe.get("nodes")
    safe_nodes = [node for node in nodes if isinstance(node, Mapping)] if isinstance(nodes, list) else []
    node_by_artifact = {
        _first_nonempty(node.get("artifact_id")): node
        for node in safe_nodes
        if _first_nonempty(node.get("artifact_id"))
    }
    orphan_nodes = sorted([
        _first_nonempty(node.get("artifact_id"))
        for node in safe_nodes
        if _first_nonempty(node.get("parent_artifact_id"))
        and _first_nonempty(node.get("parent_artifact_id")) not in node_by_artifact
    ])
    cycle_detected = _lineage_cycle_detected(node_by_artifact)
    immutable_ok = all(_lineage_node_immutable_ok(node) for node in safe_nodes)
    ancestry_ok = all(
        _lineage_replay_ancestry_ok(node, node_by_artifact)
        for node in safe_nodes
        if _first_nonempty(node.get("lineage_type")) == "replay"
    )

    issues: List[str] = []
    if orphan_nodes:
        issues.append("orphan_nodes")
    if cycle_detected:
        issues.append("cycle_detected")
    if not immutable_ok:
        issues.append("immutable_fields_modified")
    if not ancestry_ok:
        issues.append("replay_ancestry_modified")
    return {
        "valid": not issues,
        "orphan_nodes": orphan_nodes,
        "cycle_detected": cycle_detected,
        "immutable_ok": immutable_ok,
        "issues": issues,
    }


def build_runtime_repair_knowledge_snapshot(
    artifact: Any,
    replay_result: Any,
    lineage_node: Any,
) -> Dict[str, Any]:
    safe_artifact = artifact if isinstance(artifact, Mapping) else {}
    safe_replay = replay_result if isinstance(replay_result, Mapping) else {}
    safe_lineage = lineage_node if isinstance(lineage_node, Mapping) else {}

    changed_files = _sorted_changed_files(safe_artifact.get("changed_files", []))
    diff_summary = safe_artifact.get("diff_summary") if isinstance(safe_artifact.get("diff_summary"), Mapping) else {}
    replay_stable = _replay_digest(
        changed_files=changed_files,
        diff_summary=diff_summary,
        rollback_performed=bool(safe_artifact.get("rollback_performed", False)),
    ) == _first_nonempty(safe_replay.get("replay_digest")) and bool(safe_replay.get("replay_success", False))
    replay_consistency = "stable" if replay_stable else "unstable"
    operation_patterns = _knowledge_operation_patterns(changed_files=changed_files, diff_summary=diff_summary)
    rollback_patterns = {
        "rollback_occurred": bool(safe_artifact.get("rollback_performed", False)),
        "rollback_success": bool(safe_artifact.get("rollback_performed", False)) and not bool(safe_artifact.get("commit_success", False)),
        "rollback_reproducible": bool(safe_artifact.get("rollback_performed", False)) and replay_consistency == "stable",
    }
    repair_patterns = _knowledge_repair_patterns(
        diff_summary=diff_summary,
        rollback_patterns=rollback_patterns,
        replay_consistency=replay_consistency,
    )
    core_fields = {
        "artifact_id": _first_nonempty(safe_artifact.get("artifact_id")),
        "lineage_id": _first_nonempty(safe_lineage.get("lineage_id")),
        "repair_patterns": repair_patterns,
        "operation_patterns": operation_patterns,
        "rollback_patterns": rollback_patterns,
        "replay_consistency": replay_consistency,
        "changed_file_types": _changed_file_types(changed_files),
    }
    knowledge_digest = _immutable_digest(core_fields)
    return {
        "knowledge_id": f"repair_knowledge_{knowledge_digest[:16]}",
        **core_fields,
        "generated_at": _utc_timestamp(),
        "knowledge_digest": knowledge_digest,
        "immutable_fields": freeze_runtime_export(core_fields),
    }


def validate_runtime_repair_knowledge_snapshot(snapshot: Any) -> Dict[str, Any]:
    safe = snapshot if isinstance(snapshot, Mapping) else {}
    immutable_fields = safe.get("immutable_fields")
    immutable_ok = isinstance(immutable_fields, Mapping)
    if immutable_ok:
        for field in (
            "artifact_id",
            "lineage_id",
            "repair_patterns",
            "operation_patterns",
            "rollback_patterns",
            "replay_consistency",
            "changed_file_types",
        ):
            if freeze_runtime_export(safe.get(field)) != freeze_runtime_export(immutable_fields.get(field)):
                immutable_ok = False
                break
    digest_ok = immutable_ok and _first_nonempty(safe.get("knowledge_digest")) == _immutable_digest(immutable_fields)
    issues: List[str] = []
    if not immutable_ok:
        issues.append("immutable_fields_modified")
    if not digest_ok:
        issues.append("knowledge_digest_mismatch")
    if _first_nonempty(safe.get("replay_consistency")) not in ("stable", "unstable"):
        issues.append("invalid_replay_consistency")
    return {
        "valid": not issues,
        "digest_ok": digest_ok,
        "immutable_ok": immutable_ok,
        "issues": issues,
    }


def build_runtime_repair_knowledge_index(snapshots: Any) -> Dict[str, Any]:
    safe_snapshots = [snapshot for snapshot in snapshots if isinstance(snapshot, Mapping)] if isinstance(snapshots, list) else []
    entries = sorted(
        [_knowledge_index_entry(snapshot) for snapshot in safe_snapshots],
        key=lambda item: (_first_nonempty(item.get("artifact_id")), _first_nonempty(item.get("lineage_id")), _first_nonempty(item.get("knowledge_id"))),
    )
    by_repair_pattern: Dict[str, List[Dict[str, Any]]] = {}
    by_operation_pattern: Dict[str, List[Dict[str, Any]]] = {}
    by_file_type: Dict[str, List[Dict[str, Any]]] = {}
    by_replay_consistency: Dict[str, List[Dict[str, Any]]] = {}

    for entry in entries:
        for pattern in entry["repair_patterns"]:
            by_repair_pattern.setdefault(pattern, []).append(entry)
        for operation_type, ratio in entry["operation_type_ratios"].items():
            if ratio > 0:
                by_operation_pattern.setdefault(operation_type, []).append(entry)
        for file_type in entry["changed_file_types"]:
            by_file_type.setdefault(file_type, []).append(entry)
        by_replay_consistency.setdefault(entry["replay_consistency"], []).append(entry)

    index_core = {
        "snapshot_count": len(entries),
        "entries": entries,
        "by_repair_pattern": _sorted_index_map(by_repair_pattern),
        "by_operation_pattern": _sorted_index_map(by_operation_pattern),
        "by_file_type": _sorted_index_map(by_file_type),
        "by_replay_consistency": _sorted_index_map(by_replay_consistency),
    }
    index_digest = _immutable_digest(index_core)
    return {
        "index_id": f"repair_knowledge_index_{index_digest[:16]}",
        **index_core,
        "index_digest": index_digest,
        "built_at": _utc_timestamp(),
    }


def query_runtime_repair_knowledge_index(index: Any, query: Any) -> Dict[str, Any]:
    safe_index = index if isinstance(index, Mapping) else {}
    safe_query = query if isinstance(query, Mapping) else {}
    entries = safe_index.get("entries")
    safe_entries = [entry for entry in entries if isinstance(entry, Mapping)] if isinstance(entries, list) else []
    matches: List[Dict[str, Any]] = []
    for entry in safe_entries:
        if _knowledge_entry_matches(entry, safe_query):
            matches.append(freeze_runtime_export(entry))
    matches = sorted(
        matches,
        key=lambda item: (_first_nonempty(item.get("artifact_id")), _first_nonempty(item.get("lineage_id")), _first_nonempty(item.get("knowledge_id"))),
    )
    query_core = {
        "query": freeze_runtime_export(safe_query),
        "matches": matches,
    }
    return {
        "matches": matches,
        "match_count": len(matches),
        "query_digest": _immutable_digest(query_core),
    }


def validate_runtime_repair_knowledge_index(index: Any) -> Dict[str, Any]:
    safe = index if isinstance(index, Mapping) else {}
    index_core = {
        "snapshot_count": int(safe.get("snapshot_count") or 0),
        "entries": freeze_runtime_export(safe.get("entries", [])),
        "by_repair_pattern": freeze_runtime_export(safe.get("by_repair_pattern", {})),
        "by_operation_pattern": freeze_runtime_export(safe.get("by_operation_pattern", {})),
        "by_file_type": freeze_runtime_export(safe.get("by_file_type", {})),
        "by_replay_consistency": freeze_runtime_export(safe.get("by_replay_consistency", {})),
    }
    digest_ok = _first_nonempty(safe.get("index_digest")) == _immutable_digest(index_core)
    issues: List[str] = []
    if not digest_ok:
        issues.append("index_digest_mismatch")
    if int(safe.get("snapshot_count") or 0) != len(index_core["entries"]):
        issues.append("snapshot_count_mismatch")
    return {
        "valid": not issues,
        "digest_ok": digest_ok,
        "issues": issues,
    }


def build_runtime_repair_similarity_query(
    transaction: Any,
    preview: Any = None,
) -> Dict[str, Any]:
    safe_transaction = transaction if isinstance(transaction, Mapping) else {}
    safe_preview = preview if isinstance(preview, Mapping) else {}
    operations = safe_transaction.get("operations")
    safe_operations = [operation for operation in operations if isinstance(operation, Mapping)] if isinstance(operations, list) else []
    changed_files = safe_preview.get("changed_files")
    safe_changed_files = _sorted_changed_files(changed_files) if isinstance(changed_files, list) else _changed_files_from_operations(safe_operations)
    diff_summary = safe_preview.get("diff_summary") if isinstance(safe_preview.get("diff_summary"), Mapping) else _diff_summary_from_operations(safe_operations)
    replay_consistency = _first_nonempty(safe_preview.get("replay_consistency"), "unknown")
    rollback_triggered = bool(diff_summary.get("rollback", False)) or int(diff_summary.get("failures") or 0) > 0

    repair_patterns = _knowledge_repair_patterns(
        diff_summary=diff_summary,
        rollback_patterns={"rollback_occurred": rollback_triggered},
        replay_consistency=replay_consistency,
    )
    operation_patterns = {
        "operation_types": sorted(_unique([
            _first_nonempty(operation.get("op_type"))
            for operation in safe_operations
            if _first_nonempty(operation.get("op_type"))
        ])),
        "rollback_triggered": rollback_triggered,
    }
    file_types = _changed_file_types(safe_changed_files)
    core = {
        "repair_patterns": repair_patterns,
        "operation_patterns": operation_patterns,
        "file_types": file_types,
        "changed_file_count": len(safe_changed_files),
        "replay_consistency": replay_consistency,
    }
    query_digest = _immutable_digest(core)
    return {
        "query_id": f"repair_similarity_query_{query_digest[:16]}",
        **core,
        "query_digest": query_digest,
    }


def retrieve_runtime_repair_candidates(
    knowledge_index: Any,
    similarity_query: Any,
) -> Dict[str, Any]:
    safe_index = knowledge_index if isinstance(knowledge_index, Mapping) else {}
    safe_query = similarity_query if isinstance(similarity_query, Mapping) else {}
    entries = safe_index.get("entries")
    safe_entries = [entry for entry in entries if isinstance(entry, Mapping)] if isinstance(entries, list) else []
    scored = [
        _score_similarity_candidate(entry, safe_query)
        for entry in safe_entries
    ]
    matches = [
        item["entry"]
        for item in scored
        if item["score"] > 0
    ]
    ranked_scored = sorted(
        [item for item in scored if item["score"] > 0],
        key=lambda item: (-item["score"], _first_nonempty(item["entry"].get("artifact_id")), _first_nonempty(item["entry"].get("knowledge_id"))),
    )
    ranked_matches = [item["entry"] for item in ranked_scored]
    similarity_scores = {
        _first_nonempty(item["entry"].get("artifact_id")): item["score"]
        for item in ranked_scored
    }
    core = {
        "query_digest": _first_nonempty(safe_query.get("query_digest")),
        "ranked_matches": ranked_matches,
        "similarity_scores": similarity_scores,
    }
    retrieval_digest = _immutable_digest(core)
    return {
        "retrieval_id": f"repair_candidate_retrieval_{retrieval_digest[:16]}",
        "query_digest": _first_nonempty(safe_query.get("query_digest")),
        "query_snapshot": freeze_runtime_export(safe_query),
        "matches": matches,
        "ranked_matches": ranked_matches,
        "similarity_scores": similarity_scores,
        "retrieval_digest": retrieval_digest,
    }


def validate_runtime_repair_candidate_retrieval(result: Any) -> Dict[str, Any]:
    safe = result if isinstance(result, Mapping) else {}
    ranked_matches = safe.get("ranked_matches")
    similarity_scores = safe.get("similarity_scores")
    safe_ranked = [item for item in ranked_matches if isinstance(item, Mapping)] if isinstance(ranked_matches, list) else []
    safe_scores = similarity_scores if isinstance(similarity_scores, Mapping) else {}
    expected_ranked = sorted(
        safe_ranked,
        key=lambda item: (-int(safe_scores.get(_first_nonempty(item.get("artifact_id"))) or 0), _first_nonempty(item.get("artifact_id")), _first_nonempty(item.get("knowledge_id"))),
    )
    deterministic_ok = safe_ranked == expected_ranked
    core = {
        "query_digest": _first_nonempty(safe.get("query_digest")),
        "ranked_matches": safe_ranked,
        "similarity_scores": freeze_runtime_export(safe_scores),
    }
    digest_ok = _first_nonempty(safe.get("retrieval_digest")) == _immutable_digest(core)
    issues: List[str] = []
    if not deterministic_ok:
        issues.append("ranking_not_deterministic")
    if not digest_ok:
        issues.append("retrieval_digest_mismatch")
    return {
        "valid": not issues,
        "deterministic_ok": deterministic_ok,
        "issues": issues,
    }


def explain_runtime_repair_candidate_match(
    similarity_query: Any,
    candidate: Any,
) -> Dict[str, Any]:
    safe_query = similarity_query if isinstance(similarity_query, Mapping) else {}
    safe_candidate = candidate if isinstance(candidate, Mapping) else {}
    matched_patterns = sorted(
        set(_string_list(safe_query.get("repair_patterns"), fallback=[])).intersection(
            set(_string_list(safe_candidate.get("repair_patterns"), fallback=[]))
        )
    )
    query_operation_patterns = safe_query.get("operation_patterns")
    query_operation_types = set(_string_list(
        query_operation_patterns.get("operation_types") if isinstance(query_operation_patterns, Mapping) else [],
        fallback=[],
    ))
    candidate_operation_ratios = safe_candidate.get("operation_type_ratios")
    candidate_operation_types = {
        op_type
        for op_type, ratio in candidate_operation_ratios.items()
        if isinstance(candidate_operation_ratios, Mapping) and float(ratio or 0) > 0
    } if isinstance(candidate_operation_ratios, Mapping) else set()
    matched_operation_types = sorted(query_operation_types.intersection(candidate_operation_types))
    matched_file_types = sorted(
        set(_string_list(safe_query.get("file_types"), fallback=[])).intersection(
            set(_string_list(safe_candidate.get("changed_file_types"), fallback=[]))
        )
    )
    replay_consistency_match = (
        _first_nonempty(safe_query.get("replay_consistency"))
        == _first_nonempty(safe_candidate.get("replay_consistency"))
    )
    query_rollback = "rollback triggered" in _string_list(safe_query.get("repair_patterns"), fallback=[])
    candidate_rollback = "rollback triggered" in _string_list(safe_candidate.get("repair_patterns"), fallback=[])
    rollback_pattern_match = query_rollback and candidate_rollback
    similarity_score = _score_similarity_candidate(safe_candidate, safe_query)["score"]
    explanation_summary = _candidate_explanation_summary(
        matched_patterns=matched_patterns,
        matched_operation_types=matched_operation_types,
        matched_file_types=matched_file_types,
        replay_consistency_match=replay_consistency_match,
        rollback_pattern_match=rollback_pattern_match,
    )
    core = {
        "candidate_id": _first_nonempty(safe_candidate.get("artifact_id"), safe_candidate.get("knowledge_id")),
        "matched_patterns": matched_patterns,
        "matched_operation_types": matched_operation_types,
        "matched_file_types": matched_file_types,
        "replay_consistency_match": replay_consistency_match,
        "rollback_pattern_match": rollback_pattern_match,
        "similarity_score": similarity_score,
        "explanation_summary": explanation_summary,
    }
    explanation_digest = _immutable_digest(core)
    return {
        "candidate_id": core["candidate_id"],
        "explanation_id": f"repair_candidate_explanation_{explanation_digest[:16]}",
        **{key: core[key] for key in (
            "matched_patterns",
            "matched_operation_types",
            "matched_file_types",
            "replay_consistency_match",
            "rollback_pattern_match",
            "similarity_score",
            "explanation_summary",
        )},
        "explanation_digest": explanation_digest,
    }


def build_runtime_repair_candidate_explanations(retrieval_result: Any) -> Dict[str, Any]:
    safe = retrieval_result if isinstance(retrieval_result, Mapping) else {}
    query_snapshot = safe.get("query_snapshot")
    if not isinstance(query_snapshot, Mapping):
        query_snapshot = {}
    ranked_matches = safe.get("ranked_matches")
    safe_matches = [match for match in ranked_matches if isinstance(match, Mapping)] if isinstance(ranked_matches, list) else []
    explanations = [
        explain_runtime_repair_candidate_match(query_snapshot, candidate)
        for candidate in safe_matches
    ]
    explanations = sorted(
        explanations,
        key=lambda item: (-int(item.get("similarity_score") or 0), _first_nonempty(item.get("candidate_id")), _first_nonempty(item.get("explanation_id"))),
    )
    core = {
        "retrieval_id": _first_nonempty(safe.get("retrieval_id")),
        "explanations": explanations,
    }
    return {
        "retrieval_id": core["retrieval_id"],
        "explanations": explanations,
        "explanation_count": len(explanations),
        "explanations_digest": _immutable_digest(core),
    }


def validate_runtime_repair_candidate_explanations(result: Any) -> Dict[str, Any]:
    safe = result if isinstance(result, Mapping) else {}
    explanations = safe.get("explanations")
    safe_explanations = [item for item in explanations if isinstance(item, Mapping)] if isinstance(explanations, list) else []
    expected_order = sorted(
        safe_explanations,
        key=lambda item: (-int(item.get("similarity_score") or 0), _first_nonempty(item.get("candidate_id")), _first_nonempty(item.get("explanation_id"))),
    )
    deterministic_ok = safe_explanations == expected_order
    core = {
        "retrieval_id": _first_nonempty(safe.get("retrieval_id")),
        "explanations": safe_explanations,
    }
    digest_ok = _first_nonempty(safe.get("explanations_digest")) == _immutable_digest(core)
    issues: List[str] = []
    if not deterministic_ok:
        issues.append("explanation_order_not_deterministic")
    if not digest_ok:
        issues.append("explanations_digest_mismatch")
    if int(safe.get("explanation_count") or 0) != len(safe_explanations):
        issues.append("explanation_count_mismatch")
    return {
        "valid": not issues,
        "deterministic_ok": deterministic_ok and digest_ok,
        "issues": issues,
    }


def build_runtime_repair_recommendation_draft(
    similarity_query: Any,
    retrieval_result: Any,
    explanations: Any,
) -> Dict[str, Any]:
    safe_query = similarity_query if isinstance(similarity_query, Mapping) else {}
    safe_retrieval = retrieval_result if isinstance(retrieval_result, Mapping) else {}
    safe_explanations = explanations if isinstance(explanations, Mapping) else {}
    ranked_matches = safe_retrieval.get("ranked_matches")
    safe_matches = [match for match in ranked_matches if isinstance(match, Mapping)] if isinstance(ranked_matches, list) else []
    similarity_scores = safe_retrieval.get("similarity_scores")
    safe_scores = similarity_scores if isinstance(similarity_scores, Mapping) else {}
    recommended_candidates = [
        {
            "artifact_id": _first_nonempty(match.get("artifact_id")),
            "knowledge_id": _first_nonempty(match.get("knowledge_id")),
            "lineage_id": _first_nonempty(match.get("lineage_id")),
            "similarity_score": int(safe_scores.get(_first_nonempty(match.get("artifact_id"))) or 0),
        }
        for match in safe_matches
    ]
    recommended_candidates = sorted(
        recommended_candidates,
        key=lambda item: (-int(item["similarity_score"]), item["artifact_id"], item["knowledge_id"]),
    )
    explanation_items = safe_explanations.get("explanations")
    safe_explanation_items = [item for item in explanation_items if isinstance(item, Mapping)] if isinstance(explanation_items, list) else []
    explanation_refs = sorted(
        [
            {
                "candidate_id": _first_nonempty(item.get("candidate_id")),
                "explanation_id": _first_nonempty(item.get("explanation_id")),
            }
            for item in safe_explanation_items
        ],
        key=lambda item: (item["candidate_id"], item["explanation_id"]),
    )
    top_score = recommended_candidates[0]["similarity_score"] if recommended_candidates else 0
    core = {
        "query_id": _first_nonempty(safe_query.get("query_id")),
        "retrieval_id": _first_nonempty(safe_retrieval.get("retrieval_id")),
        "recommendation_status": "draft_only",
        "recommended_candidates": recommended_candidates,
        "explanation_refs": explanation_refs,
        "confidence_summary": _recommendation_confidence(top_score),
        "limitations": _recommendation_limitations(),
    }
    draft_digest = _immutable_digest(core)
    return {
        "draft_id": f"repair_recommendation_draft_{draft_digest[:16]}",
        **core,
        "draft_digest": draft_digest,
        "created_at": _utc_timestamp(),
    }


def validate_runtime_repair_recommendation_draft(draft: Any) -> Dict[str, Any]:
    safe = draft if isinstance(draft, Mapping) else {}
    core = {
        "query_id": _first_nonempty(safe.get("query_id")),
        "retrieval_id": _first_nonempty(safe.get("retrieval_id")),
        "recommendation_status": _first_nonempty(safe.get("recommendation_status")),
        "recommended_candidates": freeze_runtime_export(safe.get("recommended_candidates", [])),
        "explanation_refs": freeze_runtime_export(safe.get("explanation_refs", [])),
        "confidence_summary": _first_nonempty(safe.get("confidence_summary")),
        "limitations": freeze_runtime_export(safe.get("limitations", [])),
    }
    digest_ok = _first_nonempty(safe.get("draft_digest")) == _immutable_digest(core)
    read_only_ok = (
        core["recommendation_status"] == "draft_only"
        and all(item in core["limitations"] for item in _recommendation_limitations())
    )
    issues: List[str] = []
    if not digest_ok:
        issues.append("draft_digest_mismatch")
    if not read_only_ok:
        issues.append("read_only_constraints_missing")
    return {
        "valid": not issues,
        "digest_ok": digest_ok,
        "read_only_ok": read_only_ok,
        "issues": issues,
    }


def create_runtime_repair_recommendation_review(
    recommendation_draft: Any,
) -> Dict[str, Any]:
    safe = recommendation_draft if isinstance(recommendation_draft, Mapping) else {}
    core = {
        "draft_id": _first_nonempty(safe.get("draft_id")),
        "review_status": "pending",
        "usable": False,
    }
    review_digest = _recommendation_review_digest(core)
    return {
        "review_id": f"repair_recommendation_review_{review_digest[:16]}",
        **core,
        "created_at": _utc_timestamp(),
        "review_digest": review_digest,
        "draft_snapshot": freeze_runtime_export(safe),
    }


def approve_runtime_repair_recommendation_review(
    review: Any,
    reviewer: Any,
    note: Any = "",
) -> Dict[str, Any]:
    safe = dict(review) if isinstance(review, Mapping) else {}
    safe["review_status"] = "approved"
    safe["approved_by"] = _first_nonempty(reviewer)
    safe["approved_at"] = _utc_timestamp()
    safe["note"] = _first_nonempty(note)
    safe["usable"] = True
    safe["review_digest"] = _recommendation_review_digest(safe)
    return safe


def reject_runtime_repair_recommendation_review(
    review: Any,
    reviewer: Any,
    reason: Any = "",
) -> Dict[str, Any]:
    safe = dict(review) if isinstance(review, Mapping) else {}
    safe["review_status"] = "rejected"
    safe["rejected_by"] = _first_nonempty(reviewer)
    safe["rejected_at"] = _utc_timestamp()
    safe["reason"] = _first_nonempty(reason)
    safe["usable"] = False
    safe["review_digest"] = _recommendation_review_digest(safe)
    return safe


def validate_runtime_repair_recommendation_review(review: Any) -> Dict[str, Any]:
    safe = review if isinstance(review, Mapping) else {}
    status = _first_nonempty(safe.get("review_status"))
    usable = bool(safe.get("usable", False))
    deterministic_ok = _first_nonempty(safe.get("review_digest")) == _recommendation_review_digest(safe)
    issues: List[str] = []
    if status not in ("pending", "approved", "rejected"):
        issues.append("invalid_review_status")
    if status != "approved" and usable:
        issues.append("usable_without_approval")
    if status == "approved" and not usable:
        issues.append("approved_not_usable")
    if not deterministic_ok:
        issues.append("review_digest_mismatch")
    draft_snapshot = safe.get("draft_snapshot")
    if isinstance(draft_snapshot, Mapping):
        draft_validation = validate_runtime_repair_recommendation_draft(draft_snapshot)
        if not draft_validation["read_only_ok"]:
            issues.append("draft_not_read_only")
    return {
        "valid": not issues,
        "deterministic_ok": deterministic_ok,
        "issues": issues,
    }


def build_runtime_repair_recommendation_provenance(
    recommendation_draft: Any,
    retrieval_result: Any,
    explanations: Any,
    recommendation_review: Any = None,
) -> Dict[str, Any]:
    safe_draft = recommendation_draft if isinstance(recommendation_draft, Mapping) else {}
    safe_retrieval = retrieval_result if isinstance(retrieval_result, Mapping) else {}
    safe_explanations = explanations if isinstance(explanations, Mapping) else {}
    safe_review = recommendation_review if isinstance(recommendation_review, Mapping) else {}
    ranked_matches = safe_retrieval.get("ranked_matches")
    safe_matches = [match for match in ranked_matches if isinstance(match, Mapping)] if isinstance(ranked_matches, list) else []
    explanation_items = safe_explanations.get("explanations")
    safe_explanation_items = [item for item in explanation_items if isinstance(item, Mapping)] if isinstance(explanation_items, list) else []

    candidate_artifact_ids = sorted(_unique([
        _first_nonempty(match.get("artifact_id"))
        for match in safe_matches
    ]))
    lineage_refs = _recommendation_lineage_refs(safe_matches)
    replay_consistency_refs = _recommendation_replay_consistency_refs(safe_matches)
    core = {
        "recommendation_id": _first_nonempty(safe_draft.get("draft_id")),
        "retrieval_id": _first_nonempty(safe_retrieval.get("retrieval_id")),
        "explanation_ids": sorted(_unique([
            _first_nonempty(item.get("explanation_id"))
            for item in safe_explanation_items
        ])),
        "candidate_artifact_ids": candidate_artifact_ids,
        "lineage_refs": lineage_refs,
        "replay_consistency_refs": replay_consistency_refs,
        "review_id": _first_nonempty(safe_review.get("review_id")),
        "review_status": _first_nonempty(safe_review.get("review_status")),
    }
    provenance_digest = _immutable_digest(core)
    return {
        "provenance_id": f"repair_recommendation_provenance_{provenance_digest[:16]}",
        **core,
        "provenance_digest": provenance_digest,
        "created_at": _utc_timestamp(),
        "immutable_fields": freeze_runtime_export(core),
    }


def validate_runtime_repair_recommendation_provenance(provenance: Any) -> Dict[str, Any]:
    safe = provenance if isinstance(provenance, Mapping) else {}
    immutable_fields = safe.get("immutable_fields")
    immutable_ok = isinstance(immutable_fields, Mapping)
    if immutable_ok:
        for field in (
            "recommendation_id",
            "retrieval_id",
            "explanation_ids",
            "candidate_artifact_ids",
            "lineage_refs",
            "replay_consistency_refs",
            "review_id",
            "review_status",
        ):
            if freeze_runtime_export(safe.get(field)) != freeze_runtime_export(immutable_fields.get(field)):
                immutable_ok = False
                break
    digest_ok = immutable_ok and _first_nonempty(safe.get("provenance_digest")) == _immutable_digest(immutable_fields)
    issues: List[str] = []
    if not immutable_ok:
        issues.append("immutable_fields_modified")
    if not digest_ok:
        issues.append("provenance_digest_mismatch")
    return {
        "valid": not issues,
        "immutable_ok": immutable_ok,
        "digest_ok": digest_ok,
        "issues": issues,
    }


def assess_runtime_repair_risk(
    transaction: Any,
    recommendation_draft: Any = None,
    retrieval_result: Any = None,
) -> Dict[str, Any]:
    safe_transaction = transaction if isinstance(transaction, Mapping) else {}
    safe_draft = recommendation_draft if isinstance(recommendation_draft, Mapping) else {}
    safe_retrieval = retrieval_result if isinstance(retrieval_result, Mapping) else {}
    factors = _repair_risk_factors(
        transaction=safe_transaction,
        recommendation_draft=safe_draft,
        retrieval_result=safe_retrieval,
    )
    risk_score = sum(int(item["score"]) for item in factors)
    core = {
        "transaction_id": _first_nonempty(safe_transaction.get("transaction_id")),
        "risk_level": _risk_level_for_score(risk_score),
        "risk_score": risk_score,
        "risk_factors": factors,
        "mitigation_notes": _risk_mitigation_notes(),
    }
    risk_digest = _immutable_digest(core)
    return {
        "risk_id": f"repair_risk_{risk_digest[:16]}",
        **core,
        "assessed_at": _utc_timestamp(),
        "risk_digest": risk_digest,
    }


def validate_runtime_repair_risk_assessment(risk: Any) -> Dict[str, Any]:
    safe = risk if isinstance(risk, Mapping) else {}
    factors = safe.get("risk_factors")
    safe_factors = [factor for factor in factors if isinstance(factor, Mapping)] if isinstance(factors, list) else []
    expected_factors = sorted(
        safe_factors,
        key=lambda item: (_first_nonempty(item.get("factor")), int(item.get("score") or 0)),
    )
    expected_score = sum(int(item.get("score") or 0) for item in safe_factors)
    deterministic_ok = safe_factors == expected_factors and int(safe.get("risk_score") or 0) == expected_score
    core = {
        "transaction_id": _first_nonempty(safe.get("transaction_id")),
        "risk_level": _first_nonempty(safe.get("risk_level")),
        "risk_score": int(safe.get("risk_score") or 0),
        "risk_factors": freeze_runtime_export(safe_factors),
        "mitigation_notes": freeze_runtime_export(safe.get("mitigation_notes", [])),
    }
    digest_ok = _first_nonempty(safe.get("risk_digest")) == _immutable_digest(core)
    issues: List[str] = []
    if not deterministic_ok:
        issues.append("risk_not_deterministic")
    if not digest_ok:
        issues.append("risk_digest_mismatch")
    if _first_nonempty(safe.get("risk_level")) != _risk_level_for_score(int(safe.get("risk_score") or 0)):
        issues.append("risk_level_mismatch")
    return {
        "valid": not issues,
        "deterministic_ok": deterministic_ok and digest_ok,
        "issues": issues,
    }


def evaluate_runtime_repair_policy(
    transaction: Any,
    recommendation_draft: Any = None,
    risk_assessment: Any = None,
) -> Dict[str, Any]:
    """Evaluate deterministic read-only repair policy constraints."""
    safe_transaction = transaction if isinstance(transaction, Mapping) else {}
    safe_recommendation = recommendation_draft if isinstance(recommendation_draft, Mapping) else {}
    safe_risk = risk_assessment if isinstance(risk_assessment, Mapping) else {}

    violated_policies = _runtime_repair_policy_violations(
        transaction=safe_transaction,
        recommendation_draft=safe_recommendation,
        risk_assessment=safe_risk,
    )
    warnings = _runtime_repair_policy_warnings(
        transaction=safe_transaction,
        recommendation_draft=safe_recommendation,
        risk_assessment=safe_risk,
    )
    policy_result = _runtime_repair_policy_result(
        violated_policies=violated_policies,
        warnings=warnings,
    )
    enforcement_state = _runtime_repair_policy_enforcement_state(policy_result)
    core = {
        "transaction_id": _first_nonempty(safe_transaction.get("transaction_id")),
        "policy_result": policy_result,
        "violated_policies": violated_policies,
        "warnings": warnings,
        "enforcement_state": enforcement_state,
    }
    policy_digest = _immutable_digest(core)
    return {
        "policy_eval_id": f"repair_policy_eval_{policy_digest[:16]}",
        **core,
        "evaluated_at": _utc_timestamp(),
        "policy_digest": policy_digest,
    }


def validate_runtime_repair_policy_evaluation(eval: Any) -> Dict[str, Any]:
    safe = eval if isinstance(eval, Mapping) else {}
    violated_policies = _string_list(safe.get("violated_policies"), fallback=[])
    warnings = _string_list(safe.get("warnings"), fallback=[])
    expected_violated = sorted(_unique(violated_policies))
    expected_warnings = sorted(_unique(warnings))
    ordering_ok = violated_policies == expected_violated and warnings == expected_warnings
    expected_result = _runtime_repair_policy_result(
        violated_policies=expected_violated,
        warnings=expected_warnings,
    )
    expected_enforcement = _runtime_repair_policy_enforcement_state(expected_result)
    result_ok = _first_nonempty(safe.get("policy_result")) == expected_result
    enforcement_ok = _first_nonempty(safe.get("enforcement_state")) == expected_enforcement
    core = {
        "transaction_id": _first_nonempty(safe.get("transaction_id")),
        "policy_result": _first_nonempty(safe.get("policy_result")),
        "violated_policies": violated_policies,
        "warnings": warnings,
        "enforcement_state": _first_nonempty(safe.get("enforcement_state")),
    }
    expected_digest = _immutable_digest(core)
    digest_ok = _first_nonempty(safe.get("policy_digest")) == expected_digest
    eval_id_ok = _first_nonempty(safe.get("policy_eval_id")) == f"repair_policy_eval_{expected_digest[:16]}"

    issues: List[str] = []
    if not ordering_ok:
        issues.append("policy_ordering_not_deterministic")
    if not result_ok:
        issues.append("policy_result_mismatch")
    if not enforcement_ok:
        issues.append("enforcement_state_mismatch")
    if not digest_ok:
        issues.append("policy_digest_mismatch")
    if not eval_id_ok:
        issues.append("policy_eval_id_mismatch")
    if not _first_nonempty(safe.get("evaluated_at")):
        issues.append("evaluated_at_missing")

    deterministic_ok = ordering_ok and result_ok and enforcement_ok and digest_ok and eval_id_ok
    return {
        "valid": not issues,
        "deterministic_ok": deterministic_ok,
        "issues": issues,
    }


def build_runtime_repair_governance_report(
    transaction: Any,
    recommendation_draft: Any,
    recommendation_review: Any,
    recommendation_provenance: Any,
    risk_assessment: Any,
    decision_trace: Any,
    policy_evaluation: Any,
) -> Dict[str, Any]:
    """Build a deterministic read-only governance report for repair review."""
    safe_transaction = transaction if isinstance(transaction, Mapping) else {}
    safe_draft = recommendation_draft if isinstance(recommendation_draft, Mapping) else {}
    safe_review = recommendation_review if isinstance(recommendation_review, Mapping) else {}
    safe_provenance = recommendation_provenance if isinstance(recommendation_provenance, Mapping) else {}
    safe_risk = risk_assessment if isinstance(risk_assessment, Mapping) else {}
    safe_trace = decision_trace if isinstance(decision_trace, Mapping) else {}
    safe_policy = policy_evaluation if isinstance(policy_evaluation, Mapping) else {}

    recommendation_summary = _governance_recommendation_summary(safe_draft, safe_review)
    risk_summary = _governance_risk_summary(safe_risk)
    policy_summary = _governance_policy_summary(safe_policy)
    reasoning_summary = _governance_reasoning_summary(safe_trace)
    provenance_summary = _governance_provenance_summary(safe_provenance)
    governance_state = _governance_state(
        recommendation_review=safe_review,
        risk_assessment=safe_risk,
        policy_evaluation=safe_policy,
    )
    enforcement_state = _governance_enforcement_state(governance_state, safe_policy)
    core = {
        "transaction_id": _first_nonempty(safe_transaction.get("transaction_id")),
        "governance_state": governance_state,
        "recommendation_summary": recommendation_summary,
        "risk_summary": risk_summary,
        "policy_summary": policy_summary,
        "reasoning_summary": reasoning_summary,
        "provenance_summary": provenance_summary,
        "enforcement_state": enforcement_state,
    }
    report_digest = _immutable_digest(core)
    return {
        "report_id": f"repair_governance_report_{report_digest[:16]}",
        **core,
        "report_digest": report_digest,
        "created_at": _utc_timestamp(),
    }


def validate_runtime_repair_governance_report(report: Any) -> Dict[str, Any]:
    safe = report if isinstance(report, Mapping) else {}
    recommendation_summary = safe.get("recommendation_summary") if isinstance(safe.get("recommendation_summary"), Mapping) else {}
    risk_summary = safe.get("risk_summary") if isinstance(safe.get("risk_summary"), Mapping) else {}
    policy_summary = safe.get("policy_summary") if isinstance(safe.get("policy_summary"), Mapping) else {}
    reasoning_summary = safe.get("reasoning_summary") if isinstance(safe.get("reasoning_summary"), Mapping) else {}
    provenance_summary = safe.get("provenance_summary") if isinstance(safe.get("provenance_summary"), Mapping) else {}

    summary_order_ok = (
        _governance_top_candidates_ordered(recommendation_summary.get("top_candidates"))
        and _governance_factor_list_ordered(risk_summary.get("risk_factors"))
        and _string_list(policy_summary.get("violated_policies"), fallback=[]) == sorted(_string_list(policy_summary.get("violated_policies"), fallback=[]))
        and _string_list(policy_summary.get("warnings"), fallback=[]) == sorted(_string_list(policy_summary.get("warnings"), fallback=[]))
        and _governance_reasoning_steps_ordered(reasoning_summary.get("reasoning_steps"))
    )
    expected_governance = _governance_state_from_report(
        recommendation_summary=recommendation_summary,
        risk_summary=risk_summary,
        policy_summary=policy_summary,
    )
    governance_ok = _first_nonempty(safe.get("governance_state")) == expected_governance
    expected_enforcement = _governance_enforcement_state_from_report(
        governance_state=expected_governance,
        policy_summary=policy_summary,
    )
    enforcement_ok = _first_nonempty(safe.get("enforcement_state")) == expected_enforcement
    core = {
        "transaction_id": _first_nonempty(safe.get("transaction_id")),
        "governance_state": _first_nonempty(safe.get("governance_state")),
        "recommendation_summary": freeze_runtime_export(recommendation_summary),
        "risk_summary": freeze_runtime_export(risk_summary),
        "policy_summary": freeze_runtime_export(policy_summary),
        "reasoning_summary": freeze_runtime_export(reasoning_summary),
        "provenance_summary": freeze_runtime_export(provenance_summary),
        "enforcement_state": _first_nonempty(safe.get("enforcement_state")),
    }
    expected_digest = _immutable_digest(core)
    digest_ok = _first_nonempty(safe.get("report_digest")) == expected_digest
    report_id_ok = _first_nonempty(safe.get("report_id")) == f"repair_governance_report_{expected_digest[:16]}"

    issues: List[str] = []
    if not summary_order_ok:
        issues.append("summary_ordering_not_deterministic")
    if not governance_ok:
        issues.append("governance_state_mismatch")
    if not enforcement_ok:
        issues.append("enforcement_state_mismatch")
    if not digest_ok:
        issues.append("report_digest_mismatch")
    if not report_id_ok:
        issues.append("report_id_mismatch")
    if not _first_nonempty(safe.get("created_at")):
        issues.append("created_at_missing")

    deterministic_ok = summary_order_ok and governance_ok and enforcement_ok and digest_ok and report_id_ok
    return {
        "valid": not issues,
        "deterministic_ok": deterministic_ok,
        "issues": issues,
    }


def build_runtime_repair_decision_trace(
    transaction: Any,
    retrieval_result: Any,
    explanations: Any,
    recommendation_draft: Any,
    risk_assessment: Any,
) -> Dict[str, Any]:
    """Build a read-only deterministic trace for repair decision inputs.

    The trace records the derivation sources for retrieval, explanation,
    recommendation, and risk. It does not mutate the transaction, apply a
    repair, execute commands, or connect to scheduler auto decisions.
    """
    safe_transaction = transaction if isinstance(transaction, Mapping) else {}
    safe_retrieval = retrieval_result if isinstance(retrieval_result, Mapping) else {}
    safe_explanations = explanations if isinstance(explanations, Mapping) else {}
    safe_recommendation = recommendation_draft if isinstance(recommendation_draft, Mapping) else {}
    safe_risk = risk_assessment if isinstance(risk_assessment, Mapping) else {}

    retrieval_refs = _decision_trace_retrieval_refs(safe_retrieval)
    explanation_refs = _decision_trace_explanation_refs(safe_explanations)
    recommendation_ref = _decision_trace_recommendation_ref(safe_recommendation)
    risk_ref = _decision_trace_risk_ref(safe_risk)
    reasoning_steps = _decision_trace_reasoning_steps(
        retrieval_result=safe_retrieval,
        explanations=safe_explanations,
        recommendation_draft=safe_recommendation,
        risk_assessment=safe_risk,
    )
    final_decision_state = _decision_trace_final_state(
        recommendation_draft=safe_recommendation,
        risk_assessment=safe_risk,
    )
    core = {
        "transaction_id": _first_nonempty(safe_transaction.get("transaction_id")),
        "retrieval_refs": retrieval_refs,
        "explanation_refs": explanation_refs,
        "recommendation_ref": recommendation_ref,
        "risk_ref": risk_ref,
        "reasoning_steps": reasoning_steps,
        "final_decision_state": final_decision_state,
    }
    trace_digest = _immutable_digest(core)
    return {
        "trace_id": f"repair_decision_trace_{trace_digest[:16]}",
        **core,
        "trace_digest": trace_digest,
        "created_at": _utc_timestamp(),
    }


def validate_runtime_repair_decision_trace(trace: Any) -> Dict[str, Any]:
    safe = trace if isinstance(trace, Mapping) else {}
    reasoning_steps = safe.get("reasoning_steps")
    safe_steps = [step for step in reasoning_steps if isinstance(step, Mapping)] if isinstance(reasoning_steps, list) else []
    expected_step_keys = [
        "retrieval_matched_patterns",
        "candidate_ranking",
        "explanation_summary",
        "confidence_summary",
        "risk_factors",
        "mitigation_notes",
    ]
    actual_step_keys = [_first_nonempty(step.get("step_key")) for step in safe_steps]
    ordering_ok = actual_step_keys == expected_step_keys

    recommendation_ref = safe.get("recommendation_ref") if isinstance(safe.get("recommendation_ref"), Mapping) else {}
    risk_ref = safe.get("risk_ref") if isinstance(safe.get("risk_ref"), Mapping) else {}
    expected_state = _decision_trace_final_state(
        recommendation_draft=recommendation_ref,
        risk_assessment=risk_ref,
    )
    state_ok = _first_nonempty(safe.get("final_decision_state")) == expected_state
    core = {
        "transaction_id": _first_nonempty(safe.get("transaction_id")),
        "retrieval_refs": freeze_runtime_export(safe.get("retrieval_refs", {})),
        "explanation_refs": freeze_runtime_export(safe.get("explanation_refs", [])),
        "recommendation_ref": freeze_runtime_export(recommendation_ref),
        "risk_ref": freeze_runtime_export(risk_ref),
        "reasoning_steps": freeze_runtime_export(safe_steps),
        "final_decision_state": _first_nonempty(safe.get("final_decision_state")),
    }
    expected_digest = _immutable_digest(core)
    digest_ok = _first_nonempty(safe.get("trace_digest")) == expected_digest
    trace_id_ok = _first_nonempty(safe.get("trace_id")) == f"repair_decision_trace_{expected_digest[:16]}"

    issues: List[str] = []
    if not ordering_ok:
        issues.append("reasoning_order_not_deterministic")
    if not state_ok:
        issues.append("final_decision_state_mismatch")
    if not digest_ok:
        issues.append("trace_digest_mismatch")
    if not trace_id_ok:
        issues.append("trace_id_mismatch")
    if not _first_nonempty(safe.get("created_at")):
        issues.append("created_at_missing")

    deterministic_ok = ordering_ok and state_ok and digest_ok and trace_id_ok
    return {
        "valid": not issues,
        "deterministic_ok": deterministic_ok,
        "issues": issues,
    }


def _build_transaction_id(
    *,
    task_id: str,
    proposal_id: str,
    target_path: str,
    diff_text: str,
) -> str:
    seed = "|".join([task_id, proposal_id, target_path, _sha256(diff_text)])
    digest = hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"repair_tx_{digest}"


def _build_commit_token_id(*, transaction_id: str, approved_by: str, issued_unix: float) -> str:
    seed = "|".join([transaction_id, approved_by, f"{issued_unix:.6f}"])
    digest = hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"repair_commit_token_{digest}"


def _build_review_id(review_result: Mapping[str, Any]) -> str:
    seed = "|".join([
        _first_nonempty(review_result.get("transaction_id")),
        _first_nonempty(review_result.get("review_status")),
        _first_nonempty(review_result.get("approved_by")),
        _first_nonempty(review_result.get("approved_at")),
    ])
    digest = hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"repair_review_{digest}"


def _build_commit_intent_id(*, immutable_fields: Mapping[str, Any]) -> str:
    digest = _immutable_digest(immutable_fields)[:16]
    return f"repair_commit_intent_{digest}"


def _build_commit_session_id(*, intent_id: str, token_id: str, lease_started_unix: float) -> str:
    seed = "|".join([intent_id, token_id, f"{lease_started_unix:.6f}"])
    digest = hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"repair_commit_session_{digest}"


def _commit_consistency_digest(
    *,
    transaction_id: str,
    changed_files: Any,
    diff_summary: Any,
    token_id: str,
    intent_id: str,
    session_id: str,
) -> str:
    return _immutable_digest(
        {
            "transaction_id": transaction_id,
            "changed_files": changed_files,
            "diff_summary": diff_summary,
            "token_id": token_id,
            "intent_id": intent_id,
            "session_id": session_id,
        }
    )


def _build_temp_commit_id(*, transaction_id: str, session_id: str, committed_files: Any) -> str:
    digest = _immutable_digest(
        {
            "transaction_id": transaction_id,
            "session_id": session_id,
            "committed_files": committed_files,
        }
    )[:16]
    return f"repair_temp_commit_{digest}"


def _build_commit_artifact_id(*, core_fields: Mapping[str, Any]) -> str:
    return f"repair_commit_artifact_{_immutable_digest(core_fields)[:16]}"


def _build_replay_id(*, artifact_id: str, replay_digest: str) -> str:
    return f"repair_replay_{_immutable_digest({'artifact_id': artifact_id, 'replay_digest': replay_digest})[:16]}"


def _build_lineage_id(*, immutable_fields: Mapping[str, Any]) -> str:
    return f"repair_lineage_{_immutable_digest(immutable_fields)[:16]}"


def _replay_digest(*, changed_files: Any, diff_summary: Any, rollback_performed: bool) -> str:
    return _immutable_digest(
        {
            "changed_files": _sorted_changed_files(changed_files),
            "diff_summary": freeze_runtime_export(diff_summary),
            "rollback_performed": bool(rollback_performed),
        }
    )


def _diff_summary_from_changed_files(
    *,
    changed_files: List[Any],
    failures: int,
    rollback: bool,
) -> Dict[str, Any]:
    return {
        "total_files_changed": len(changed_files),
        "writes": sum(1 for item in changed_files if isinstance(item, Mapping) and item.get("operation_type") == "write_file"),
        "patches": sum(1 for item in changed_files if isinstance(item, Mapping) and item.get("operation_type") == "patch_file"),
        "deletes": sum(1 for item in changed_files if isinstance(item, Mapping) and item.get("operation_type") == "delete_file"),
        "failures": int(failures),
        "rollback": bool(rollback),
    }


def _lineage_path_for_node(node: Mapping[str, Any], node_by_artifact: Mapping[str, Mapping[str, Any]]) -> List[str]:
    path: List[str] = []
    seen = set()
    current = node
    while isinstance(current, Mapping):
        artifact_id = _first_nonempty(current.get("artifact_id"))
        if not artifact_id or artifact_id in seen:
            break
        seen.add(artifact_id)
        path.append(artifact_id)
        parent_id = _first_nonempty(current.get("parent_artifact_id"))
        if not parent_id:
            break
        current = node_by_artifact.get(parent_id, {})
    return list(reversed(path))


def _lineage_cycle_detected(node_by_artifact: Mapping[str, Mapping[str, Any]]) -> bool:
    for artifact_id in node_by_artifact:
        seen = set()
        current_id = artifact_id
        while current_id:
            if current_id in seen:
                return True
            seen.add(current_id)
            current = node_by_artifact.get(current_id)
            if not isinstance(current, Mapping):
                break
            current_id = _first_nonempty(current.get("parent_artifact_id"))
    return False


def _lineage_node_immutable_ok(node: Mapping[str, Any]) -> bool:
    immutable_fields = node.get("immutable_fields")
    if not isinstance(immutable_fields, Mapping):
        return False
    for field in ("artifact_id", "parent_artifact_id", "root_artifact_id", "lineage_depth", "lineage_type"):
        if freeze_runtime_export(node.get(field)) != freeze_runtime_export(immutable_fields.get(field)):
            return False
    return _first_nonempty(node.get("immutable_digest")) == _immutable_digest(immutable_fields)


def _lineage_replay_ancestry_ok(node: Mapping[str, Any], node_by_artifact: Mapping[str, Mapping[str, Any]]) -> bool:
    parent_id = _first_nonempty(node.get("parent_artifact_id"))
    parent = node_by_artifact.get(parent_id)
    if not isinstance(parent, Mapping):
        return False
    return _first_nonempty(node.get("root_artifact_id")) == _first_nonempty(parent.get("root_artifact_id"), parent.get("artifact_id"))


def _knowledge_operation_patterns(*, changed_files: List[Any], diff_summary: Mapping[Any, Any]) -> Dict[str, Any]:
    total = max(1, len(changed_files))
    writes = int(diff_summary.get("writes") or 0)
    patches = int(diff_summary.get("patches") or 0)
    deletes = int(diff_summary.get("deletes") or 0)
    return {
        "operation_count": writes + patches + deletes,
        "file_count": len(changed_files),
        "write_ratio": writes / total,
        "patch_ratio": patches / total,
        "delete_ratio": deletes / total,
    }


def _knowledge_repair_patterns(
    *,
    diff_summary: Mapping[Any, Any],
    rollback_patterns: Mapping[str, Any],
    replay_consistency: str,
) -> List[str]:
    writes = int(diff_summary.get("writes") or 0)
    patches = int(diff_summary.get("patches") or 0)
    deletes = int(diff_summary.get("deletes") or 0)
    patterns: List[str] = []
    if writes >= patches and writes >= deletes and writes > 0:
        patterns.append("write dominant")
    if patches > writes and patches >= deletes:
        patterns.append("patch dominant")
    if deletes > 0:
        patterns.append("delete involved")
    if bool(rollback_patterns.get("rollback_occurred", False)):
        patterns.append("rollback triggered")
    if replay_consistency == "stable":
        patterns.append("replay stable")
    return patterns


def _changed_file_types(changed_files: List[Any]) -> List[str]:
    file_types: List[str] = []
    for item in changed_files:
        if not isinstance(item, Mapping):
            continue
        suffix = Path(_first_nonempty(item.get("target_path"))).suffix.lower()
        file_types.append(suffix if suffix else "[no_extension]")
    return sorted(_unique(file_types))


def _knowledge_index_entry(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    operation_patterns = snapshot.get("operation_patterns")
    if not isinstance(operation_patterns, Mapping):
        operation_patterns = {}
    return {
        "knowledge_id": _first_nonempty(snapshot.get("knowledge_id")),
        "artifact_id": _first_nonempty(snapshot.get("artifact_id")),
        "lineage_id": _first_nonempty(snapshot.get("lineage_id")),
        "root_lineage_id": _first_nonempty(snapshot.get("root_lineage_id"), snapshot.get("lineage_id")),
        "repair_patterns": sorted(_string_list(snapshot.get("repair_patterns"), fallback=[])),
        "operation_type_ratios": {
            "write_file": float(operation_patterns.get("write_ratio") or 0),
            "patch_file": float(operation_patterns.get("patch_ratio") or 0),
            "delete_file": float(operation_patterns.get("delete_ratio") or 0),
        },
        "changed_file_types": sorted(_string_list(snapshot.get("changed_file_types"), fallback=[])),
        "replay_consistency": _first_nonempty(snapshot.get("replay_consistency")),
    }


def _sorted_index_map(index_map: Mapping[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    return {
        key: sorted(
            [freeze_runtime_export(item) for item in index_map[key]],
            key=lambda item: (_first_nonempty(item.get("artifact_id")), _first_nonempty(item.get("lineage_id")), _first_nonempty(item.get("knowledge_id"))),
        )
        for key in sorted(index_map)
    }


def _knowledge_entry_matches(entry: Mapping[str, Any], query: Mapping[str, Any]) -> bool:
    repair_pattern = _first_nonempty(query.get("repair_pattern"))
    if repair_pattern and repair_pattern not in entry.get("repair_patterns", []):
        return False

    operation_type = _first_nonempty(query.get("operation_type"))
    operation_type_ratios = entry.get("operation_type_ratios")
    if operation_type:
        if not isinstance(operation_type_ratios, Mapping) or float(operation_type_ratios.get(operation_type) or 0) <= 0:
            return False

    file_type = _first_nonempty(query.get("file_type"))
    if file_type and file_type not in entry.get("changed_file_types", []):
        return False

    replay_consistency = _first_nonempty(query.get("replay_consistency"))
    if replay_consistency and replay_consistency != _first_nonempty(entry.get("replay_consistency")):
        return False

    artifact_id = _first_nonempty(query.get("artifact_id"))
    if artifact_id and artifact_id != _first_nonempty(entry.get("artifact_id")):
        return False

    lineage_id = _first_nonempty(query.get("lineage_id"))
    if lineage_id and lineage_id != _first_nonempty(entry.get("lineage_id")):
        return False

    return True


def _changed_files_from_operations(operations: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    changed_files: List[Dict[str, Any]] = []
    for operation in operations:
        target_path = _normalize_display_path(operation.get("target_path"))
        if not target_path:
            continue
        op_type = _first_nonempty(operation.get("op_type"))
        changed_files.append(
            {
                "target_path": target_path,
                "operation_type": op_type,
                "before_exists": op_type != "write_file",
                "after_exists": op_type != "delete_file",
                "content_changed": True,
            }
        )
    return _sorted_changed_files(changed_files)


def _diff_summary_from_operations(operations: List[Mapping[str, Any]]) -> Dict[str, Any]:
    writes = sum(1 for operation in operations if _first_nonempty(operation.get("op_type")) == "write_file")
    patches = sum(1 for operation in operations if _first_nonempty(operation.get("op_type")) == "patch_file")
    deletes = sum(1 for operation in operations if _first_nonempty(operation.get("op_type")) == "delete_file")
    failures = sum(1 for operation in operations if _first_nonempty(operation.get("op_type")) == "command")
    return {
        "total_files_changed": writes + patches + deletes,
        "writes": writes,
        "patches": patches,
        "deletes": deletes,
        "failures": failures,
        "rollback": failures > 0,
    }


def _score_similarity_candidate(entry: Mapping[str, Any], query: Mapping[str, Any]) -> Dict[str, Any]:
    score = 0
    entry_patterns = set(_string_list(entry.get("repair_patterns"), fallback=[]))
    query_patterns = set(_string_list(query.get("repair_patterns"), fallback=[]))
    score += 3 * len(entry_patterns.intersection(query_patterns))

    operation_type_ratios = entry.get("operation_type_ratios")
    entry_operation_types = {
        op_type
        for op_type, ratio in operation_type_ratios.items()
        if isinstance(operation_type_ratios, Mapping) and float(ratio or 0) > 0
    } if isinstance(operation_type_ratios, Mapping) else set()
    query_operation_patterns = query.get("operation_patterns")
    query_operation_types = set(_string_list(
        query_operation_patterns.get("operation_types") if isinstance(query_operation_patterns, Mapping) else [],
        fallback=[],
    ))
    score += 2 * len(entry_operation_types.intersection(query_operation_types))

    entry_file_types = set(_string_list(entry.get("changed_file_types"), fallback=[]))
    query_file_types = set(_string_list(query.get("file_types"), fallback=[]))
    score += len(entry_file_types.intersection(query_file_types))

    if _first_nonempty(entry.get("replay_consistency")) == _first_nonempty(query.get("replay_consistency")):
        score += 1

    entry_rollback = "rollback triggered" in entry_patterns
    query_rollback = "rollback triggered" in query_patterns
    if entry_rollback and query_rollback:
        score += 1

    return {
        "entry": freeze_runtime_export(entry),
        "score": score,
    }


def _candidate_explanation_summary(
    *,
    matched_patterns: List[str],
    matched_operation_types: List[str],
    matched_file_types: List[str],
    replay_consistency_match: bool,
    rollback_pattern_match: bool,
) -> List[str]:
    summary: List[str] = []
    if matched_patterns:
        summary.append("matched repair pattern")
    if matched_operation_types:
        summary.append("matched operation type")
    if matched_file_types:
        summary.append("matched file type")
    if replay_consistency_match:
        summary.append("matched replay consistency")
    if rollback_pattern_match:
        summary.append("matched rollback behavior")
    return summary


def _recommendation_confidence(top_score: int) -> str:
    if top_score >= 6:
        return "high"
    if top_score >= 3:
        return "medium"
    return "low"


def _recommendation_limitations() -> List[str]:
    return [
        "read-only recommendation",
        "does not modify transaction",
        "requires human review before use",
    ]


def _recommendation_review_digest(review: Mapping[str, Any]) -> str:
    core = {
        "draft_id": _first_nonempty(review.get("draft_id")),
        "review_status": _first_nonempty(review.get("review_status")),
        "usable": bool(review.get("usable", False)),
        "approved_by": _first_nonempty(review.get("approved_by")),
        "note": _first_nonempty(review.get("note")),
        "rejected_by": _first_nonempty(review.get("rejected_by")),
        "reason": _first_nonempty(review.get("reason")),
    }
    return _immutable_digest(core)


def _recommendation_lineage_refs(candidates: List[Mapping[str, Any]]) -> Dict[str, List[str]]:
    lineage_ids = sorted(_unique([
        _first_nonempty(candidate.get("lineage_id"))
        for candidate in candidates
    ]))
    root_lineage_ids = sorted(_unique([
        _first_nonempty(candidate.get("root_lineage_id"), candidate.get("lineage_id"))
        for candidate in candidates
    ]))
    return {
        "candidate_lineage_ids": lineage_ids,
        "root_lineage_ids": root_lineage_ids,
    }


def _recommendation_replay_consistency_refs(candidates: List[Mapping[str, Any]]) -> Dict[str, Any]:
    stable_sources = sorted(_unique([
        _first_nonempty(candidate.get("artifact_id"))
        for candidate in candidates
        if _first_nonempty(candidate.get("replay_consistency")) == "stable"
    ]))
    unstable_sources = sorted(_unique([
        _first_nonempty(candidate.get("artifact_id"))
        for candidate in candidates
        if _first_nonempty(candidate.get("replay_consistency")) == "unstable"
    ]))
    rollback_sources = sorted(_unique([
        _first_nonempty(candidate.get("artifact_id"))
        for candidate in candidates
        if "rollback triggered" in _string_list(candidate.get("repair_patterns"), fallback=[])
    ]))
    return {
        "stable_sources": stable_sources,
        "unstable_sources": unstable_sources,
        "rollback_sources": rollback_sources,
    }


def _runtime_repair_policy_violations(
    *,
    transaction: Mapping[str, Any],
    recommendation_draft: Mapping[str, Any],
    risk_assessment: Mapping[str, Any],
) -> List[str]:
    policies: List[str] = []
    risk_level = _first_nonempty(risk_assessment.get("risk_level"))
    if risk_level == "critical" and _runtime_repair_policy_has_delete(transaction):
        policies.append("critical_delete_file_blocked")
    if risk_level == "high" and _runtime_repair_policy_has_unstable_replay(recommendation_draft, risk_assessment):
        policies.append("unstable_replay_high_risk_blocked")
    return sorted(_unique(policies))


def _runtime_repair_policy_warnings(
    *,
    transaction: Mapping[str, Any],
    recommendation_draft: Mapping[str, Any],
    risk_assessment: Mapping[str, Any],
) -> List[str]:
    warnings: List[str] = []
    risk_level = _first_nonempty(risk_assessment.get("risk_level"))
    risk_factors = _runtime_repair_policy_risk_factors(risk_assessment)
    if not _runtime_repair_policy_has_replay_verification(recommendation_draft, risk_assessment):
        warnings.append("missing_replay_verification")
    if risk_level in ("medium", "high") and "no_historical_match" in risk_factors:
        warnings.append("no_historical_match_medium_or_high_risk")
    if _transaction_has_rollback_history(transaction) and "patch_dominant" in risk_factors:
        warnings.append("rollback_history_patch_dominant")
    return sorted(_unique(warnings))


def _runtime_repair_policy_result(
    *,
    violated_policies: List[str],
    warnings: List[str],
) -> str:
    if violated_policies:
        return "blocked"
    if warnings:
        return "warning"
    return "allowed"


def _runtime_repair_policy_enforcement_state(policy_result: str) -> str:
    if policy_result == "blocked":
        return "execution_blocked"
    if policy_result == "warning":
        return "manual_review_required"
    return "advisory_only"


def _runtime_repair_policy_has_delete(transaction: Mapping[str, Any]) -> bool:
    operations = transaction.get("operations")
    safe_operations = [operation for operation in operations if isinstance(operation, Mapping)] if isinstance(operations, list) else []
    return any(_first_nonempty(operation.get("op_type")) == "delete_file" for operation in safe_operations)


def _runtime_repair_policy_has_unstable_replay(
    recommendation_draft: Mapping[str, Any],
    risk_assessment: Mapping[str, Any],
) -> bool:
    if "unstable_replay" in _runtime_repair_policy_risk_factors(risk_assessment):
        return True
    return "unstable" in _runtime_repair_policy_replay_values(recommendation_draft)


def _runtime_repair_policy_has_replay_verification(
    recommendation_draft: Mapping[str, Any],
    risk_assessment: Mapping[str, Any],
) -> bool:
    if "unstable_replay" in _runtime_repair_policy_risk_factors(risk_assessment):
        return True
    replay_values = _runtime_repair_policy_replay_values(recommendation_draft)
    return "stable" in replay_values or "unstable" in replay_values


def _runtime_repair_policy_replay_values(value: Any) -> List[str]:
    values: List[str] = []
    if not isinstance(value, Mapping):
        return values
    direct = _first_nonempty(value.get("replay_consistency"))
    if direct:
        values.append(direct)
    refs = value.get("replay_consistency_refs")
    if isinstance(refs, Mapping):
        if _string_list(refs.get("stable_sources"), fallback=[]):
            values.append("stable")
        if _string_list(refs.get("unstable_sources"), fallback=[]):
            values.append("unstable")
    candidates = value.get("recommended_candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, Mapping):
                replay = _first_nonempty(candidate.get("replay_consistency"))
                if replay:
                    values.append(replay)
    return sorted(_unique(values))


def _runtime_repair_policy_risk_factors(risk_assessment: Mapping[str, Any]) -> List[str]:
    factors = risk_assessment.get("risk_factors")
    safe_factors = [factor for factor in factors if isinstance(factor, Mapping)] if isinstance(factors, list) else []
    return sorted(_unique([
        _first_nonempty(factor.get("factor"))
        for factor in safe_factors
    ]))


def _governance_recommendation_summary(
    recommendation_draft: Mapping[str, Any],
    recommendation_review: Mapping[str, Any],
) -> Dict[str, Any]:
    candidates = recommendation_draft.get("recommended_candidates")
    safe_candidates = [candidate for candidate in candidates if isinstance(candidate, Mapping)] if isinstance(candidates, list) else []
    top_candidates = [
        {
            "artifact_id": _first_nonempty(candidate.get("artifact_id")),
            "knowledge_id": _first_nonempty(candidate.get("knowledge_id")),
            "similarity_score": int(candidate.get("similarity_score") or 0),
        }
        for candidate in safe_candidates
    ]
    return {
        "recommendation_id": _first_nonempty(
            recommendation_draft.get("draft_id"),
            recommendation_draft.get("recommendation_id"),
        ),
        "confidence_summary": _first_nonempty(recommendation_draft.get("confidence_summary")),
        "recommendation_status": _first_nonempty(recommendation_draft.get("recommendation_status")),
        "review_id": _first_nonempty(recommendation_review.get("review_id")),
        "review_status": _first_nonempty(recommendation_review.get("review_status")),
        "usable": bool(recommendation_review.get("usable", False) or recommendation_draft.get("usable", False)),
        "top_candidates": sorted(
            top_candidates,
            key=lambda item: (-item["similarity_score"], item["artifact_id"], item["knowledge_id"]),
        ),
    }


def _governance_risk_summary(risk_assessment: Mapping[str, Any]) -> Dict[str, Any]:
    factors = risk_assessment.get("risk_factors")
    safe_factors = [factor for factor in factors if isinstance(factor, Mapping)] if isinstance(factors, list) else []
    risk_factors = [
        {
            "factor": _first_nonempty(factor.get("factor")),
            "score": int(factor.get("score") or 0),
        }
        for factor in safe_factors
    ]
    return {
        "risk_id": _first_nonempty(risk_assessment.get("risk_id")),
        "risk_level": _first_nonempty(risk_assessment.get("risk_level")),
        "risk_score": int(risk_assessment.get("risk_score") or 0),
        "risk_factors": sorted(
            risk_factors,
            key=lambda item: (item["factor"], item["score"]),
        ),
    }


def _governance_policy_summary(policy_evaluation: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "policy_eval_id": _first_nonempty(policy_evaluation.get("policy_eval_id")),
        "policy_result": _first_nonempty(policy_evaluation.get("policy_result")),
        "violated_policies": sorted(_string_list(policy_evaluation.get("violated_policies"), fallback=[])),
        "warnings": sorted(_string_list(policy_evaluation.get("warnings"), fallback=[])),
        "enforcement_state": _first_nonempty(policy_evaluation.get("enforcement_state")),
    }


def _governance_reasoning_summary(decision_trace: Mapping[str, Any]) -> Dict[str, Any]:
    steps = decision_trace.get("reasoning_steps")
    safe_steps = [step for step in steps if isinstance(step, Mapping)] if isinstance(steps, list) else []
    reasoning_steps = [
        {
            "step_index": int(step.get("step_index") or 0),
            "step_key": _first_nonempty(step.get("step_key")),
            "summary": _first_nonempty(step.get("summary")),
        }
        for step in safe_steps
    ]
    return {
        "trace_id": _first_nonempty(decision_trace.get("trace_id")),
        "final_decision_state": _first_nonempty(decision_trace.get("final_decision_state")),
        "reasoning_steps": sorted(
            reasoning_steps,
            key=lambda item: (item["step_index"], item["step_key"]),
        ),
    }


def _governance_provenance_summary(recommendation_provenance: Mapping[str, Any]) -> Dict[str, Any]:
    lineage_refs = recommendation_provenance.get("lineage_refs")
    safe_lineage_refs = lineage_refs if isinstance(lineage_refs, Mapping) else {}
    replay_refs = recommendation_provenance.get("replay_consistency_refs")
    safe_replay_refs = replay_refs if isinstance(replay_refs, Mapping) else {}
    return {
        "provenance_id": _first_nonempty(recommendation_provenance.get("provenance_id")),
        "recommendation_id": _first_nonempty(recommendation_provenance.get("recommendation_id")),
        "retrieval_id": _first_nonempty(recommendation_provenance.get("retrieval_id")),
        "explanation_ids": sorted(_string_list(recommendation_provenance.get("explanation_ids"), fallback=[])),
        "candidate_artifact_ids": sorted(_string_list(recommendation_provenance.get("candidate_artifact_ids"), fallback=[])),
        "lineage_refs": {
            "candidate_lineage_ids": sorted(_string_list(safe_lineage_refs.get("candidate_lineage_ids"), fallback=[])),
            "root_lineage_ids": sorted(_string_list(safe_lineage_refs.get("root_lineage_ids"), fallback=[])),
        },
        "replay_consistency_refs": {
            "stable_sources": sorted(_string_list(safe_replay_refs.get("stable_sources"), fallback=[])),
            "unstable_sources": sorted(_string_list(safe_replay_refs.get("unstable_sources"), fallback=[])),
            "rollback_sources": sorted(_string_list(safe_replay_refs.get("rollback_sources"), fallback=[])),
        },
    }


def _governance_state(
    *,
    recommendation_review: Mapping[str, Any],
    risk_assessment: Mapping[str, Any],
    policy_evaluation: Mapping[str, Any],
) -> str:
    if _first_nonempty(policy_evaluation.get("policy_result")) == "blocked":
        return "execution_blocked"
    if _first_nonempty(risk_assessment.get("risk_level")) == "critical":
        return "high_risk_review"
    if (
        _decision_trace_recommendation_approved(recommendation_review)
        and _first_nonempty(policy_evaluation.get("policy_result")) == "warning"
    ):
        return "review_required"
    return "advisory_only"


def _governance_enforcement_state(
    governance_state: str,
    policy_evaluation: Mapping[str, Any],
) -> str:
    if governance_state == "execution_blocked":
        return "execution_blocked"
    policy_enforcement = _first_nonempty(policy_evaluation.get("enforcement_state"))
    if governance_state in ("review_required", "high_risk_review"):
        return "manual_review_required"
    return policy_enforcement or "advisory_only"


def _governance_state_from_report(
    *,
    recommendation_summary: Mapping[str, Any],
    risk_summary: Mapping[str, Any],
    policy_summary: Mapping[str, Any],
) -> str:
    if _first_nonempty(policy_summary.get("policy_result")) == "blocked":
        return "execution_blocked"
    if _first_nonempty(risk_summary.get("risk_level")) == "critical":
        return "high_risk_review"
    if (
        _decision_trace_recommendation_approved(recommendation_summary)
        and _first_nonempty(policy_summary.get("policy_result")) == "warning"
    ):
        return "review_required"
    return "advisory_only"


def _governance_enforcement_state_from_report(
    *,
    governance_state: str,
    policy_summary: Mapping[str, Any],
) -> str:
    if governance_state == "execution_blocked":
        return "execution_blocked"
    if governance_state in ("review_required", "high_risk_review"):
        return "manual_review_required"
    return _first_nonempty(policy_summary.get("enforcement_state"), "advisory_only")


def _governance_top_candidates_ordered(value: Any) -> bool:
    if not isinstance(value, list):
        return True
    safe = [item for item in value if isinstance(item, Mapping)]
    expected = sorted(
        safe,
        key=lambda item: (-int(item.get("similarity_score") or 0), _first_nonempty(item.get("artifact_id")), _first_nonempty(item.get("knowledge_id"))),
    )
    return safe == expected


def _governance_factor_list_ordered(value: Any) -> bool:
    if not isinstance(value, list):
        return True
    safe = [item for item in value if isinstance(item, Mapping)]
    expected = sorted(
        safe,
        key=lambda item: (_first_nonempty(item.get("factor")), int(item.get("score") or 0)),
    )
    return safe == expected


def _governance_reasoning_steps_ordered(value: Any) -> bool:
    if not isinstance(value, list):
        return True
    safe = [item for item in value if isinstance(item, Mapping)]
    expected = sorted(
        safe,
        key=lambda item: (int(item.get("step_index") or 0), _first_nonempty(item.get("step_key"))),
    )
    return safe == expected


def _decision_trace_retrieval_refs(retrieval_result: Mapping[str, Any]) -> Dict[str, Any]:
    ranked_matches = retrieval_result.get("ranked_matches")
    safe_matches = [match for match in ranked_matches if isinstance(match, Mapping)] if isinstance(ranked_matches, list) else []
    return {
        "retrieval_id": _first_nonempty(retrieval_result.get("retrieval_id")),
        "query_digest": _first_nonempty(retrieval_result.get("query_digest")),
        "candidate_artifact_ids": sorted(_unique([
            _first_nonempty(match.get("artifact_id"))
            for match in safe_matches
        ])),
        "ranked_candidate_count": len(safe_matches),
        "similarity_scores": freeze_runtime_export(retrieval_result.get("similarity_scores", {})),
    }


def _decision_trace_explanation_refs(explanations: Mapping[str, Any]) -> List[Dict[str, Any]]:
    items = explanations.get("explanations")
    safe_items = [item for item in items if isinstance(item, Mapping)] if isinstance(items, list) else []
    refs = [
        {
            "candidate_id": _first_nonempty(item.get("candidate_id")),
            "explanation_id": _first_nonempty(item.get("explanation_id")),
            "explanation_digest": _first_nonempty(item.get("explanation_digest")),
        }
        for item in safe_items
    ]
    return sorted(
        refs,
        key=lambda item: (item["candidate_id"], item["explanation_id"], item["explanation_digest"]),
    )


def _decision_trace_recommendation_ref(recommendation_draft: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "recommendation_id": _first_nonempty(
            recommendation_draft.get("draft_id"),
            recommendation_draft.get("recommendation_id"),
        ),
        "recommendation_status": _first_nonempty(recommendation_draft.get("recommendation_status")),
        "review_status": _first_nonempty(recommendation_draft.get("review_status")),
        "usable": bool(recommendation_draft.get("usable", False)),
        "confidence_summary": _first_nonempty(recommendation_draft.get("confidence_summary")),
        "recommended_candidates": freeze_runtime_export(recommendation_draft.get("recommended_candidates", [])),
        "draft_digest": _first_nonempty(recommendation_draft.get("draft_digest")),
    }


def _decision_trace_risk_ref(risk_assessment: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "risk_id": _first_nonempty(risk_assessment.get("risk_id")),
        "risk_level": _first_nonempty(risk_assessment.get("risk_level")),
        "risk_score": int(risk_assessment.get("risk_score") or 0),
        "risk_factors": freeze_runtime_export(risk_assessment.get("risk_factors", [])),
        "mitigation_notes": freeze_runtime_export(risk_assessment.get("mitigation_notes", [])),
        "risk_digest": _first_nonempty(risk_assessment.get("risk_digest")),
    }


def _decision_trace_reasoning_steps(
    *,
    retrieval_result: Mapping[str, Any],
    explanations: Mapping[str, Any],
    recommendation_draft: Mapping[str, Any],
    risk_assessment: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    return [
        {
            "step_index": 1,
            "step_key": "retrieval_matched_patterns",
            "summary": "retrieval matched patterns",
            "details": _decision_trace_matched_patterns(retrieval_result),
        },
        {
            "step_index": 2,
            "step_key": "candidate_ranking",
            "summary": "candidate ranking",
            "details": _decision_trace_candidate_ranking(retrieval_result),
        },
        {
            "step_index": 3,
            "step_key": "explanation_summary",
            "summary": "explanation summary",
            "details": _decision_trace_explanation_summary(explanations),
        },
        {
            "step_index": 4,
            "step_key": "confidence_summary",
            "summary": "confidence summary",
            "details": {
                "confidence_summary": _first_nonempty(recommendation_draft.get("confidence_summary")),
                "recommended_candidate_count": len(recommendation_draft.get("recommended_candidates") if isinstance(recommendation_draft.get("recommended_candidates"), list) else []),
            },
        },
        {
            "step_index": 5,
            "step_key": "risk_factors",
            "summary": "risk factors",
            "details": sorted(
                [
                    freeze_runtime_export(item)
                    for item in risk_assessment.get("risk_factors", [])
                    if isinstance(item, Mapping)
                ],
                key=lambda item: (_first_nonempty(item.get("factor")), int(item.get("score") or 0)),
            ) if isinstance(risk_assessment.get("risk_factors"), list) else [],
        },
        {
            "step_index": 6,
            "step_key": "mitigation_notes",
            "summary": "mitigation notes",
            "details": sorted(_string_list(risk_assessment.get("mitigation_notes"), fallback=[])),
        },
    ]


def _decision_trace_matched_patterns(retrieval_result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    ranked_matches = retrieval_result.get("ranked_matches")
    safe_matches = [match for match in ranked_matches if isinstance(match, Mapping)] if isinstance(ranked_matches, list) else []
    details = [
        {
            "artifact_id": _first_nonempty(match.get("artifact_id")),
            "repair_patterns": sorted(_string_list(match.get("repair_patterns"), fallback=[])),
            "replay_consistency": _first_nonempty(match.get("replay_consistency")),
        }
        for match in safe_matches
    ]
    return sorted(
        details,
        key=lambda item: (item["artifact_id"], item["replay_consistency"]),
    )


def _decision_trace_candidate_ranking(retrieval_result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    ranked_matches = retrieval_result.get("ranked_matches")
    safe_matches = [match for match in ranked_matches if isinstance(match, Mapping)] if isinstance(ranked_matches, list) else []
    scores = retrieval_result.get("similarity_scores")
    safe_scores = scores if isinstance(scores, Mapping) else {}
    ranking = [
        {
            "rank": index + 1,
            "artifact_id": _first_nonempty(match.get("artifact_id")),
            "knowledge_id": _first_nonempty(match.get("knowledge_id")),
            "similarity_score": int(safe_scores.get(_first_nonempty(match.get("artifact_id"))) or 0),
        }
        for index, match in enumerate(safe_matches)
    ]
    return sorted(
        ranking,
        key=lambda item: (item["rank"], -item["similarity_score"], item["artifact_id"], item["knowledge_id"]),
    )


def _decision_trace_explanation_summary(explanations: Mapping[str, Any]) -> List[Dict[str, Any]]:
    items = explanations.get("explanations")
    safe_items = [item for item in items if isinstance(item, Mapping)] if isinstance(items, list) else []
    summaries = [
        {
            "candidate_id": _first_nonempty(item.get("candidate_id")),
            "explanation_id": _first_nonempty(item.get("explanation_id")),
            "summary": sorted(_string_list(item.get("explanation_summary"), fallback=[])),
            "similarity_score": int(item.get("similarity_score") or 0),
        }
        for item in safe_items
    ]
    return sorted(
        summaries,
        key=lambda item: (-item["similarity_score"], item["candidate_id"], item["explanation_id"]),
    )


def _decision_trace_final_state(
    *,
    recommendation_draft: Mapping[str, Any],
    risk_assessment: Mapping[str, Any],
) -> str:
    risk_level = _first_nonempty(risk_assessment.get("risk_level"))
    if risk_level == "critical":
        return "critical_risk"
    if risk_level == "high":
        return "high_risk"
    if risk_level in ("low", "medium") and _decision_trace_recommendation_approved(recommendation_draft):
        return "review_required"
    return "advisory_only"


def _decision_trace_recommendation_approved(recommendation_draft: Mapping[str, Any]) -> bool:
    return (
        _first_nonempty(recommendation_draft.get("review_status")) == "approved"
        or _first_nonempty(recommendation_draft.get("recommendation_status")) == "approved"
        or bool(recommendation_draft.get("usable", False))
    )


def _repair_risk_factors(
    *,
    transaction: Mapping[str, Any],
    recommendation_draft: Mapping[str, Any],
    retrieval_result: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    operations = transaction.get("operations")
    safe_operations = [operation for operation in operations if isinstance(operation, Mapping)] if isinstance(operations, list) else []
    factors: List[Dict[str, Any]] = []
    if any(_first_nonempty(operation.get("op_type")) == "delete_file" for operation in safe_operations):
        factors.append({"factor": "delete_file", "score": 4})

    if _transaction_has_rollback_history(transaction):
        factors.append({"factor": "rollback_history", "score": 3})

    ranked_matches = retrieval_result.get("ranked_matches")
    safe_matches = [match for match in ranked_matches if isinstance(match, Mapping)] if isinstance(ranked_matches, list) else []
    if any(_first_nonempty(match.get("replay_consistency")) == "unstable" for match in safe_matches):
        factors.append({"factor": "unstable_replay", "score": 3})

    file_count = len(_changed_files_from_operations(safe_operations))
    if file_count >= 3:
        factors.append({"factor": "high_file_count", "score": 2})

    patch_count = sum(1 for operation in safe_operations if _first_nonempty(operation.get("op_type")) == "patch_file")
    write_count = sum(1 for operation in safe_operations if _first_nonempty(operation.get("op_type")) == "write_file")
    delete_count = sum(1 for operation in safe_operations if _first_nonempty(operation.get("op_type")) == "delete_file")
    if patch_count > write_count and patch_count >= delete_count and patch_count > 0:
        factors.append({"factor": "patch_dominant", "score": 2})

    if _first_nonempty(recommendation_draft.get("confidence_summary")) == "low":
        factors.append({"factor": "low_similarity_confidence", "score": 2})

    if isinstance(ranked_matches, list) and not ranked_matches:
        factors.append({"factor": "no_historical_match", "score": 3})

    return sorted(factors, key=lambda item: (item["factor"], item["score"]))


def _transaction_has_rollback_history(transaction: Mapping[str, Any]) -> bool:
    if bool(transaction.get("rollback_performed", False)):
        return True
    history = transaction.get("repair_history")
    if isinstance(history, list):
        return any(isinstance(item, Mapping) and bool(item.get("rollback_performed", False)) for item in history)
    return False


def _risk_level_for_score(score: int) -> str:
    if score <= 2:
        return "low"
    if score <= 5:
        return "medium"
    if score <= 8:
        return "high"
    return "critical"


def _risk_mitigation_notes() -> List[str]:
    return [
        "requires manual review",
        "requires replay verification",
        "requires rollback validation",
    ]


def _sorted_changed_files(value: Any) -> List[Any]:
    if not isinstance(value, list):
        return []
    return sorted(
        [freeze_runtime_export(item) for item in value],
        key=lambda item: _first_nonempty(item.get("target_path")) if isinstance(item, Mapping) else str(item),
    )


def _artifact_public_snapshot(artifact: Mapping[str, Any]) -> Dict[str, Any]:
    fields = [
        "artifact_id",
        "transaction_id",
        "commit_id",
        "review_id",
        "token_id",
        "intent_id",
        "session_id",
        "consistency_digest",
        "changed_files",
        "diff_summary",
        "commit_success",
        "rollback_performed",
        "created_at",
        "immutable_digest",
    ]
    return {field: freeze_runtime_export(artifact.get(field)) for field in fields}


def _immutable_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8", errors="replace")).hexdigest()


def _intent_immutable_fields_ok(intent: Mapping[str, Any]) -> bool:
    immutable_fields = intent.get("immutable_fields")
    if not isinstance(immutable_fields, Mapping):
        return False
    for field in ("transaction_id", "token_id", "review_id", "changed_files", "diff_summary"):
        if freeze_runtime_export(intent.get(field)) != freeze_runtime_export(immutable_fields.get(field)):
            return False
    return _first_nonempty(intent.get("immutable_digest")) == _immutable_digest(immutable_fields)


def _sha256(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()


def _utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _unix_to_utc_timestamp(value: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value))


def _commit_token_expired(token: Mapping[str, Any]) -> bool:
    try:
        expires_at = float(token.get("expires_at_unix"))
    except (TypeError, ValueError):
        return True
    return time.time() >= expires_at


def _commit_session_expired(session: Mapping[str, Any]) -> bool:
    try:
        expires_at = float(session.get("lease_expires_at_unix"))
    except (TypeError, ValueError):
        return True
    return time.time() >= expires_at


def _resolve_boundary_root(value: Any) -> Path:
    root = Path(_first_nonempty(value, ".")).expanduser()
    return root.resolve()


def _resolve_allowed_boundaries(*, workspace_boundary: Path, allowed_roots: Any) -> List[Path]:
    if allowed_roots is None:
        return [workspace_boundary]

    roots = allowed_roots if isinstance(allowed_roots, list) else [allowed_roots]
    resolved: List[Path] = []
    for root in roots:
        root_text = _first_nonempty(root)
        if not root_text:
            continue
        candidate = Path(root_text).expanduser()
        if not candidate.is_absolute():
            candidate = workspace_boundary / candidate
        resolved_candidate = candidate.resolve()
        if _path_is_relative_to(resolved_candidate, workspace_boundary):
            resolved.append(resolved_candidate)
    return resolved or [workspace_boundary]


def _target_path_is_allowed(
    target_path: str,
    *,
    workspace_boundary: Path,
    allowed_boundaries: List[Path],
) -> bool:
    candidate = Path(target_path).expanduser()
    if not candidate.is_absolute():
        candidate = workspace_boundary / candidate
    resolved = candidate.resolve()
    if not _path_is_relative_to(resolved, workspace_boundary):
        return False
    return any(_path_is_relative_to(resolved, boundary) for boundary in allowed_boundaries)


def _path_is_relative_to(path: Path, boundary: Path) -> bool:
    try:
        path.relative_to(boundary)
    except ValueError:
        return False
    return True


def _operation_has_payload(operation: Mapping[str, Any]) -> bool:
    for key in ("content", "patch", "payload"):
        value = operation.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, (list, dict)) and value:
            return True
        if value not in (None, "", [], {}):
            return True
    return False


def _review_risk_level(*, changed_files: List[Any], diff_summary: Mapping[Any, Any]) -> str:
    if _diff_has_failure(diff_summary):
        return "blocked"
    if any(
        isinstance(item, Mapping) and _first_nonempty(item.get("operation_type")) == "delete_file"
        for item in changed_files
    ):
        return "high"

    changed_count = len(changed_files)
    if changed_count == 0:
        return "low"
    if changed_count <= 2:
        return "medium"
    return "high"


def _review_reasons(
    *,
    changed_files: List[Any],
    diff_summary: Mapping[Any, Any],
    preview_ready: bool,
    risk_level: str,
) -> List[str]:
    reasons: List[str] = []
    if not preview_ready:
        reasons.append("preview_not_ready")
    if _diff_has_failure(diff_summary):
        reasons.append("rollback_or_failure")
    if any(
        isinstance(item, Mapping) and _first_nonempty(item.get("operation_type")) == "delete_file"
        for item in changed_files
    ):
        reasons.append("delete_operation")
    if len(changed_files) >= 3:
        reasons.append("multi_file_change")
    if not changed_files:
        reasons.append("no_changed_files")
    reasons.append(f"risk:{risk_level}")
    return _unique(reasons)


def _diff_has_failure(diff_summary: Any) -> bool:
    summary = diff_summary if isinstance(diff_summary, Mapping) else {}
    return bool(summary.get("rollback", False)) or int(summary.get("failures") or 0) > 0


def _seed_sandbox_files(files_value: Any, *, sandbox_root: Path) -> None:
    if not isinstance(files_value, Mapping):
        return
    for path_value, content in files_value.items():
        target_path = _resolve_sandbox_target(path_value, sandbox_root=sandbox_root)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(str(content), encoding="utf-8")


def _snapshot_sandbox(sandbox_root: Path) -> Dict[str, Dict[str, Any]]:
    snapshot: Dict[str, Dict[str, Any]] = {}
    if not sandbox_root.exists():
        return snapshot
    for path in sorted(sandbox_root.rglob("*"), key=lambda item: item.relative_to(sandbox_root).as_posix()):
        if not path.is_file():
            continue
        relative_path = path.relative_to(sandbox_root).as_posix()
        content = path.read_bytes()
        snapshot[relative_path] = {
            "exists": True,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }
    return snapshot


def _operation_type_by_path(applied_operations: List[Any]) -> Dict[str, str]:
    operation_by_path: Dict[str, str] = {}
    for operation in applied_operations:
        if not isinstance(operation, Mapping):
            continue
        target_path = _normalize_display_path(operation.get("target_path"))
        op_type = _first_nonempty(operation.get("op_type"))
        if target_path and op_type:
            operation_by_path[target_path] = op_type
    return operation_by_path


def _changed_files_from_snapshots(
    *,
    before_snapshot: Mapping[Any, Any],
    after_snapshot: Mapping[Any, Any],
    operation_by_path: Mapping[str, str],
) -> List[Dict[str, Any]]:
    changed_paths = sorted(
        _unique([
            _normalize_display_path(path)
            for path in list(before_snapshot.keys()) + list(after_snapshot.keys())
            if _snapshot_entry_changed(before_snapshot.get(path), after_snapshot.get(path))
        ])
    )
    return [
        {
            "target_path": path,
            "operation_type": _first_nonempty(operation_by_path.get(path), _infer_operation_type(path, before_snapshot, after_snapshot)),
            "before_exists": path in before_snapshot,
            "after_exists": path in after_snapshot,
            "content_changed": _snapshot_entry_changed(before_snapshot.get(path), after_snapshot.get(path)),
        }
        for path in changed_paths
    ]


def _snapshot_entry_changed(before_entry: Any, after_entry: Any) -> bool:
    before = before_entry if isinstance(before_entry, Mapping) else None
    after = after_entry if isinstance(after_entry, Mapping) else None
    if before is None or after is None:
        return before is not after
    return _first_nonempty(before.get("sha256")) != _first_nonempty(after.get("sha256"))


def _infer_operation_type(path: str, before_snapshot: Mapping[Any, Any], after_snapshot: Mapping[Any, Any]) -> str:
    if path not in before_snapshot and path in after_snapshot:
        return "write_file"
    if path in before_snapshot and path not in after_snapshot:
        return "delete_file"
    return "patch_file"


def _commit_operation_results(
    *,
    applied_operations: List[Any],
    failed_operation: Optional[Mapping[str, Any]],
    rollback_applied: bool,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for operation in applied_operations:
        if not isinstance(operation, Mapping):
            continue
        op_type = _first_nonempty(operation.get("op_type"))
        results.append(
            {
                "operation_index": int(operation.get("index") or 0),
                "op_type": op_type,
                "target_path": _normalize_display_path(operation.get("target_path")),
                "success": True,
                "rollback_applied": rollback_applied,
                "summary": _operation_result_summary(op_type, success=True),
            }
        )
    if failed_operation is not None:
        op_type = _first_nonempty(failed_operation.get("op_type"))
        results.append(
            {
                "operation_index": failed_operation.get("index"),
                "op_type": op_type,
                "target_path": _normalize_display_path(failed_operation.get("target_path")),
                "success": False,
                "rollback_applied": rollback_applied,
                "summary": _first_nonempty(failed_operation.get("reason"), _operation_result_summary(op_type, success=False)),
            }
        )
    return sorted(results, key=lambda item: (-1 if item["operation_index"] is None else int(item["operation_index"])))


def _operation_result_summary(op_type: str, *, success: bool) -> str:
    if not success:
        return "operation failed"
    summaries = {
        "write_file": "wrote content in sandbox",
        "patch_file": "applied patch in sandbox",
        "delete_file": "deleted file in sandbox",
    }
    return summaries.get(op_type, "processed operation in sandbox")


def _apply_sandbox_operation(
    operation: Mapping[str, Any],
    *,
    index: int,
    sandbox_root: Path,
) -> Dict[str, Any]:
    op_type = _first_nonempty(operation.get("op_type"))
    target_path = _resolve_sandbox_target(
        operation.get("target_path"),
        sandbox_root=sandbox_root,
    )

    if op_type == "write_file":
        content = operation.get("content")
        if content is None:
            raise ValueError("content_missing")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(str(content), encoding="utf-8")
    elif op_type == "patch_file":
        patch_text = _first_nonempty(operation.get("patch"), operation.get("content"))
        if not patch_text:
            raise ValueError("patch_missing")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(_minimal_patch_result(patch_text), encoding="utf-8")
    elif op_type == "delete_file":
        if target_path.is_dir():
            shutil.rmtree(target_path)
        elif target_path.exists():
            target_path.unlink()
    else:
        raise ValueError(f"unsupported_operation:{op_type}")

    return {
        "index": index,
        "op_type": op_type,
        "target_path": _sandbox_relative_path(target_path, sandbox_root=sandbox_root),
    }


def _resolve_sandbox_target(path_value: Any, *, sandbox_root: Path) -> Path:
    path_text = _first_nonempty(path_value)
    if not path_text:
        raise ValueError("target_path_missing")

    candidate = Path(path_text).expanduser()
    if not candidate.is_absolute():
        candidate = sandbox_root / candidate
    resolved = candidate.resolve()
    if not _path_is_relative_to(resolved, sandbox_root):
        raise ValueError("unsafe_target_path")
    return resolved


def _sandbox_relative_path(path: Path, *, sandbox_root: Path) -> str:
    return path.relative_to(sandbox_root).as_posix()


def _minimal_patch_result(patch_text: str) -> str:
    lines: List[str] = []
    for line in str(patch_text).splitlines():
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            lines.append(line[1:])
        elif line.startswith(" ") or line.startswith("\t"):
            lines.append(line[1:])
    if not lines:
        raise ValueError("patch_has_no_content")
    return "\n".join(lines) + "\n"


def _copy_directory_state(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _restore_directory_state(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _operation_plan_summary(op_type: str) -> str:
    summaries = {
        "write_file": "would write content",
        "patch_file": "would apply patch",
        "delete_file": "would delete file",
        "command": "would execute command",
    }
    return summaries.get(op_type, "would process operation")


def _normalize_display_path(path_value: Any) -> str:
    path_text = _first_nonempty(path_value).replace("\\", "/")
    if not path_text:
        return ""

    prefix = ""
    if path_text.startswith("/"):
        prefix = "/"
        path_text = path_text.lstrip("/")

    parts: List[str] = []
    for part in path_text.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            if parts and parts[-1] != "..":
                parts.pop()
            else:
                parts.append(part)
            continue
        parts.append(part)

    normalized = "/".join(parts)
    return prefix + normalized if normalized else prefix


def _build_summary(
    *,
    status: str,
    transaction_id: str,
    target_path: str,
    blocked_reasons: List[str],
) -> str:
    if status == "staged":
        return (
            f"Repair apply transaction {transaction_id} is staged for {target_path}. "
            "No mutation has been applied; rollback snapshot is required before apply."
        )
    return "Repair apply transaction blocked: " + ", ".join(_unique(blocked_reasons))


def _string_list(value: Any, *, fallback: Optional[List[str]] = None) -> List[str]:
    if isinstance(value, list):
        return _unique([str(item).strip() for item in value if str(item or "").strip()])
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return list(fallback or [])


def _unique(values: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
