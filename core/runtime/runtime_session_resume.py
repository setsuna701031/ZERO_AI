from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

SESSION_STATUS_OPEN = "open"
SESSION_STATUS_RESUMABLE = "resumable"
SESSION_STATUS_RESUMED = "resumed"
SESSION_STATUS_FINALIZED = "finalized"
SESSION_STATUS_EMPTY = "empty"

TASK_STATUS_CREATED = "created"
TASK_STATUS_QUEUED = "queued"
TASK_STATUS_READY = "ready"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_RETRY = "retry"
TASK_STATUS_RETRYING = "retrying"
TASK_STATUS_BLOCKED = "blocked"
TASK_STATUS_REVIEW_REQUIRED = "review_required"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_FINISHED = "finished"
TASK_STATUS_DONE = "done"
TASK_STATUS_CANCELLED = "cancelled"

RESUMABLE_TASK_STATUSES = {
    TASK_STATUS_CREATED,
    TASK_STATUS_QUEUED,
    TASK_STATUS_READY,
    TASK_STATUS_RUNNING,
    TASK_STATUS_RETRY,
    TASK_STATUS_RETRYING,
    TASK_STATUS_BLOCKED,
    TASK_STATUS_REVIEW_REQUIRED,
}

TERMINAL_TASK_STATUSES = {
    TASK_STATUS_FAILED,
    TASK_STATUS_FINISHED,
    TASK_STATUS_DONE,
    TASK_STATUS_CANCELLED,
    "success",
    "completed",
    "error",
}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_resume_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _copy_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _copy_list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def normalize_task_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text or TASK_STATUS_CREATED


def is_resumable_task_status(value: Any) -> bool:
    return normalize_task_status(value) in RESUMABLE_TASK_STATUSES


def is_terminal_task_status(value: Any) -> bool:
    return normalize_task_status(value) in TERMINAL_TASK_STATUSES


def extract_task_id(task: Mapping[str, Any] | None) -> str:
    if not isinstance(task, Mapping):
        return ""
    for key in ("task_id", "id", "uuid", "name"):
        value = str(task.get(key) or "").strip()
        if value:
            return value
    return ""


@dataclass(frozen=True)
class RuntimeTaskResumeSnapshot:
    task_id: str
    status: str
    current_step_index: int = 0
    retry_count: int = 0
    max_retries: int = 0
    task: dict[str, Any] = field(default_factory=dict)
    resume_reason: str = ""
    fingerprint: str = ""
    captured_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "RuntimeTaskResumeSnapshot":
        data = payload if isinstance(payload, Mapping) else {}
        return cls(
            task_id=str(data.get("task_id") or ""),
            status=normalize_task_status(data.get("status")),
            current_step_index=_safe_int(data.get("current_step_index"), 0),
            retry_count=_safe_int(data.get("retry_count"), 0),
            max_retries=_safe_int(data.get("max_retries"), 0),
            task=_copy_dict(data.get("task")),
            resume_reason=str(data.get("resume_reason") or ""),
            fingerprint=str(data.get("fingerprint") or ""),
            captured_at=str(data.get("captured_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeSessionResumeRecord:
    session_id: str
    status: str
    workspace_root: str
    snapshots: list[RuntimeTaskResumeSnapshot] = field(default_factory=list)
    resume_plan: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "workspace_root": self.workspace_root,
            "snapshots": [item.to_dict() for item in self.snapshots],
            "resume_plan": copy.deepcopy(self.resume_plan),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> "RuntimeSessionResumeRecord":
        data = payload if isinstance(payload, Mapping) else {}
        return cls(
            session_id=str(data.get("session_id") or ""),
            status=str(data.get("status") or SESSION_STATUS_EMPTY),
            workspace_root=str(data.get("workspace_root") or "."),
            snapshots=[RuntimeTaskResumeSnapshot.from_dict(x) for x in data.get("snapshots") or [] if isinstance(x, Mapping)],
            resume_plan=_copy_dict(data.get("resume_plan")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


class RuntimeSessionResumeStoreError(RuntimeError):
    pass


class RuntimeSessionResume:
    """Persistent session resume and task-continuation coordinator.

    Boundary:
    - This module owns durable resume records and resumable task selection.
    - It does not execute tasks directly.
    - Scheduler/AgentLoop can call build_resume_plan() and then submit the
      returned task ids back into their existing dispatch path.
    """

    def __init__(self, *, workspace_root: str | Path = ".", storage_path: str | Path | None = None) -> None:
        self.workspace_root = Path(workspace_root)
        self.storage_path = Path(storage_path) if storage_path is not None else self.workspace_root / "workspace" / "runtime_session_resume.json"
        self._records: dict[str, RuntimeSessionResumeRecord] = {}
        self._order: list[str] = []
        self.load()

    @classmethod
    def with_workspace(cls, workspace_root: str | Path = ".", **kwargs: Any) -> "RuntimeSessionResume":
        return cls(workspace_root=workspace_root, **kwargs)

    def capture_task_snapshot(self, task: Mapping[str, Any], *, resume_reason: str = "") -> RuntimeTaskResumeSnapshot:
        task_copy = _copy_dict(task)
        task_id = extract_task_id(task_copy)
        if not task_id:
            task_id = "task:" + stable_resume_fingerprint(task_copy)[:16]
            task_copy.setdefault("task_id", task_id)
        status = normalize_task_status(task_copy.get("status"))
        current_step_index = _safe_int(task_copy.get("current_step_index", task_copy.get("step_index", 0)), 0)
        retry_count = _safe_int(task_copy.get("retry_count"), 0)
        max_retries = _safe_int(task_copy.get("max_retries"), 0)
        fingerprint_payload = {
            "task_id": task_id,
            "status": status,
            "current_step_index": current_step_index,
            "retry_count": retry_count,
            "max_retries": max_retries,
            "task": task_copy,
        }
        return RuntimeTaskResumeSnapshot(
            task_id=task_id,
            status=status,
            current_step_index=current_step_index,
            retry_count=retry_count,
            max_retries=max_retries,
            task=task_copy,
            resume_reason=resume_reason or _default_resume_reason(status),
            fingerprint=stable_resume_fingerprint(fingerprint_payload),
        )

    def create_session_record(
        self,
        *,
        session_id: str | None = None,
        tasks: Iterable[Mapping[str, Any]] | None = None,
        metadata: Mapping[str, Any] | None = None,
        include_terminal: bool = False,
    ) -> RuntimeSessionResumeRecord:
        normalized_session_id = str(session_id or "").strip() or self._new_session_id(tasks=tasks, metadata=metadata)
        snapshots: list[RuntimeTaskResumeSnapshot] = []
        for task in tasks or []:
            if not isinstance(task, Mapping):
                continue
            snapshot = self.capture_task_snapshot(task)
            if include_terminal or is_resumable_task_status(snapshot.status):
                snapshots.append(snapshot)

        resume_plan = self._build_resume_plan_from_snapshots(snapshots)
        status = SESSION_STATUS_RESUMABLE if snapshots else SESSION_STATUS_EMPTY
        now = utc_timestamp()
        record = RuntimeSessionResumeRecord(
            session_id=normalized_session_id,
            status=status,
            workspace_root=str(self.workspace_root),
            snapshots=snapshots,
            resume_plan=resume_plan,
            metadata=_copy_dict(metadata),
            created_at=now,
            updated_at=now,
        )
        self._records[normalized_session_id] = record
        if normalized_session_id not in self._order:
            self._order.append(normalized_session_id)
        self.save()
        return record

    def build_resume_plan(
        self,
        *,
        session_id: str | None = None,
        tasks: Iterable[Mapping[str, Any]] | None = None,
        include_terminal: bool = False,
        persist: bool = True,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if tasks is not None:
            record = self.create_session_record(
                session_id=session_id,
                tasks=tasks,
                include_terminal=include_terminal,
                metadata=metadata,
            )
            return copy.deepcopy(record.resume_plan)

        record = self.get_record(session_id) if session_id else self.latest_record()
        if record is None:
            return self._empty_resume_plan(reason="no_session_record")

        snapshots = [item for item in record.snapshots if include_terminal or is_resumable_task_status(item.status)]
        plan = self._build_resume_plan_from_snapshots(snapshots)
        if persist:
            updated = RuntimeSessionResumeRecord(
                session_id=record.session_id,
                status=SESSION_STATUS_RESUMABLE if snapshots else SESSION_STATUS_EMPTY,
                workspace_root=record.workspace_root,
                snapshots=list(record.snapshots),
                resume_plan=copy.deepcopy(plan),
                metadata=copy.deepcopy(record.metadata),
                created_at=record.created_at,
                updated_at=utc_timestamp(),
            )
            self._records[record.session_id] = updated
            self.save()
        return plan

    def mark_resumed(self, session_id: str | None = None, *, metadata: Mapping[str, Any] | None = None) -> RuntimeSessionResumeRecord:
        record = self.get_record(session_id) if session_id else self.latest_record()
        if record is None:
            raise RuntimeSessionResumeStoreError("session_record_not_found")
        merged_metadata = copy.deepcopy(record.metadata)
        if isinstance(metadata, Mapping):
            merged_metadata.update(copy.deepcopy(dict(metadata)))
        updated = RuntimeSessionResumeRecord(
            session_id=record.session_id,
            status=SESSION_STATUS_RESUMED,
            workspace_root=record.workspace_root,
            snapshots=list(record.snapshots),
            resume_plan=copy.deepcopy(record.resume_plan),
            metadata=merged_metadata,
            created_at=record.created_at,
            updated_at=utc_timestamp(),
        )
        self._records[record.session_id] = updated
        self.save()
        return updated

    def finalize_session(self, session_id: str | None = None, *, final_result: Mapping[str, Any] | None = None) -> RuntimeSessionResumeRecord:
        record = self.get_record(session_id) if session_id else self.latest_record()
        if record is None:
            raise RuntimeSessionResumeStoreError("session_record_not_found")
        metadata = copy.deepcopy(record.metadata)
        if isinstance(final_result, Mapping):
            metadata["final_result"] = copy.deepcopy(dict(final_result))
        updated = RuntimeSessionResumeRecord(
            session_id=record.session_id,
            status=SESSION_STATUS_FINALIZED,
            workspace_root=record.workspace_root,
            snapshots=list(record.snapshots),
            resume_plan=copy.deepcopy(record.resume_plan),
            metadata=metadata,
            created_at=record.created_at,
            updated_at=utc_timestamp(),
        )
        self._records[record.session_id] = updated
        self.save()
        return updated

    def get_record(self, session_id: str | None) -> RuntimeSessionResumeRecord | None:
        key = str(session_id or "").strip()
        return self._records.get(key)

    def latest_record(self) -> RuntimeSessionResumeRecord | None:
        for key in reversed(self._order):
            if key in self._records:
                return self._records[key]
        return None

    def list_records(self) -> list[RuntimeSessionResumeRecord]:
        return [self._records[key] for key in self._order if key in self._records]

    def load(self) -> None:
        if not self.storage_path.exists():
            self._records = {}
            self._order = []
            return
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeSessionResumeStoreError(f"failed_to_load_session_resume_store: {exc}") from exc
        records_payload = payload.get("records") if isinstance(payload, Mapping) else []
        records: dict[str, RuntimeSessionResumeRecord] = {}
        order: list[str] = []
        for item in records_payload or []:
            if not isinstance(item, Mapping):
                continue
            record = RuntimeSessionResumeRecord.from_dict(item)
            if not record.session_id:
                continue
            records[record.session_id] = record
            order.append(record.session_id)
        self._records = records
        self._order = order

    def save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "runtime_session_resume.v1",
            "workspace_root": str(self.workspace_root),
            "records": [self._records[key].to_dict() for key in self._order if key in self._records],
            "updated_at": utc_timestamp(),
        }
        tmp_path = self.storage_path.with_suffix(self.storage_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self.storage_path)

    def _build_resume_plan_from_snapshots(self, snapshots: Iterable[RuntimeTaskResumeSnapshot]) -> dict[str, Any]:
        ordered = list(snapshots or [])
        task_ids = [item.task_id for item in ordered]
        blocked = [item.task_id for item in ordered if item.status in {TASK_STATUS_BLOCKED, TASK_STATUS_REVIEW_REQUIRED}]
        runnable = [item.task_id for item in ordered if item.status not in {TASK_STATUS_BLOCKED, TASK_STATUS_REVIEW_REQUIRED}]
        plan_payload = {
            "ok": bool(task_ids),
            "action": "resume_tasks" if task_ids else "nothing_to_resume",
            "task_ids": task_ids,
            "runnable_task_ids": runnable,
            "blocked_task_ids": blocked,
            "snapshot_count": len(ordered),
            "status_counts": _count_statuses(item.status for item in ordered),
            "resume_policy": {
                "terminal_tasks_excluded": True,
                "blocked_tasks_preserved": True,
                "scheduler_should_requeue_runnable": True,
                "scheduler_should_keep_blocked_waiting": True,
            },
            "fingerprint": stable_resume_fingerprint([item.to_dict() for item in ordered]),
            "created_at": utc_timestamp(),
        }
        return plan_payload

    def _empty_resume_plan(self, *, reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "action": "nothing_to_resume",
            "reason": reason,
            "task_ids": [],
            "runnable_task_ids": [],
            "blocked_task_ids": [],
            "snapshot_count": 0,
            "status_counts": {},
            "fingerprint": stable_resume_fingerprint({"reason": reason}),
            "created_at": utc_timestamp(),
        }

    def _new_session_id(self, *, tasks: Iterable[Mapping[str, Any]] | None, metadata: Mapping[str, Any] | None) -> str:
        payload = {
            "tasks": [extract_task_id(item) or dict(item) for item in tasks or [] if isinstance(item, Mapping)],
            "metadata": dict(metadata or {}),
            "time": utc_timestamp(),
        }
        return "runtime_session:" + stable_resume_fingerprint(payload)[:16]


def build_runtime_resume_plan(tasks: Iterable[Mapping[str, Any]], *, workspace_root: str | Path = ".", storage_path: str | Path | None = None, session_id: str | None = None, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    runtime = RuntimeSessionResume(workspace_root=workspace_root, storage_path=storage_path)
    return runtime.build_resume_plan(session_id=session_id, tasks=tasks, metadata=metadata)


def capture_runtime_session(tasks: Iterable[Mapping[str, Any]], *, workspace_root: str | Path = ".", storage_path: str | Path | None = None, session_id: str | None = None, metadata: Mapping[str, Any] | None = None) -> RuntimeSessionResumeRecord:
    runtime = RuntimeSessionResume(workspace_root=workspace_root, storage_path=storage_path)
    return runtime.create_session_record(session_id=session_id, tasks=tasks, metadata=metadata)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _default_resume_reason(status: str) -> str:
    status = normalize_task_status(status)
    if status in {TASK_STATUS_RUNNING, TASK_STATUS_RETRY, TASK_STATUS_RETRYING}:
        return "interrupted_active_task"
    if status in {TASK_STATUS_BLOCKED, TASK_STATUS_REVIEW_REQUIRED}:
        return "preserve_waiting_task"
    return "non_terminal_task"


def _count_statuses(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = normalize_task_status(value)
        counts[key] = counts.get(key, 0) + 1
    return counts
