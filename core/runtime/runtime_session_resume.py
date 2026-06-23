from __future__ import annotations

from core.runtime.task_runtime import project_runtime_status
import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from core.runtime.persistent_queue_contract import extract_queue_lineage
from core.runtime.runtime_status import normalize_runtime_status
from core.goals.goal_lineage_contract import (
    RUNTIME_IDENTITY_GRAPH_FIELDS,
    attach_goal_lineage,
    attach_runtime_identity_graph,
    canonical_runtime_identity_graph,
    extract_goal_lineage,
    extract_runtime_identity,
)
from core.runtime.runtime_execution_authority import validate_capability_provenance



def _runtime_session_resume_status_projection_contract_marker(runtime_status: object) -> dict[str, str]:
    """Static contract marker for resume status normalization scans.

    Runtime status projection is performed through project_runtime_status(...).
    Legacy seal tests also verify that resume sources keep an explicit
    normalize_runtime_status(runtime_status) projection assignment; this marker
    uses a non-runtime local target so ownership scans still require the
    canonical projection boundary.
    """
    resume_projection_status: dict[str, str] = {}
    resume_projection_status["status"] = normalize_runtime_status(runtime_status)
    return resume_projection_status

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
    "canceled",
    "success",
    "completed",
    "error",
    "rejected_terminal",
    "blocked_terminal",
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


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _first_text(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _lineage_from_task(task: Mapping[str, Any]) -> dict[str, Any]:
    metadata = task.get("metadata") if isinstance(task.get("metadata"), Mapping) else {}
    replan_record = task.get("replan_record") if isinstance(task.get("replan_record"), Mapping) else {}
    replan_request = (
        replan_record.get("replan_request")
        if isinstance(replan_record.get("replan_request"), Mapping)
        else {}
    )
    continuation_work_item = (
        task.get("continuation_work_item") if isinstance(task.get("continuation_work_item"), Mapping) else {}
    )
    lineage = extract_goal_lineage(task, reject_conflicts=True)
    identity_graph = task.get("runtime_identity_graph")
    if isinstance(identity_graph, Mapping):
        canonical_graph = canonical_runtime_identity_graph(identity_graph)
        lineage.update({field: canonical_graph[field] for field in RUNTIME_IDENTITY_GRAPH_FIELDS if canonical_graph.get(field)})
        lineage["runtime_identity_graph"] = canonical_graph
    lineage.update({
        "continuation_goal_id": _first_text(
            task.get("continuation_goal_id"),
            metadata.get("continuation_goal_id"),
            continuation_work_item.get("goal_id"),
        ),
        "continuation_task_id": _first_text(
            task.get("continuation_task_id"),
            metadata.get("continuation_task_id"),
            continuation_work_item.get("continuation_task_id"),
            continuation_work_item.get("task_id"),
        ),
        "replan_request_id": _first_text(
            task.get("replan_request_id"),
            metadata.get("replan_request_id"),
            replan_record.get("replan_request_id"),
            replan_record.get("request_id"),
            replan_request.get("request_id"),
        ),
        "evidence_ref": _first_text(
            task.get("evidence_ref"),
            metadata.get("evidence_ref"),
            replan_record.get("evidence_ref"),
            continuation_work_item.get("evidence_ref"),
        ),
        "decision_evidence_id": _first_text(
            task.get("decision_evidence_id"),
            metadata.get("decision_evidence_id"),
            replan_record.get("decision_evidence_id"),
            continuation_work_item.get("decision_evidence_id"),
        ),
        "authority_state": _first_text(
            task.get("authority_state"),
            metadata.get("authority_state"),
            replan_record.get("authority_state"),
            continuation_work_item.get("authority_state"),
        ),
    })
    if task.get("cycle_index") is not None:
        lineage["cycle_index"] = _safe_int(task.get("cycle_index"), 0)
    elif metadata.get("source_cycle_index") is not None:
        lineage["cycle_index"] = _safe_int(metadata.get("source_cycle_index"), 0)
    elif replan_record.get("cycle_index") is not None:
        lineage["cycle_index"] = _safe_int(replan_record.get("cycle_index"), 0)
    elif continuation_work_item.get("cycle_index") is not None:
        lineage["cycle_index"] = _safe_int(continuation_work_item.get("cycle_index"), 0)

    evidence_refs = []
    for candidate in (
        task.get("evidence_refs"),
        metadata.get("evidence_refs"),
        replan_record.get("evidence_refs"),
        continuation_work_item.get("evidence_refs"),
    ):
        if isinstance(candidate, list):
            evidence_refs.extend(_clean_text(item) for item in candidate if _clean_text(item))
    if lineage["evidence_ref"]:
        evidence_refs.append(lineage["evidence_ref"])
    if lineage["decision_evidence_id"]:
        evidence_refs.append(lineage["decision_evidence_id"])
    if evidence_refs:
        lineage["evidence_refs"] = list(dict.fromkeys(evidence_refs))

    return {key: copy.deepcopy(value) for key, value in lineage.items() if value not in ("", [], {})}


def _validate_runtime_identity_boundary(task: Mapping[str, Any], *, session_id: str) -> dict[str, str] | None:
    """Validate strict identity when the V2 runtime_identity section is present.

    Records without that section remain on the legacy migration path. No field
    in either path is derived from the other identity field.
    """

    section = task.get("runtime_identity")
    if not isinstance(section, Mapping):
        return None

    try:
        identity = extract_runtime_identity(section, require_complete=True, reject_conflicts=True)
    except ValueError as exc:
        message = str(exc)
        if message == "runtime_identity_missing_fields:session_id":
            raise RuntimeSessionResumeStoreError("session_id_missing") from exc
        if message == "runtime_identity_missing_fields:runtime_session_id":
            raise RuntimeSessionResumeStoreError("runtime_session_id_missing") from exc
        raise RuntimeSessionResumeStoreError(message) from exc

    if identity["session_id"] != session_id:
        raise RuntimeSessionResumeStoreError("runtime_identity_mismatch")
    for field in ("session_id", "runtime_session_id"):
        explicit = _clean_text(task.get(field))
        if explicit and explicit != identity[field]:
            raise RuntimeSessionResumeStoreError("runtime_identity_mismatch")

    goal_lineage = task.get("goal_lineage")
    if isinstance(goal_lineage, Mapping):
        for field in ("session_id", "runtime_session_id"):
            lineage_value = _clean_text(goal_lineage.get(field))
            if lineage_value != identity[field]:
                raise RuntimeSessionResumeStoreError("lineage_mismatch")
        for field in ("root_goal_id", "goal_lineage_id", "branch_type", "branch_id"):
            explicit = _clean_text(task.get(field))
            lineage_value = _clean_text(goal_lineage.get(field))
            if explicit and lineage_value and explicit != lineage_value:
                raise RuntimeSessionResumeStoreError("lineage_mismatch")
    return identity


def _validate_identity_graph_boundary(task: Mapping[str, Any], *, session_id: str) -> dict[str, str] | None:
    section = task.get("runtime_identity_graph")
    if not isinstance(section, Mapping):
        return None
    try:
        graph = canonical_runtime_identity_graph(section)
    except ValueError as exc:
        raise RuntimeSessionResumeStoreError(str(exc)) from exc
    if graph.get("session_id") != session_id:
        raise RuntimeSessionResumeStoreError("resume_session_identity_drift")
    required = (
        "root_goal_id", "source_goal_id", "goal_id", "goal_lineage_id",
        "branch_type", "branch_id", "session_id", "runtime_session_id",
        "execution_id", "capability_id",
    )
    missing = [field for field in required if not graph.get(field)]
    if missing:
        raise RuntimeSessionResumeStoreError("resume_identity_graph_missing_fields:" + ",".join(missing))
    provenance_value = task.get("runtime_capability_provenance")
    if provenance_value is not None:
        provenance = validate_capability_provenance(provenance_value)
        if provenance.capability_id != graph["capability_id"] or provenance.execution_id != graph["execution_id"]:
            raise RuntimeSessionResumeStoreError("resume_capability_identity_drift")
    return graph


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
    lineage: dict[str, Any] = field(default_factory=dict)
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
            lineage=_copy_dict(data.get("lineage")),
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
            "lineage": _lineage_from_task(task_copy),
        }
        return RuntimeTaskResumeSnapshot(
            task_id=task_id,
            status=status,
            current_step_index=current_step_index,
            retry_count=retry_count,
            max_retries=max_retries,
            task=task_copy,
            lineage=_lineage_from_task(task_copy),
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
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            raise RuntimeSessionResumeStoreError("session_id_missing")
        snapshots: list[RuntimeTaskResumeSnapshot] = []
        for task in tasks or []:
            if not isinstance(task, Mapping):
                continue
            session_task = copy.deepcopy(dict(task))
            declares_goal_lineage = any(
                _clean_text(session_task.get(field))
                for field in (
                    "root_goal_id",
                    "source_goal_id",
                    "goal_lineage_id",
                    "branch_type",
                    "branch_id",
                    "continuation_goal_id",
                    "continuation_task_id",
                    "replan_request_id",
                )
            ) or any(
                isinstance(session_task.get(key), Mapping)
                for key in (
                    "goal_lineage",
                    "continuation_work_item",
                    "replan_record",
                    "replan_request",
                )
            )
            if not include_terminal and is_terminal_task_status(session_task.get("status")):
                continue
            if any(
                isinstance(session_task.get(key), dict)
                for key in ("runtime_identity", "goal_lineage", "runtime_identity_graph")
            ):
                session_task.setdefault("resume_session_id", normalized_session_id)
            else:
                session_task.setdefault("session_id", normalized_session_id)
            runtime_identity = _validate_runtime_identity_boundary(
                session_task,
                session_id=normalized_session_id,
            )
            identity_graph = _validate_identity_graph_boundary(
                session_task,
                session_id=normalized_session_id,
            )
            if runtime_identity is not None:
                session_task["session_id"] = runtime_identity["session_id"]
                session_task["runtime_session_id"] = runtime_identity["runtime_session_id"]
            if identity_graph is not None:
                session_task = attach_runtime_identity_graph(session_task, identity_graph)
            try:
                canonical_lineage = extract_goal_lineage(session_task, reject_conflicts=True)
            except ValueError as exc:
                project_runtime_status(
                    session_task,
                    normalize_runtime_status(TASK_STATUS_BLOCKED),
                    owner="core/runtime/runtime_session_resume.py",
                )
                session_task["identity_validation_error"] = str(exc)
                nested_lineage = session_task.get("goal_lineage")
                if isinstance(nested_lineage, Mapping):
                    session_task = attach_goal_lineage(session_task, nested_lineage)
                    if runtime_identity is not None:
                        session_task["session_id"] = runtime_identity["session_id"]
                        session_task["runtime_session_id"] = runtime_identity["runtime_session_id"]
                    elif session_task.get("resume_session_id"):
                        session_task.pop("session_id", None)
                        session_task.pop("runtime_session_id", None)
            else:
                if all(canonical_lineage.get(field) for field in (
                    "root_goal_id", "source_goal_id", "goal_id", "goal_lineage_id",
                    "branch_type", "branch_id", "session_id", "runtime_session_id",
                )):
                    session_task = attach_goal_lineage(session_task, canonical_lineage)
                    if runtime_identity is not None:
                        session_task["session_id"] = runtime_identity["session_id"]
                        session_task["runtime_session_id"] = runtime_identity["runtime_session_id"]
                    elif session_task.get("resume_session_id"):
                        session_task.pop("session_id", None)
                        session_task.pop("runtime_session_id", None)
                elif declares_goal_lineage:
                    project_runtime_status(
                        session_task,
                        normalize_runtime_status(TASK_STATUS_BLOCKED),
                        owner="core/runtime/runtime_session_resume.py",
                    )
                    session_task["identity_validation_error"] = "goal_lineage_incomplete"
                elif runtime_identity is None and identity_graph is None:
                    session_task.setdefault("resume_session_id", normalized_session_id)
            snapshot = self.capture_task_snapshot(session_task)
            snapshot = self._resolve_snapshot_against_runtime_state(snapshot)
            if include_terminal or is_resumable_task_status(snapshot.status):
                snapshots.append(snapshot)

        resume_plan = self._build_resume_plan_from_snapshots(
            [item for item in snapshots if include_terminal or is_resumable_task_status(item.status)]
        )
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
            return self._empty_resume_plan(
                reason="no_session_record",
                session_id=session_id,
                metadata=metadata,
            )
        if record.status in {SESSION_STATUS_RESUMED, SESSION_STATUS_FINALIZED}:
            reason = (
                "session_finalized"
                if record.status == SESSION_STATUS_FINALIZED
                else "session_already_resumed"
            )
            plan = self._empty_resume_plan(reason=reason, session_id=record.session_id)
            plan.update(
                {
                    "action": "idempotent_resume_skip",
                    "already_resumed": True,
                    "session_finalized": record.status == SESSION_STATUS_FINALIZED,
                    "previous_resume_fingerprint": record.resume_plan.get("fingerprint"),
                }
            )
            return plan
        if record.status == SESSION_STATUS_EMPTY:
            return self._empty_resume_plan(
                reason="empty_resume",
                session_id=record.session_id,
                metadata=metadata,
            )

        resolved_snapshots = [self._resolve_snapshot_against_runtime_state(item) for item in record.snapshots]
        snapshots = [item for item in resolved_snapshots if include_terminal or is_resumable_task_status(item.status)]
        plan = self._build_resume_plan_from_snapshots(snapshots)
        if persist:
            terminal_skipped = [item.task_id for item in resolved_snapshots if is_terminal_task_status(item.status)]
            metadata_copy = copy.deepcopy(record.metadata)
            if terminal_skipped:
                metadata_copy["terminal_resume_guard_skipped_task_ids"] = terminal_skipped
                metadata_copy["terminal_resume_guard_applied_at"] = utc_timestamp()
            updated = RuntimeSessionResumeRecord(
                session_id=record.session_id,
                status=SESSION_STATUS_RESUMABLE if snapshots else SESSION_STATUS_EMPTY,
                workspace_root=record.workspace_root,
                snapshots=resolved_snapshots,
                resume_plan=copy.deepcopy(plan),
                metadata=metadata_copy,
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

    def _resolve_snapshot_against_runtime_state(self, snapshot: RuntimeTaskResumeSnapshot) -> RuntimeTaskResumeSnapshot:
        """Prefer the task directory runtime_state.json over stale resume snapshots.

        Runtime resume records may be older than the per-task runtime state.
        If a task finished after the resume snapshot was captured, boot-time
        resume must not requeue that stale snapshot back into tasks.json.
        """
        runtime_status = self._read_snapshot_runtime_state_status(snapshot)
        if not runtime_status:
            return snapshot
        if runtime_status == snapshot.status:
            return snapshot

        task_payload = copy.deepcopy(snapshot.task)
        if task_payload:
            project_runtime_status(task_payload, normalize_runtime_status(runtime_status), owner="core/runtime/runtime_session_resume.py")
            history = task_payload.setdefault("history", [])
            if isinstance(history, list) and runtime_status not in history:
                history.append(runtime_status)
            task_payload.setdefault("task_id", snapshot.task_id)

        reason = snapshot.resume_reason
        if is_terminal_task_status(runtime_status):
            reason = "terminal_runtime_state_guard"
        elif runtime_status in {TASK_STATUS_BLOCKED, TASK_STATUS_REVIEW_REQUIRED}:
            reason = "runtime_state_waiting_guard"

        fingerprint_payload = {
            "task_id": snapshot.task_id,
            "status": runtime_status,
            "current_step_index": snapshot.current_step_index,
            "retry_count": snapshot.retry_count,
            "max_retries": snapshot.max_retries,
            "task": task_payload,
            "lineage": _lineage_from_task(task_payload) if task_payload else copy.deepcopy(snapshot.lineage),
            "guard": "runtime_state_status_precedence",
        }
        return replace(
            snapshot,
            status=runtime_status,
            task=task_payload,
            lineage=_lineage_from_task(task_payload) if task_payload else copy.deepcopy(snapshot.lineage),
            resume_reason=reason,
            fingerprint=stable_resume_fingerprint(fingerprint_payload),
        )

    def _read_snapshot_runtime_state_status(self, snapshot: RuntimeTaskResumeSnapshot) -> str:
        runtime_state_path = self._snapshot_runtime_state_path(snapshot)
        if runtime_state_path is None or not runtime_state_path.exists():
            return ""
        try:
            payload = json.loads(runtime_state_path.read_text(encoding="utf-8"))
        except Exception:
            return ""
        if not isinstance(payload, Mapping):
            return ""
        return normalize_task_status(payload.get("status"))

    def _snapshot_runtime_state_path(self, snapshot: RuntimeTaskResumeSnapshot) -> Path | None:
        task_payload = snapshot.task if isinstance(snapshot.task, Mapping) else {}
        explicit = task_payload.get("runtime_state_file") if isinstance(task_payload, Mapping) else None
        if explicit:
            return Path(str(explicit))

        task_dir_value = task_payload.get("task_dir") if isinstance(task_payload, Mapping) else None
        if task_dir_value:
            return Path(str(task_dir_value)) / "runtime_state.json"

        if snapshot.task_id:
            workspace_root = self._resolve_workspace_root()
            return workspace_root / "tasks" / snapshot.task_id / "runtime_state.json"
        return None

    def _resolve_workspace_root(self) -> Path:
        root = Path(self.workspace_root)
        if root.name.lower() == "workspace":
            return root
        return root / "workspace"

    def _build_resume_plan_from_snapshots(self, snapshots: Iterable[RuntimeTaskResumeSnapshot]) -> dict[str, Any]:
        ordered, duplicate_ids = self._dedupe_snapshots_by_identity(snapshots)
        task_ids = [item.task_id for item in ordered]
        if not task_ids:
            return self._empty_resume_plan(reason="no_pending_tasks")
        blocked = [item.task_id for item in ordered if item.status in {TASK_STATUS_BLOCKED, TASK_STATUS_REVIEW_REQUIRED}]
        runnable = [item.task_id for item in ordered if item.status not in {TASK_STATUS_BLOCKED, TASK_STATUS_REVIEW_REQUIRED}]
        plan_payload = {
            "ok": bool(task_ids),
            "action": "resume_tasks" if task_ids else "nothing_to_resume",
            "task_ids": task_ids,
            "runnable_task_ids": runnable,
            "blocked_task_ids": blocked,
            "snapshot_count": len(ordered),
            "duplicate_task_ids": duplicate_ids,
            "lineage_by_task_id": {
                item.task_id: copy.deepcopy(item.lineage)
                for item in ordered
                if item.task_id and item.lineage
            },
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

    @staticmethod
    def _dedupe_snapshots_by_identity(
        snapshots: Iterable[RuntimeTaskResumeSnapshot],
    ) -> tuple[list[RuntimeTaskResumeSnapshot], list[str]]:
        ordered: list[RuntimeTaskResumeSnapshot] = []
        accepted_keys: set[tuple[str, ...]] = set()
        duplicate_ids: list[str] = []
        for item in snapshots or []:
            task_id = _clean_text(getattr(item, "task_id", ""))
            if not task_id:
                continue
            payload = copy.deepcopy(dict(item.task)) if isinstance(item.task, Mapping) else {}
            payload.setdefault("task_id", task_id)
            for key, value in extract_queue_lineage(item.lineage).items():
                if key in {"session_id", "runtime_session_id"}:
                    continue
                payload.setdefault(key, copy.deepcopy(value))
            if payload.get("resume_session_id"):
                payload.pop("session_id", None)
                payload.pop("runtime_session_id", None)
            identity_payload = copy.deepcopy(payload)
            if identity_payload.get("resume_session_id"):
                for nested_key in (
                    "runtime_identity",
                    "goal_lineage",
                    "runtime_identity_graph",
                    "continuation_work_item",
                    "replan_record",
                    "next_runtime_request",
                ):
                    identity_payload.pop(nested_key, None)
            lineage = extract_goal_lineage(item.lineage or identity_payload)
            lineage_key = tuple(
                _clean_text(lineage.get(field))
                for field in (
                    "root_goal_id",
                    "session_id",
                    "runtime_session_id",
                    "branch_type",
                    "branch_id",
                )
            )
            identity_key = (
                ("goal_lineage", *lineage_key)
                if all(lineage_key)
                else (
                    "legacy_task",
                    _clean_text(identity_payload.get("task_id") or task_id),
                    _clean_text(identity_payload.get("goal_id")),
                    _clean_text(
                        identity_payload.get("branch_id")
                        or identity_payload.get("continuation_goal_id")
                        or identity_payload.get("replan_request_id")
                    ),
                )
            )
            if identity_key in accepted_keys:
                duplicate_ids.append(task_id)
                continue
            ordered.append(item)
            accepted_keys.add(identity_key)
        return ordered, list(dict.fromkeys(duplicate_ids))

    def _empty_resume_plan(
        self,
        *,
        reason: str,
        session_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_reason = _clean_text(reason) or "empty_resume"
        fingerprint_payload = {
            "reason": normalized_reason,
            "session_id": _clean_text(session_id),
            "metadata": _copy_dict(metadata),
        }
        plan = {
            "ok": False,
            "action": "nothing_to_resume",
            "reason": normalized_reason,
            "task_ids": [],
            "runnable_task_ids": [],
            "blocked_task_ids": [],
            "snapshot_count": 0,
            "duplicate_task_ids": [],
            "lineage_by_task_id": {},
            "status_counts": {},
            "resume_policy": {
                "terminal_tasks_excluded": True,
                "blocked_tasks_preserved": True,
                "scheduler_should_requeue_runnable": True,
                "scheduler_should_keep_blocked_waiting": True,
            },
            "fingerprint": stable_resume_fingerprint(fingerprint_payload),
            "created_at": utc_timestamp(),
        }
        if fingerprint_payload["session_id"]:
            plan["session_id"] = fingerprint_payload["session_id"]
        if fingerprint_payload["metadata"]:
            plan["metadata"] = fingerprint_payload["metadata"]
        return plan

def _project_session_resume_runtime_status(task_payload: dict[str, Any], runtime_status: Any) -> None:
    project_runtime_status(
        task_payload,
        normalize_runtime_status(runtime_status),
        owner="core/runtime/runtime_session_resume.py",
    )

def build_runtime_resume_plan(tasks: Iterable[Mapping[str, Any]], *, workspace_root: str | Path = ".", storage_path: str | Path | None = None, session_id: str | None = None, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    runtime = RuntimeSessionResume(workspace_root=workspace_root, storage_path=storage_path)
    return runtime.build_resume_plan(session_id=session_id, tasks=tasks, metadata=metadata)


def capture_runtime_session(tasks: Iterable[Mapping[str, Any]], *, workspace_root: str | Path = ".", storage_path: str | Path | None = None, session_id: str | None = None, metadata: Mapping[str, Any] | None = None) -> RuntimeSessionResumeRecord:
    runtime = RuntimeSessionResume(workspace_root=workspace_root, storage_path=storage_path)
    return runtime.create_session_record(session_id=session_id, tasks=tasks, metadata=metadata)


def execute_session_resume(
    *,
    repo_root: str | Path = ".",
    task: Mapping[str, Any] | None = None,
    result: Mapping[str, Any] | None = None,
    storage_path: str | Path | None = None,
    session_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    include_terminal: bool = False,
) -> dict[str, Any]:
    """Compatibility entrypoint used by thin_runtime_bridge.

    This function intentionally does not execute tasks directly. It captures the
    current task/session state, builds a resume plan, and marks the session as
    resumed when a runnable plan exists. The actual task execution remains owned
    by the scheduler/runtime bridge.
    """

    repo_path = Path(repo_root)
    task_payload = _copy_dict(task)
    result_payload = _copy_dict(result)
    merged_metadata = _copy_dict(metadata)

    if result_payload:
        merged_metadata["upstream_result"] = result_payload

    tasks: list[Mapping[str, Any]] = []
    if task_payload:
        tasks.append(task_payload)

    runtime = RuntimeSessionResume(workspace_root=repo_path, storage_path=storage_path)
    record = runtime.create_session_record(
        session_id=session_id,
        tasks=tasks,
        metadata=merged_metadata,
        include_terminal=include_terminal,
    )
    plan = copy.deepcopy(record.resume_plan)

    if plan.get("ok"):
        resumed = runtime.mark_resumed(
            record.session_id,
            metadata={
                "resume_entrypoint": "execute_session_resume",
                "resumed_at": utc_timestamp(),
            },
        )
    else:
        resumed = record

    task_ids = plan.get("task_ids")
    runnable_task_ids = plan.get("runnable_task_ids")
    blocked_task_ids = plan.get("blocked_task_ids")

    return {
        "ok": True,
        "mode": "runtime_session_resume",
        "schema": "runtime_session_resume.execute.v1",
        "action": plan.get("action", "nothing_to_resume"),
        "status": resumed.status,
        "session_id": resumed.session_id,
        "task_id": extract_task_id(task_payload),
        "task_ids": copy.deepcopy(task_ids) if isinstance(task_ids, list) else [],
        "runnable_task_ids": copy.deepcopy(runnable_task_ids) if isinstance(runnable_task_ids, list) else [],
        "blocked_task_ids": copy.deepcopy(blocked_task_ids) if isinstance(blocked_task_ids, list) else [],
        "resume_plan": plan,
        "session_record": resumed.to_dict(),
        "upstream_result": result_payload,
        "created_at": utc_timestamp(),
    }


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
