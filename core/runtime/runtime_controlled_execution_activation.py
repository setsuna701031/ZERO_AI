from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from core.runtime.runtime_executor_admission_token import issue_executor_admission_token


RUNTIME_CONTROLLED_EXECUTION_ACTIVATION_CONTRACT = "zero.runtime.controlled_execution_activation.v1"
_MAX_FILE_SIZE = 8 * 1024 * 1024


def _mapping(value: Any) -> dict[str, Any]: return deepcopy(dict(value)) if isinstance(value, Mapping) else {}
def _canonical(value: Any) -> str: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
def _fingerprint(value: Any) -> str: return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _reparse(path: Path) -> bool:
    try: return bool(getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError: return False


def _snapshot(root: Path, files: list[str], max_size: int) -> tuple[dict[str, Any], list[str]]:
    entries, blocked = [], []
    root_resolved = root.resolve(strict=True)
    for relative in files:
        candidate = root / relative
        reason, digest, size, exists, kind, readable = "", "", None, candidate.exists(), "missing", False
        try:
            current = root
            for part in Path(relative).parts:
                current = current / part
                if current.exists() and (current.is_symlink() or _reparse(current)):
                    reason = "symlink_or_reparse_point"; break
            resolved = candidate.resolve(strict=False)
            if os.path.commonpath([str(root_resolved), str(resolved)]) != str(root_resolved): reason = "path_outside_target_root"
            if not reason and exists:
                info = candidate.stat()
                if candidate.is_dir(): reason, kind = "directory_not_allowed", "directory"
                elif not candidate.is_file(): reason, kind = "non_regular_file", "unsupported"
                elif info.st_size > max_size: reason, kind, size = "file_too_large", "file", info.st_size
                else:
                    kind, size = "file", info.st_size
                    before = candidate.stat()
                    content = candidate.read_bytes()
                    after = candidate.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        reason = "unstable_file_during_snapshot"
                    else: digest = sha256(content).hexdigest(); readable = True
        except (OSError, RuntimeError, ValueError) as exc:
            reason = f"unreadable:{type(exc).__name__}"
        eligible = not reason
        if reason: blocked.append(f"snapshot:{relative}:{reason}")
        entries.append({"path": relative, "resolved_candidate_path": str(candidate.resolve(strict=False)),
                        "exists": exists, "file_type": kind, "size": size,
                        "content_hash_sha256": digest, "metadata_available": exists and not reason,
                        "read_status": "read" if readable else "missing" if not exists else "blocked",
                        "snapshot_eligible": eligible, "safety_status": "safe" if eligible else "blocked",
                        "reason": reason})
    manifest = {"contract": "zero.runtime.pre_execution_snapshot_manifest.v1",
                "manifest_id": f"snapshot-manifest-{_fingerprint(entries)[:16]}",
                "entries": entries, "all_paths_eligible": not blocked,
                "file_copies_created": False, "target_root_modified": False}
    return manifest, blocked


def activate_controlled_execution(execution_plan: Mapping[str, Any],
        execution_plan_review_result: Mapping[str, Any],
        operator_execution_request: Mapping[str, Any], *, target_root: Any,
        now: Any = None, runtime_config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    plan, review, request = map(_mapping, (execution_plan, execution_plan_review_result, operator_execution_request))
    config = _mapping(runtime_config)
    token = issue_executor_admission_token(plan, review, request, target_root=target_root, now=now)
    reasons = list(token["reasons"])
    root = None
    if token["token_status"] == "issued":
        try: root = Path(target_root).resolve(strict=True)
        except (OSError, RuntimeError, TypeError): reasons.append("invalid_target_root")
    executor_entry = {
        "contract": "zero.runtime.controlled_executor_entry.v1",
        "entry_status": "admitted" if not reasons else "denied", "token_id": token["token_id"],
        "mode": "controlled_dry_run", "dry_run_only": True,
        "active_execution_allowed": False, "file_mutation_allowed": False,
    }
    manifest = {"contract": "zero.runtime.pre_execution_snapshot_manifest.v1", "entries": [],
                "all_paths_eligible": False, "file_copies_created": False, "target_root_modified": False}
    if not reasons and root:
        manifest, snapshot_reasons = _snapshot(root, token["allowed_files"], int(config.get("max_snapshot_file_size") or _MAX_FILE_SIZE))
        reasons.extend(snapshot_reasons)
    operations = []
    validation_requirements = [item.get("requirement") for item in plan.get("validation_plan", []) if isinstance(item, Mapping)]
    for entry in manifest.get("entries", []):
        operation = "update_candidate" if entry["exists"] else "create_candidate"
        operations.append({"path": entry["path"], "current_state_reference": entry.get("content_hash_sha256") or "missing",
            "requested_change_reference": "not_provided", "intended_operation": "unknown",
            "preconditions": ["executor_admission_token_valid", "snapshot_eligible"],
            "validation_requirements": deepcopy(validation_requirements),
            "rollback_requirements": deepcopy(plan.get("rollback_plan", {})),
            "mutation_ready": False, "blocked_reasons": ["requested_change_content_not_available", f"candidate_classification:{operation}"],
            "patch_text_generated": False, "replacement_content_generated": False})
    dry_plan = {"contract": "zero.runtime.dry_run_mutation_plan.v1",
                "plan_id": f"dry-run-plan-{_fingerprint(operations)[:16]}", "operations": operations,
                "mutation_performed": False, "patch_generated": False, "patch_applied": False}
    preflight_complete = not reasons
    validation = {"contract": "zero.runtime.validation_evidence_capture.v1",
        "required_checks": deepcopy(validation_requirements),
        "input_schema_valid": token["token_status"] == "issued", "path_safety_valid": not any("path" in r for r in reasons),
        "snapshot_validation_valid": manifest.get("all_paths_eligible") is True,
        "token_validation_valid": token["token_status"] == "issued",
        "dry_run_plan_validation_valid": bool(operations) or not token.get("allowed_files"),
        "preflight_validation_complete": preflight_complete,
        "project_validation_executed": False, "project_validation_passed": None,
        "validation_execution_allowed": False, "missing_evidence": deepcopy(plan.get("evidence_requirements", [])),
        "blocked_reasons": deepcopy(reasons)}
    validation["validation_evidence_id"] = f"validation-evidence-{_fingerprint(validation)[:16]}"
    original_hashes = {e["path"]: e["content_hash_sha256"] for e in manifest.get("entries", []) if e.get("content_hash_sha256")}
    rollback = {"contract": "zero.runtime.rollback_prepared_state.v1",
        "snapshot_manifest_reference": manifest.get("manifest_id", ""),
        "affected_paths": list(token.get("allowed_files", [])), "original_hashes": original_hashes,
        "rollback_requirements": deepcopy(plan.get("rollback_plan", {})),
        "rollback_evidence_requirements": ["complete_recoverable_snapshot_required"],
        "rollback_ready": False, "rollback_execution_allowed": False,
        "operation_rollback_prerequisites": {
            "create_candidate": ["delete_created_file_authorization", "creation_evidence"],
            "update_candidate": ["complete_original_content", "metadata_restore_evidence"],
            "delete_candidate": ["complete_original_content", "recreation_authorization"]},
        "missing_prerequisites": ["complete_original_content", "complete_recoverable_snapshot_not_created"],
        "reasons": ["hash_manifest_is_not_recoverable_snapshot"]}
    rollback["rollback_state_id"] = f"rollback-state-{_fingerprint(rollback)[:16]}"
    completed = not reasons
    seed = {"token_id": token["token_id"], "snapshot": manifest.get("manifest_id"),
            "dry_plan": dry_plan["plan_id"], "status": "completed" if completed else "blocked"}
    fixed = {"active_execution_ready": False, "execution_allowed": False,
             "file_mutation_performed": False, "patch_applied": False,
             "validation_executed": False, "rollback_executed": False, "commit_performed": False}
    result = {"contract": RUNTIME_CONTROLLED_EXECUTION_ACTIVATION_CONTRACT,
        "activation_id": f"controlled-activation-{_fingerprint(seed)[:16]}",
        "activation_status": "completed" if completed else "blocked", "mode": "controlled_dry_run",
        "plan_id": token["plan_id"], "review_result_id": token["review_result_id"],
        "operator_request_id": token["operator_request_id"], "token": token,
        "executor_entry": executor_entry, "snapshot_manifest": manifest,
        "dry_run_mutation_plan": dry_plan, "validation_evidence": validation,
        "rollback_prepared_state": rollback, "dry_run_completed": completed,
        "executor_admission_ready": token["token_status"] == "issued", **fixed, "reasons": reasons}
    result["audit_record"] = {"event_type": "controlled_execution_dry_run_evaluated",
        "activation_id": result["activation_id"], "activation_status": result["activation_status"],
        "token_id": token["token_id"], "plan_id": result["plan_id"],
        "review_result_id": result["review_result_id"], "operator_request_id": result["operator_request_id"],
        "dry_run_completed": completed, **fixed, "reasons": deepcopy(reasons)}
    return result


__all__ = ["RUNTIME_CONTROLLED_EXECUTION_ACTIVATION_CONTRACT", "activate_controlled_execution"]
