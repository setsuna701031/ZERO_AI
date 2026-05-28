from __future__ import annotations

import copy
import difflib
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PATCH_STATUS_CREATED = "created"
PATCH_STATUS_SNAPSHOTTED = "snapshotted"
PATCH_STATUS_DIFFED = "diffed"
PATCH_STATUS_ROLLED_BACK = "rolled_back"
PATCH_STATUS_FINALIZED = "finalized"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_patch_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _copy_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _copy_list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


@dataclass(frozen=True)
class RuntimePatchFileSnapshot:
    path: str
    exists: bool
    content: str = ""
    sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "exists": self.exists,
            "content": self.content,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimePatchFileSnapshot":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            path=str(data.get("path") or ""),
            exists=bool(data.get("exists", False)),
            content=str(data.get("content") or ""),
            sha256=str(data.get("sha256") or ""),
        )


@dataclass(frozen=True)
class RuntimePatchDiffEntry:
    path: str
    before_sha256: str
    after_sha256: str
    diff: str
    status: str = PATCH_STATUS_DIFFED

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
            "diff": self.diff,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimePatchDiffEntry":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            path=str(data.get("path") or ""),
            before_sha256=str(data.get("before_sha256") or ""),
            after_sha256=str(data.get("after_sha256") or ""),
            diff=str(data.get("diff") or ""),
            status=str(data.get("status") or PATCH_STATUS_DIFFED),
        )


@dataclass(frozen=True)
class RuntimePatchRecord:
    patch_id: str
    workspace_root: str
    status: str = PATCH_STATUS_CREATED
    target_files: list[str] = field(default_factory=list)
    before_snapshots: dict[str, RuntimePatchFileSnapshot] = field(default_factory=dict)
    after_snapshots: dict[str, RuntimePatchFileSnapshot] = field(default_factory=dict)
    diffs: list[RuntimePatchDiffEntry] = field(default_factory=list)
    mutation_ref: dict[str, Any] = field(default_factory=dict)
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "workspace_root": self.workspace_root,
            "status": self.status,
            "target_files": copy.deepcopy(self.target_files),
            "before_snapshots": {
                key: value.to_dict()
                for key, value in self.before_snapshots.items()
            },
            "after_snapshots": {
                key: value.to_dict()
                for key, value in self.after_snapshots.items()
            },
            "diffs": [item.to_dict() for item in self.diffs],
            "mutation_ref": copy.deepcopy(self.mutation_ref),
            "audit_log": copy.deepcopy(self.audit_log),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimePatchRecord":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            patch_id=str(data.get("patch_id") or ""),
            workspace_root=str(data.get("workspace_root") or "."),
            status=str(data.get("status") or PATCH_STATUS_CREATED),
            target_files=[str(x) for x in data.get("target_files") or []],
            before_snapshots={
                str(k): RuntimePatchFileSnapshot.from_dict(v)
                for k, v in (data.get("before_snapshots") or {}).items()
                if isinstance(v, dict)
            },
            after_snapshots={
                str(k): RuntimePatchFileSnapshot.from_dict(v)
                for k, v in (data.get("after_snapshots") or {}).items()
                if isinstance(v, dict)
            },
            diffs=[RuntimePatchDiffEntry.from_dict(x) for x in data.get("diffs") or [] if isinstance(x, dict)],
            mutation_ref=_copy_dict(data.get("mutation_ref")),
            audit_log=_copy_list(data.get("audit_log")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


class RuntimeNativeGitPatchPipelineRejected(RuntimeError):
    pass


class RuntimeNativeGitPatchPipeline:
    """
    Runtime-native git-style diff / patch pipeline.

    It does not require git to be installed. It gives ZERO the needed Codex-like
    artifact boundary:
      - pre-mutation file snapshots
      - post-mutation snapshots
      - unified diff generation
      - persistent patch record
      - rollback from snapshot
    """

    def __init__(
        self,
        *,
        workspace_root: str | Path,
        storage_path: str | Path | None = None,
        mutation_loop: Any = None,
        engineering_session: Any = None,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.storage_path = Path(storage_path) if storage_path is not None else self.workspace_root / "workspace" / "runtime_native_git_patch_pipeline.json"
        self.mutation_loop = mutation_loop
        self.engineering_session = engineering_session
        self._records: dict[str, RuntimePatchRecord] = {}
        self._order: list[str] = []
        self.load()

    @classmethod
    def with_workspace(cls, workspace_root: str | Path = ".", **kwargs: Any) -> "RuntimeNativeGitPatchPipeline":
        return cls(workspace_root=workspace_root, **kwargs)

    def create_patch(
        self,
        *,
        target_files: list[str],
        patch_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimePatchRecord:
        targets = [self._validate_target(x) for x in target_files]
        if not targets:
            raise RuntimeNativeGitPatchPipelineRejected("target_files_required")
        if patch_id is None:
            patch_id = "runtime-git-patch-" + stable_patch_fingerprint(
                {
                    "target_files": targets,
                    "workspace_root": str(self.workspace_root),
                    "sequence": len(self._order) + 1,
                }
            )[:16]
        if patch_id in self._records:
            raise RuntimeNativeGitPatchPipelineRejected(f"patch already exists: {patch_id!r}")

        record = RuntimePatchRecord(
            patch_id=patch_id,
            workspace_root=str(self.workspace_root),
            target_files=targets,
            metadata=_copy_dict(metadata),
        )
        self._records[patch_id] = record
        self._order.append(patch_id)
        self._audit(record.patch_id, "patch_created", {"target_files": targets})
        self.save()
        return self.get_patch(patch_id)

    def snapshot_before(self, patch_id: str) -> RuntimePatchRecord:
        record = self.get_patch(patch_id)
        snapshots = {
            target: self._snapshot_file(target).to_dict()
            for target in record.target_files
        }
        updated = self._replace_record(
            record,
            status=PATCH_STATUS_SNAPSHOTTED,
            before_snapshots=snapshots,
        )
        self._audit(patch_id, "before_snapshot_captured", {"files": list(snapshots)})
        return updated

    def snapshot_after_and_diff(self, patch_id: str) -> RuntimePatchRecord:
        record = self.get_patch(patch_id)
        after = {
            target: self._snapshot_file(target).to_dict()
            for target in record.target_files
        }

        diffs: list[dict[str, Any]] = []
        for target in record.target_files:
            before_snapshot = record.before_snapshots.get(target)
            if before_snapshot is None:
                before_snapshot = RuntimePatchFileSnapshot(path=target, exists=False, content="", sha256="")
            after_snapshot = RuntimePatchFileSnapshot.from_dict(after[target])

            diff_text = self._unified_diff(
                target,
                before_snapshot.content if before_snapshot.exists else "",
                after_snapshot.content if after_snapshot.exists else "",
            )
            diffs.append(
                RuntimePatchDiffEntry(
                    path=target,
                    before_sha256=before_snapshot.sha256,
                    after_sha256=after_snapshot.sha256,
                    diff=diff_text,
                ).to_dict()
            )

        updated = self._replace_record(
            record,
            status=PATCH_STATUS_DIFFED,
            after_snapshots=after,
            diffs=diffs,
        )
        self._audit(patch_id, "after_snapshot_and_diff_captured", {"diff_count": len(diffs)})
        return updated

    def run_mutation_with_patch(
        self,
        *,
        target_files: list[str],
        mutation_goal: str,
        plan_fn: Any,
        verify_fn: Any | None = None,
        repair_fn: Any | None = None,
        max_retries: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> RuntimePatchRecord:
        if self.mutation_loop is None:
            raise RuntimeNativeGitPatchPipelineRejected("mutation_loop_required")

        record = self.create_patch(
            target_files=target_files,
            metadata=metadata,
        )
        record = self.snapshot_before(record.patch_id)

        mutation = self.mutation_loop.run_mutation(
            goal=mutation_goal,
            plan_fn=plan_fn,
            verify_fn=verify_fn,
            repair_fn=repair_fn,
            max_retries=max_retries,
            metadata={
                "patch_id": record.patch_id,
                **_copy_dict(metadata),
            },
        )
        mutation_payload = mutation.to_dict() if hasattr(mutation, "to_dict") else copy.deepcopy(mutation)

        record = self._replace_record(
            record,
            mutation_ref=mutation_payload,
        )
        record = self.snapshot_after_and_diff(record.patch_id)

        return self.finalize_patch(record.patch_id)

    def rollback_patch(self, patch_id: str) -> RuntimePatchRecord:
        record = self.get_patch(patch_id)

        if not record.before_snapshots:
            raise RuntimeNativeGitPatchPipelineRejected("before_snapshot_required_for_rollback")

        for target, snapshot in record.before_snapshots.items():
            path = self._resolve_target(target)
            if snapshot.exists:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(snapshot.content, encoding="utf-8")
            elif path.exists():
                path.unlink()

        updated = self._replace_record(
            record,
            status=PATCH_STATUS_ROLLED_BACK,
        )
        self._audit(patch_id, "patch_rolled_back", {"target_files": record.target_files})
        return updated

    def finalize_patch(self, patch_id: str) -> RuntimePatchRecord:
        record = self.get_patch(patch_id)
        updated = self._replace_record(
            record,
            status=PATCH_STATUS_FINALIZED,
        )
        self._audit(patch_id, "patch_finalized", {"diff_count": len(record.diffs)})
        return self.get_patch(patch_id)

    def get_patch(self, patch_id: str) -> RuntimePatchRecord:
        patch_id = str(patch_id or "").strip()
        record = self._records.get(patch_id)
        if record is None:
            raise RuntimeNativeGitPatchPipelineRejected(f"patch does not exist: {patch_id!r}")
        return copy.deepcopy(record)

    def list_patches(self) -> list[RuntimePatchRecord]:
        return [copy.deepcopy(self._records[item]) for item in self._order if item in self._records]

    def health(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for record in self._records.values():
            counts[record.status] = counts.get(record.status, 0) + 1
        return {
            "ok": True,
            "runtime_phase": "runtime_native_git_patch_pipeline_health",
            "patches": len(self._records),
            "counts": counts,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_native_git_patch_pipeline",
            "records": [self._records[item].to_dict() for item in self._order if item in self._records],
        }

    def load(self) -> None:
        if self.storage_path is None or not self.storage_path.exists():
            return
        payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return
        self._records = {}
        self._order = []
        for item in payload.get("records") or []:
            if isinstance(item, dict):
                record = RuntimePatchRecord.from_dict(item)
                if record.patch_id:
                    self._records[record.patch_id] = record
                    self._order.append(record.patch_id)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def _snapshot_file(self, target: str) -> RuntimePatchFileSnapshot:
        path = self._resolve_target(target)
        if not path.exists():
            return RuntimePatchFileSnapshot(path=target, exists=False, content="", sha256="")
        content = path.read_text(encoding="utf-8")
        return RuntimePatchFileSnapshot(
            path=target,
            exists=True,
            content=content,
            sha256=sha256_text(content),
        )

    def _unified_diff(self, target: str, before: str, after: str) -> str:
        before_lines = before.splitlines(keepends=True)
        after_lines = after.splitlines(keepends=True)
        return "".join(
            difflib.unified_diff(
                before_lines,
                after_lines,
                fromfile=f"a/{target}",
                tofile=f"b/{target}",
                lineterm="",
            )
        )

    def _resolve_target(self, target: str) -> Path:
        target = self._validate_target(target)
        path = Path(target)
        if path.is_absolute():
            resolved = path
        else:
            resolved = self.workspace_root / path
        if ".." in Path(target).parts:
            raise RuntimeNativeGitPatchPipelineRejected(f"target escapes workspace: {target!r}")
        return resolved

    def _validate_target(self, target: str) -> str:
        text = str(target or "").strip().replace("\\", "/")
        if not text:
            raise RuntimeNativeGitPatchPipelineRejected("target_file_required")
        if text.startswith("../") or "/../" in text:
            raise RuntimeNativeGitPatchPipelineRejected(f"target escapes workspace: {target!r}")
        return text

    def _replace_record(self, record: RuntimePatchRecord, **updates: Any) -> RuntimePatchRecord:
        latest = self._records.get(record.patch_id, record)
        payload = latest.to_dict()
        payload.update(copy.deepcopy(updates))
        payload["updated_at"] = utc_timestamp()
        updated = RuntimePatchRecord.from_dict(payload)
        self._records[updated.patch_id] = updated
        self.save()
        return copy.deepcopy(updated)

    def _audit(self, patch_id: str, event_type: str, payload: dict[str, Any]) -> None:
        record = self._records.get(patch_id)
        if record is None:
            return
        entry = {
            "timestamp": utc_timestamp(),
            "event_type": event_type,
            "payload": copy.deepcopy(payload),
        }
        updated_payload = record.to_dict()
        updated_payload["audit_log"] = _copy_list(updated_payload.get("audit_log")) + [entry]
        updated_payload["updated_at"] = utc_timestamp()
        self._records[patch_id] = RuntimePatchRecord.from_dict(updated_payload)
        self.save()
