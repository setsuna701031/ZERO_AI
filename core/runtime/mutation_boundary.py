from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


MUTATION_STATUS_PREVIEW = "preview"
MUTATION_STATUS_WAITING_APPROVAL = "waiting_approval"
MUTATION_STATUS_APPROVED = "approved"
MUTATION_STATUS_REJECTED = "rejected"
MUTATION_STATUS_SNAPSHOT_CREATED = "snapshot_created"
MUTATION_STATUS_APPLIED = "applied"
MUTATION_STATUS_APPLY_FAILED = "apply_failed"
MUTATION_STATUS_VERIFIED = "verified"
MUTATION_STATUS_VERIFICATION_FAILED = "verification_failed"
MUTATION_STATUS_ROLLED_BACK = "rolled_back"
MUTATION_STATUS_FINALIZED = "finalized"

HIGH_RISK_PREFIXES = (
    "core/",
    "services/",
    "planning/",
    "runtime/",
    "tasks/",
)

HIGH_RISK_FILENAMES = {
    "scheduler.py",
    "agent_loop.py",
    "task_runtime.py",
    "task_runner.py",
    "execution_guard.py",
    "runtime_state_guard.py",
    "runtime_transition_policy.py",
    "repair_rollback.py",
    "step_executor.py",
}

BLOCKED_PATH_PARTS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
}

BLOCKED_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_ed25519",
    "known_hosts",
}


class MutationBoundaryError(RuntimeError):
    """Raised when a mutation lifecycle operation violates the boundary contract."""


class MutationBoundary:
    """
    ZERO controlled mutation execution boundary.

    Boundary responsibility:
    - Build a preview before a mutation is allowed to happen.
    - Decide whether approval is required.
    - Store an approval ticket.
    - Create rollback snapshots before apply.
    - Record governed apply results from the execution layer.
    - Record verification + replay verification results.
    - Write mutation audit records.

    This module deliberately does NOT:
    - call the LLM,
    - plan code edits,
    - apply diffs by itself,
    - run shell commands by itself,
    - bypass ExecutionGuard / Policy / Scheduler.

    Intended flow:

        create_preview(...)
        -> approve_mutation(...) or reject_mutation(...)
        -> create_rollback_snapshot(...)
        -> record_governed_apply(...)
        -> record_replay_verification(...)
        -> finalize_mutation(...)

    The actual file write/apply remains owned by the governed execution layer.
    """

    def __init__(
        self,
        workspace_root: str = "workspace",
        project_root: Optional[str] = None,
        mutation_root: Optional[str] = None,
        audit_filename: str = "mutation_audit.jsonl",
    ) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        self.project_root = os.path.abspath(project_root or os.path.join(self.workspace_root, os.pardir))
        self.mutation_root = os.path.abspath(
            mutation_root or os.path.join(self.workspace_root, "runtime", "mutations")
        )
        self.audit_filename = audit_filename
        self.audit_file = os.path.join(self.mutation_root, audit_filename)
        os.makedirs(self.mutation_root, exist_ok=True)

    # ============================================================
    # lifecycle: preview / approval
    # ============================================================

    def create_preview(
        self,
        *,
        operation: str,
        target_files: List[str],
        reason: str = "",
        proposed_changes: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        requires_approval: Optional[bool] = None,
        created_by: str = "zero",
    ) -> Dict[str, Any]:
        operation_text = str(operation or "").strip() or "mutation"
        normalized_targets = self._normalize_target_files(target_files)
        if not normalized_targets:
            raise MutationBoundaryError("mutation preview requires at least one target file")

        risk = self._classify_risk(normalized_targets, operation=operation_text)
        approval_required = bool(requires_approval) if requires_approval is not None else bool(
            risk.get("requires_approval")
        )

        mutation_id = self._new_mutation_id()
        mutation_dir = self._mutation_dir(mutation_id)
        os.makedirs(mutation_dir, exist_ok=False)

        preview = {
            "schema": "zero.mutation.preview.v1",
            "mutation_id": mutation_id,
            "status": MUTATION_STATUS_WAITING_APPROVAL if approval_required else MUTATION_STATUS_PREVIEW,
            "operation": operation_text,
            "reason": str(reason or "").strip(),
            "target_files": normalized_targets,
            "proposed_changes": copy.deepcopy(proposed_changes if isinstance(proposed_changes, list) else []),
            "risk": risk,
            "requires_approval": approval_required,
            "approval": self._build_approval_ticket(
                mutation_id=mutation_id,
                target_files=normalized_targets,
                risk=risk,
                reason=reason,
                required=approval_required,
            ),
            "rollback": {
                "snapshot_created": False,
                "snapshot_id": "",
                "snapshot_files": [],
            },
            "apply": {
                "applied": False,
                "ok": None,
                "changed_files": [],
                "result": {},
            },
            "verification": {
                "verified": False,
                "replay_verified": False,
                "result": {},
                "replay_result": {},
            },
            "audit": {
                "created_at": self._now(),
                "created_by": str(created_by or "zero"),
                "updated_at": self._now(),
                "events": [
                    {
                        "event": "preview_created",
                        "ts": self._now(),
                        "actor": str(created_by or "zero"),
                    }
                ],
            },
            "metadata": copy.deepcopy(metadata if isinstance(metadata, dict) else {}),
        }

        self._write_mutation_state(mutation_id, preview)
        self._write_json(os.path.join(mutation_dir, "preview.json"), preview)
        self._append_audit("preview_created", preview)
        return copy.deepcopy(preview)

    def approve_mutation(
        self,
        mutation_id: str,
        *,
        approved_by: str = "user",
        note: str = "",
    ) -> Dict[str, Any]:
        state = self.get_mutation(mutation_id)
        if state.get("status") == MUTATION_STATUS_REJECTED:
            raise MutationBoundaryError(f"cannot approve rejected mutation: {mutation_id}")

        state["status"] = MUTATION_STATUS_APPROVED
        approval = state.setdefault("approval", {})
        approval["approved"] = True
        approval["approved_by"] = str(approved_by or "user")
        approval["approved_at"] = self._now()
        approval["note"] = str(note or "")
        self._add_event(state, "approved", actor=approved_by, payload={"note": note})
        self._write_mutation_state(mutation_id, state)
        self._append_audit("approved", state)
        return copy.deepcopy(state)

    def reject_mutation(
        self,
        mutation_id: str,
        *,
        rejected_by: str = "user",
        reason: str = "",
    ) -> Dict[str, Any]:
        state = self.get_mutation(mutation_id)
        state["status"] = MUTATION_STATUS_REJECTED
        approval = state.setdefault("approval", {})
        approval["approved"] = False
        approval["rejected_by"] = str(rejected_by or "user")
        approval["rejected_at"] = self._now()
        approval["reject_reason"] = str(reason or "")
        self._add_event(state, "rejected", actor=rejected_by, payload={"reason": reason})
        self._write_mutation_state(mutation_id, state)
        self._append_audit("rejected", state)
        return copy.deepcopy(state)

    # ============================================================
    # lifecycle: rollback snapshot / apply / verification
    # ============================================================

    def create_rollback_snapshot(
        self,
        mutation_id: str,
        *,
        target_files: Optional[List[str]] = None,
        created_by: str = "zero",
    ) -> Dict[str, Any]:
        state = self.get_mutation(mutation_id)
        self._ensure_not_rejected(state)
        self._ensure_approval_contract(state)

        files = self._normalize_target_files(target_files or list(state.get("target_files") or []))
        if not files:
            raise MutationBoundaryError("rollback snapshot requires at least one target file")

        snapshot_id = self._new_snapshot_id()
        mutation_dir = self._mutation_dir(mutation_id)
        snapshot_dir = os.path.join(mutation_dir, "snapshots", snapshot_id)
        os.makedirs(snapshot_dir, exist_ok=False)

        snapshot_records: List[Dict[str, Any]] = []
        for rel_path in files:
            abs_path = self._resolve_project_path(rel_path)
            record: Dict[str, Any] = {
                "path": rel_path,
                "exists": os.path.exists(abs_path),
                "sha256": "",
                "size_bytes": 0,
                "snapshot_path": "",
            }

            if os.path.exists(abs_path):
                if not os.path.isfile(abs_path):
                    raise MutationBoundaryError(f"rollback snapshot target is not a file: {rel_path}")
                record["sha256"] = self._sha256_file(abs_path)
                record["size_bytes"] = os.path.getsize(abs_path)
                safe_snapshot_path = os.path.join(snapshot_dir, rel_path.replace("/", os.sep))
                os.makedirs(os.path.dirname(safe_snapshot_path), exist_ok=True)
                shutil.copy2(abs_path, safe_snapshot_path)
                record["snapshot_path"] = os.path.relpath(safe_snapshot_path, mutation_dir).replace("\\", "/")

            snapshot_records.append(record)

        state["status"] = MUTATION_STATUS_SNAPSHOT_CREATED
        state["rollback"] = {
            "snapshot_created": True,
            "snapshot_id": snapshot_id,
            "snapshot_dir": os.path.relpath(snapshot_dir, mutation_dir).replace("\\", "/"),
            "snapshot_files": snapshot_records,
            "created_at": self._now(),
            "created_by": str(created_by or "zero"),
        }
        self._add_event(
            state,
            "rollback_snapshot_created",
            actor=created_by,
            payload={"snapshot_id": snapshot_id, "target_files": files},
        )
        self._write_mutation_state(mutation_id, state)
        self._write_json(os.path.join(snapshot_dir, "snapshot_manifest.json"), state["rollback"])
        self._append_audit("rollback_snapshot_created", state)
        return copy.deepcopy(state)

    def record_governed_apply(
        self,
        mutation_id: str,
        *,
        apply_result: Dict[str, Any],
        changed_files: Optional[List[str]] = None,
        actor: str = "zero",
    ) -> Dict[str, Any]:
        state = self.get_mutation(mutation_id)
        self._ensure_not_rejected(state)
        self._ensure_approval_contract(state)

        rollback = state.get("rollback") if isinstance(state.get("rollback"), dict) else {}
        if not rollback.get("snapshot_created"):
            raise MutationBoundaryError("governed apply requires rollback snapshot first")

        normalized_changed = self._normalize_target_files(changed_files or list(state.get("target_files") or []))
        ok = bool(apply_result.get("ok")) if isinstance(apply_result, dict) else False

        state["status"] = MUTATION_STATUS_APPLIED if ok else MUTATION_STATUS_APPLY_FAILED
        state["apply"] = {
            "applied": ok,
            "ok": ok,
            "changed_files": normalized_changed,
            "result": copy.deepcopy(apply_result if isinstance(apply_result, dict) else {"ok": False}),
            "applied_at": self._now(),
            "actor": str(actor or "zero"),
        }
        self._add_event(
            state,
            "governed_apply_recorded",
            actor=actor,
            payload={"ok": ok, "changed_files": normalized_changed},
        )
        self._write_mutation_state(mutation_id, state)
        self._append_audit("governed_apply_recorded", state)
        return copy.deepcopy(state)

    def record_replay_verification(
        self,
        mutation_id: str,
        *,
        verification_result: Dict[str, Any],
        replay_result: Optional[Dict[str, Any]] = None,
        actor: str = "zero",
    ) -> Dict[str, Any]:
        state = self.get_mutation(mutation_id)
        self._ensure_not_rejected(state)

        apply_state = state.get("apply") if isinstance(state.get("apply"), dict) else {}
        if not apply_state.get("applied"):
            raise MutationBoundaryError("replay verification requires successful governed apply first")

        verification_ok = bool(verification_result.get("ok")) if isinstance(verification_result, dict) else False
        replay_payload = replay_result if isinstance(replay_result, dict) else {}
        replay_ok = bool(replay_payload.get("ok")) if replay_payload else verification_ok

        final_ok = verification_ok and replay_ok
        state["status"] = MUTATION_STATUS_VERIFIED if final_ok else MUTATION_STATUS_VERIFICATION_FAILED
        state["verification"] = {
            "verified": verification_ok,
            "replay_verified": replay_ok,
            "ok": final_ok,
            "result": copy.deepcopy(verification_result if isinstance(verification_result, dict) else {"ok": False}),
            "replay_result": copy.deepcopy(replay_payload),
            "verified_at": self._now(),
            "actor": str(actor or "zero"),
        }
        self._add_event(
            state,
            "replay_verification_recorded",
            actor=actor,
            payload={"verified": verification_ok, "replay_verified": replay_ok, "ok": final_ok},
        )
        self._write_mutation_state(mutation_id, state)
        self._append_audit("replay_verification_recorded", state)
        return copy.deepcopy(state)

    def rollback_mutation(
        self,
        mutation_id: str,
        *,
        actor: str = "zero",
        reason: str = "",
    ) -> Dict[str, Any]:
        state = self.get_mutation(mutation_id)
        rollback = state.get("rollback") if isinstance(state.get("rollback"), dict) else {}
        if not rollback.get("snapshot_created"):
            raise MutationBoundaryError("cannot rollback mutation without snapshot")

        mutation_dir = self._mutation_dir(mutation_id)
        restored: List[Dict[str, Any]] = []

        for record in rollback.get("snapshot_files") if isinstance(rollback.get("snapshot_files"), list) else []:
            if not isinstance(record, dict):
                continue
            rel_path = str(record.get("path") or "").strip().replace("\\", "/")
            if not rel_path:
                continue
            abs_target = self._resolve_project_path(rel_path)

            if record.get("exists"):
                snapshot_rel = str(record.get("snapshot_path") or "").replace("\\", "/")
                snapshot_abs = os.path.abspath(os.path.join(mutation_dir, snapshot_rel))
                if not self._is_under(snapshot_abs, mutation_dir) or not os.path.isfile(snapshot_abs):
                    raise MutationBoundaryError(f"snapshot file missing or unsafe: {snapshot_rel}")
                os.makedirs(os.path.dirname(abs_target), exist_ok=True)
                shutil.copy2(snapshot_abs, abs_target)
                restored.append({"path": rel_path, "restored": True, "mode": "copy_snapshot"})
            else:
                if os.path.exists(abs_target):
                    os.remove(abs_target)
                restored.append({"path": rel_path, "restored": True, "mode": "remove_new_file"})

        state["status"] = MUTATION_STATUS_ROLLED_BACK
        state["rollback"]["rolled_back"] = True
        state["rollback"]["rolled_back_at"] = self._now()
        state["rollback"]["rolled_back_by"] = str(actor or "zero")
        state["rollback"]["rollback_reason"] = str(reason or "")
        state["rollback"]["restored_files"] = restored
        self._add_event(state, "rolled_back", actor=actor, payload={"reason": reason, "restored_files": restored})
        self._write_mutation_state(mutation_id, state)
        self._append_audit("rolled_back", state)
        return copy.deepcopy(state)

    def finalize_mutation(
        self,
        mutation_id: str,
        *,
        final_status: Optional[str] = None,
        summary: str = "",
        actor: str = "zero",
    ) -> Dict[str, Any]:
        state = self.get_mutation(mutation_id)
        status = str(final_status or state.get("status") or "").strip() or MUTATION_STATUS_FINALIZED

        state["final"] = {
            "status": status,
            "summary": str(summary or ""),
            "finalized_at": self._now(),
            "actor": str(actor or "zero"),
        }
        state["status"] = status if status != MUTATION_STATUS_FINALIZED else MUTATION_STATUS_FINALIZED
        self._add_event(state, "finalized", actor=actor, payload={"status": status, "summary": summary})
        self._write_mutation_state(mutation_id, state)
        self._append_audit("finalized", state)
        return copy.deepcopy(state)


    def run_governed_mutation_lifecycle(
        self,
        *,
        operation: str,
        target_files: List[str],
        apply_result: Dict[str, Any],
        verification_result: Dict[str, Any],
        replay_result: Optional[Dict[str, Any]] = None,
        reason: str = "",
        proposed_changes: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        approved_by: str = "user",
        actor: str = "zero",
        rollback_on_failure: bool = True,
    ) -> Dict[str, Any]:
        """
        Convenience lifecycle runner for governed mutation tests/integration.

        This does not apply file changes by itself.  The execution layer still
        owns the real write/apply.  This method stitches the boundary contract:

            preview -> approval -> snapshot -> governed apply record
            -> replay verification -> optional rollback -> finalize

        Use this for smoke tests and for scheduler integration when the apply
        result is produced by a guarded executor.
        """
        preview = self.create_preview(
            operation=operation,
            target_files=target_files,
            reason=reason,
            proposed_changes=proposed_changes,
            metadata=metadata,
            created_by=actor,
        )
        mutation_id = str(preview.get("mutation_id") or "")

        if preview.get("requires_approval"):
            self.approve_mutation(mutation_id, approved_by=approved_by, note="auto-approved by lifecycle runner")

        self.create_rollback_snapshot(mutation_id, created_by=actor)
        applied = self.record_governed_apply(
            mutation_id,
            apply_result=apply_result,
            changed_files=target_files,
            actor=actor,
        )

        if not bool(applied.get("apply", {}).get("applied")):
            if rollback_on_failure:
                rolled = self.rollback_mutation(
                    mutation_id,
                    actor=actor,
                    reason="governed apply failed",
                )
                return self.finalize_mutation(
                    mutation_id,
                    final_status=str(rolled.get("status") or MUTATION_STATUS_ROLLED_BACK),
                    summary="governed apply failed; mutation rolled back",
                    actor=actor,
                )
            return self.finalize_mutation(
                mutation_id,
                final_status=MUTATION_STATUS_APPLY_FAILED,
                summary="governed apply failed",
                actor=actor,
            )

        verified = self.record_replay_verification(
            mutation_id,
            verification_result=verification_result,
            replay_result=replay_result,
            actor=actor,
        )

        verification_state = verified.get("verification") if isinstance(verified.get("verification"), dict) else {}
        if not bool(verification_state.get("ok")):
            if rollback_on_failure:
                rolled = self.rollback_mutation(
                    mutation_id,
                    actor=actor,
                    reason="verification or replay verification failed",
                )
                return self.finalize_mutation(
                    mutation_id,
                    final_status=str(rolled.get("status") or MUTATION_STATUS_ROLLED_BACK),
                    summary="verification failed; mutation rolled back",
                    actor=actor,
                )
            return self.finalize_mutation(
                mutation_id,
                final_status=MUTATION_STATUS_VERIFICATION_FAILED,
                summary="verification failed",
                actor=actor,
            )

        return self.finalize_mutation(
            mutation_id,
            final_status=MUTATION_STATUS_VERIFIED,
            summary="governed mutation applied and replay verified",
            actor=actor,
        )


    # ============================================================
    # reads / validation
    # ============================================================

    def get_mutation(self, mutation_id: str) -> Dict[str, Any]:
        mutation_id = self._normalize_mutation_id(mutation_id)
        path = self._state_file(mutation_id)
        if not os.path.exists(path):
            raise MutationBoundaryError(f"mutation state not found: {mutation_id}")
        data = self._read_json(path, {})
        if not isinstance(data, dict):
            raise MutationBoundaryError(f"mutation state is invalid: {mutation_id}")
        return data

    def list_mutations(self, limit: int = 50) -> List[Dict[str, Any]]:
        items: List[Tuple[float, Dict[str, Any]]] = []
        if not os.path.isdir(self.mutation_root):
            return []
        for name in os.listdir(self.mutation_root):
            full = os.path.join(self.mutation_root, name)
            state_file = os.path.join(full, "state.json")
            if not os.path.isdir(full) or not os.path.exists(state_file):
                continue
            data = self._read_json(state_file, {})
            if isinstance(data, dict):
                items.append((os.path.getmtime(state_file), data))
        items.sort(key=lambda pair: pair[0], reverse=True)
        return [copy.deepcopy(item[1]) for item in items[: max(1, int(limit or 50))]]

    def validate_snapshot(self, mutation_id: str) -> Dict[str, Any]:
        state = self.get_mutation(mutation_id)
        rollback = state.get("rollback") if isinstance(state.get("rollback"), dict) else {}
        records = rollback.get("snapshot_files") if isinstance(rollback.get("snapshot_files"), list) else []

        checks: List[Dict[str, Any]] = []
        ok = bool(rollback.get("snapshot_created"))
        mutation_dir = self._mutation_dir(mutation_id)

        for record in records:
            if not isinstance(record, dict):
                continue
            item = {
                "path": str(record.get("path") or ""),
                "exists_at_snapshot": bool(record.get("exists")),
                "snapshot_file_ok": True,
                "sha256_ok": True,
            }
            if record.get("exists"):
                snapshot_rel = str(record.get("snapshot_path") or "")
                snapshot_abs = os.path.abspath(os.path.join(mutation_dir, snapshot_rel))
                snapshot_ok = self._is_under(snapshot_abs, mutation_dir) and os.path.isfile(snapshot_abs)
                item["snapshot_file_ok"] = snapshot_ok
                if snapshot_ok:
                    item["sha256_ok"] = self._sha256_file(snapshot_abs) == str(record.get("sha256") or "")
                else:
                    item["sha256_ok"] = False
                ok = ok and bool(item["snapshot_file_ok"]) and bool(item["sha256_ok"])
            checks.append(item)

        return {
            "ok": ok,
            "mutation_id": state.get("mutation_id"),
            "snapshot_id": rollback.get("snapshot_id", ""),
            "checks": checks,
        }

    # ============================================================
    # policy helpers
    # ============================================================

    def _classify_risk(self, target_files: List[str], operation: str = "") -> Dict[str, Any]:
        reasons: List[str] = []
        normalized = [str(path or "").replace("\\", "/").lstrip("./") for path in target_files]
        unique = list(dict.fromkeys(normalized))

        for path in unique:
            lowered = path.lower()
            filename = os.path.basename(lowered)
            if lowered.startswith(HIGH_RISK_PREFIXES):
                reasons.append(f"repo source path: {path}")
            if filename in HIGH_RISK_FILENAMES:
                reasons.append(f"core runtime file: {path}")

        if len(unique) > 1:
            reasons.append("multi-file mutation")

        operation_lower = str(operation or "").lower()
        if any(token in operation_lower for token in ("delete", "remove", "rename", "move", "destructive")):
            reasons.append("destructive operation marker")

        if any(reason.startswith("core runtime file") for reason in reasons):
            level = "high"
        elif any("repo source path" in reason for reason in reasons) or len(unique) > 1:
            level = "medium"
        else:
            level = "low"

        return {
            "level": level,
            "reasons": reasons,
            "target_count": len(unique),
            "requires_approval": level in {"medium", "high"},
            "requires_rollback_snapshot": True,
            "requires_replay_verification": True,
        }

    def _build_approval_ticket(
        self,
        *,
        mutation_id: str,
        target_files: List[str],
        risk: Dict[str, Any],
        reason: str,
        required: bool,
    ) -> Dict[str, Any]:
        return {
            "ticket_id": f"approval_{mutation_id}",
            "required": bool(required),
            "approved": not bool(required),
            "approved_by": "auto" if not required else "",
            "approved_at": self._now() if not required else "",
            "reason": str(reason or ""),
            "risk_level": risk.get("level", "unknown"),
            "risk_reasons": list(risk.get("reasons") or []),
            "target_files": list(target_files),
        }

    def _ensure_approval_contract(self, state: Dict[str, Any]) -> None:
        approval = state.get("approval") if isinstance(state.get("approval"), dict) else {}
        required = bool(state.get("requires_approval") or approval.get("required"))
        approved = bool(approval.get("approved"))
        if required and not approved:
            raise MutationBoundaryError(
                f"mutation requires approval before this operation: {state.get('mutation_id')}"
            )

    def _ensure_not_rejected(self, state: Dict[str, Any]) -> None:
        if state.get("status") == MUTATION_STATUS_REJECTED:
            raise MutationBoundaryError(f"mutation was rejected: {state.get('mutation_id')}")

    # ============================================================
    # path / persistence helpers
    # ============================================================

    def _normalize_target_files(self, target_files: Any) -> List[str]:
        if not isinstance(target_files, list):
            return []

        normalized: List[str] = []
        for item in target_files:
            text = str(item or "").strip().replace("\\", "/").strip("/")
            text = text.lstrip("./")
            if not text:
                continue
            self._validate_relative_project_path(text)
            normalized.append(text)
        return list(dict.fromkeys(normalized))

    def _validate_relative_project_path(self, rel_path: str) -> None:
        text = str(rel_path or "").replace("\\", "/").strip()
        if not text:
            raise MutationBoundaryError("empty target path is not allowed")
        if os.path.isabs(text):
            raise MutationBoundaryError(f"absolute target path is not allowed: {rel_path}")

        parts = [part for part in text.split("/") if part]
        if any(part in {"..", "."} for part in parts):
            raise MutationBoundaryError(f"path traversal is not allowed: {rel_path}")

        lowered_parts = {part.lower() for part in parts}
        if lowered_parts.intersection(BLOCKED_PATH_PARTS):
            raise MutationBoundaryError(f"blocked target path: {rel_path}")

        filename = os.path.basename(text).lower()
        if filename in BLOCKED_FILENAMES:
            raise MutationBoundaryError(f"blocked target filename: {rel_path}")

        abs_path = self._resolve_project_path(text)
        if not self._is_under(abs_path, self.project_root):
            raise MutationBoundaryError(f"target path outside project root: {rel_path}")

    def _resolve_project_path(self, rel_path: str) -> str:
        return os.path.abspath(os.path.join(self.project_root, str(rel_path).replace("\\", os.sep)))

    def _mutation_dir(self, mutation_id: str) -> str:
        mutation_id = self._normalize_mutation_id(mutation_id)
        return os.path.join(self.mutation_root, mutation_id)

    def _state_file(self, mutation_id: str) -> str:
        return os.path.join(self._mutation_dir(mutation_id), "state.json")

    def _write_mutation_state(self, mutation_id: str, state: Dict[str, Any]) -> None:
        mutation_dir = self._mutation_dir(mutation_id)
        os.makedirs(mutation_dir, exist_ok=True)
        state.setdefault("mutation_id", mutation_id)
        state.setdefault("audit", {})
        if isinstance(state.get("audit"), dict):
            state["audit"]["updated_at"] = self._now()
        self._write_json(self._state_file(mutation_id), state)

    def _append_audit(self, event: str, state: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.audit_file), exist_ok=True)
        record = {
            "ts": self._now(),
            "event": str(event or "mutation_event"),
            "mutation_id": state.get("mutation_id", ""),
            "status": state.get("status", ""),
            "operation": state.get("operation", ""),
            "target_files": list(state.get("target_files") or []),
            "risk": copy.deepcopy(state.get("risk") or {}),
            "requires_approval": bool(state.get("requires_approval")),
        }
        with open(self.audit_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def _add_event(
        self,
        state: Dict[str, Any],
        event: str,
        *,
        actor: str = "zero",
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        audit = state.setdefault("audit", {})
        if not isinstance(audit, dict):
            audit = {}
            state["audit"] = audit
        events = audit.setdefault("events", [])
        if not isinstance(events, list):
            events = []
            audit["events"] = events
        events.append(
            {
                "event": str(event or "event"),
                "ts": self._now(),
                "actor": str(actor or "zero"),
                "payload": copy.deepcopy(payload if isinstance(payload, dict) else {}),
            }
        )
        audit["updated_at"] = self._now()

    def _write_json(self, path: str, payload: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp, path)

    def _read_json(self, path: str, default: Any) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return copy.deepcopy(default)

    def _sha256_file(self, path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _is_under(self, path: str, root: str) -> bool:
        try:
            return os.path.commonpath([os.path.abspath(root), os.path.abspath(path)]) == os.path.abspath(root)
        except Exception:
            return False

    def _new_mutation_id(self) -> str:
        return f"mutation_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    def _new_snapshot_id(self) -> str:
        return f"snapshot_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    def _normalize_mutation_id(self, mutation_id: str) -> str:
        text = str(mutation_id or "").strip()
        if not text:
            raise MutationBoundaryError("mutation_id is required")
        if "/" in text or "\\" in text or ".." in text:
            raise MutationBoundaryError(f"invalid mutation_id: {mutation_id}")
        return text

    def _now(self) -> str:
        return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def create_mutation_boundary(
    workspace_root: str = "workspace",
    project_root: Optional[str] = None,
) -> MutationBoundary:
    return MutationBoundary(workspace_root=workspace_root, project_root=project_root)


__all__ = [
    "MutationBoundary",
    "MutationBoundaryError",
    "create_mutation_boundary",
    "MUTATION_STATUS_PREVIEW",
    "MUTATION_STATUS_WAITING_APPROVAL",
    "MUTATION_STATUS_APPROVED",
    "MUTATION_STATUS_REJECTED",
    "MUTATION_STATUS_SNAPSHOT_CREATED",
    "MUTATION_STATUS_APPLIED",
    "MUTATION_STATUS_APPLY_FAILED",
    "MUTATION_STATUS_VERIFIED",
    "MUTATION_STATUS_VERIFICATION_FAILED",
    "MUTATION_STATUS_ROLLED_BACK",
    "MUTATION_STATUS_FINALIZED",
]
