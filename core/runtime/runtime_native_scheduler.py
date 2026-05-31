from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.runtime.runtime_persistence_service import RuntimePersistenceService


SCHEDULER_STATUS_QUEUED = "queued"
SCHEDULER_STATUS_RUNNING = "running"
SCHEDULER_STATUS_COMPLETED = "completed"
SCHEDULER_STATUS_FAILED = "failed"
SCHEDULER_STATUS_BLOCKED = "blocked"
SCHEDULER_STATUS_RECOVERY_QUEUED = "recovery_queued"
SCHEDULER_STATUS_CONTINUATION_READY = "continuation_ready"

SCHEDULER_PRIORITY_LOW = 10
SCHEDULER_PRIORITY_NORMAL = 50
SCHEDULER_PRIORITY_HIGH = 90


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_scheduler_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _copy_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _copy_list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


@dataclass(frozen=True)
class RuntimeNativeScheduleItem:
    schedule_id: str
    goal: str
    source_session_id: str
    runtime_id: str = ""
    owner_id: str = ""
    task_id: str = ""
    status: str = SCHEDULER_STATUS_QUEUED
    priority: int = SCHEDULER_PRIORITY_NORMAL
    ready_tick: int = 0
    attempts: int = 0
    max_attempts: int = 3
    mainline_result: dict[str, Any] = field(default_factory=dict)
    continuation_ref: dict[str, Any] = field(default_factory=dict)
    recovery_ref: dict[str, Any] = field(default_factory=dict)
    authority_ref: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "goal": self.goal,
            "source_session_id": self.source_session_id,
            "runtime_id": self.runtime_id,
            "owner_id": self.owner_id,
            "task_id": self.task_id,
            "status": self.status,
            "priority": self.priority,
            "ready_tick": self.ready_tick,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "mainline_result": copy.deepcopy(self.mainline_result),
            "continuation_ref": copy.deepcopy(self.continuation_ref),
            "recovery_ref": copy.deepcopy(self.recovery_ref),
            "authority_ref": copy.deepcopy(self.authority_ref),
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeNativeScheduleItem":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            schedule_id=str(data.get("schedule_id") or ""),
            goal=str(data.get("goal") or ""),
            source_session_id=str(data.get("source_session_id") or ""),
            runtime_id=str(data.get("runtime_id") or ""),
            owner_id=str(data.get("owner_id") or ""),
            task_id=str(data.get("task_id") or ""),
            status=str(data.get("status") or SCHEDULER_STATUS_QUEUED),
            priority=_safe_int(data.get("priority"), SCHEDULER_PRIORITY_NORMAL),
            ready_tick=_safe_int(data.get("ready_tick"), 0),
            attempts=_safe_int(data.get("attempts"), 0),
            max_attempts=max(1, _safe_int(data.get("max_attempts"), 3)),
            mainline_result=_copy_dict(data.get("mainline_result")),
            continuation_ref=_copy_dict(data.get("continuation_ref")),
            recovery_ref=_copy_dict(data.get("recovery_ref")),
            authority_ref=_copy_dict(data.get("authority_ref")),
            metadata=_copy_dict(data.get("metadata")),
            created_at=str(data.get("created_at") or utc_timestamp()),
            updated_at=str(data.get("updated_at") or utc_timestamp()),
        )


@dataclass(frozen=True)
class RuntimeNativeSchedulerEvent:
    event_id: str
    event_type: str
    schedule_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "schedule_id": self.schedule_id,
            "payload": copy.deepcopy(self.payload),
            "metadata": copy.deepcopy(self.metadata),
            "timestamp": self.timestamp,
            "source": "runtime_native_scheduler",
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimeNativeSchedulerEvent":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            event_id=str(data.get("event_id") or ""),
            event_type=str(data.get("event_type") or ""),
            schedule_id=str(data.get("schedule_id") or ""),
            payload=_copy_dict(data.get("payload")),
            metadata=_copy_dict(data.get("metadata")),
            timestamp=str(data.get("timestamp") or utc_timestamp()),
        )


class RuntimeNativeSchedulerRejected(RuntimeError):
    pass


PlannerFn = Callable[[str, dict[str, Any]], dict[str, Any]]
StepRunnerFn = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class RuntimeNativeScheduler:
    """
    Runtime-native scheduler migration adapter.

    This does not rewrite legacy scheduler.py. It provides the migration surface:
      - schedule user goals into runtime-native mainline
      - preserve session/runtime/owner propagation
      - run recovery-aware scheduling
      - expose continuation/recovery refs
      - persist queue and results
    """

    def __init__(
        self,
        *,
        storage_path: str | Path | None = None,
        mainline: Any,
        ownership_fabric: Any = None,
        supervisor_bridge: Any = None,
        journal: Any = None,
        audit: Any = None,
    ) -> None:
        if mainline is None:
            raise RuntimeNativeSchedulerRejected("runtime_native_mainline_required")
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self.mainline = mainline
        self.ownership_fabric = ownership_fabric or getattr(mainline, "ownership_fabric", None)
        self.supervisor_bridge = supervisor_bridge or getattr(mainline, "supervisor_bridge", None)
        self.journal = journal
        self.audit = audit
        self.persistence_service = RuntimePersistenceService(
            workspace_root=(self.storage_path.parent if self.storage_path is not None else "workspace"),
            source="runtime_native_scheduler",
        )
        self._items: dict[str, RuntimeNativeScheduleItem] = {}
        self._order: list[str] = []
        self._events: list[RuntimeNativeSchedulerEvent] = []
        if self.storage_path is not None:
            self.load()

    @classmethod
    def with_workspace(
        cls,
        workspace_root: str | Path = "workspace",
        **kwargs: Any,
    ) -> "RuntimeNativeScheduler":
        root = Path(workspace_root)
        scheduler_dir = root / "runtime_native_scheduler"
        scheduler_dir.mkdir(parents=True, exist_ok=True)
        return cls(storage_path=scheduler_dir / "runtime_native_scheduler.json", **kwargs)

    def schedule_goal(
        self,
        *,
        goal: str,
        source_session_id: str = "",
        runtime_id: str = "",
        owner_id: str = "",
        task_id: str = "",
        priority: int = SCHEDULER_PRIORITY_NORMAL,
        ready_tick: int = 0,
        max_attempts: int = 3,
        metadata: dict[str, Any] | None = None,
        schedule_id: str | None = None,
    ) -> RuntimeNativeScheduleItem:
        goal = self._validate_text("goal", goal)
        mainline_config = getattr(self.mainline, "config", None)
        source_session_id = str(source_session_id or getattr(mainline_config, "source_session_id", "") or "")
        runtime_id = str(runtime_id or getattr(mainline_config, "runtime_id", "") or "")
        owner_id = str(owner_id or getattr(mainline_config, "owner_id", "") or "")

        if schedule_id is None:
            schedule_id = "runtime-native-schedule-" + stable_scheduler_fingerprint(
                {
                    "goal": goal,
                    "source_session_id": source_session_id,
                    "runtime_id": runtime_id,
                    "task_id": task_id,
                    "sequence": len(self._order) + 1,
                }
            )[:16]
        schedule_id = self._validate_text("schedule_id", schedule_id)

        if schedule_id in self._items:
            raise RuntimeNativeSchedulerRejected(f"schedule already exists: {schedule_id!r}")

        item = RuntimeNativeScheduleItem(
            schedule_id=schedule_id,
            goal=goal,
            source_session_id=source_session_id,
            runtime_id=runtime_id,
            owner_id=owner_id,
            task_id=str(task_id or ""),
            priority=int(priority),
            ready_tick=int(ready_tick),
            max_attempts=max(1, int(max_attempts)),
            metadata=copy.deepcopy(metadata or {}),
        )
        self._items[schedule_id] = item
        self._order.append(schedule_id)
        self._append_event(
            "runtime_native_schedule_queued",
            schedule_id=schedule_id,
            payload={"item": item.to_dict()},
        )
        self.save()
        return copy.deepcopy(item)

    def ready_items(self, *, current_tick: int, limit: int = 10) -> list[RuntimeNativeScheduleItem]:
        queued = [
            item for item in self._items.values()
            if item.status == SCHEDULER_STATUS_QUEUED and item.ready_tick <= int(current_tick)
        ]
        queued.sort(key=lambda item: (-item.priority, item.created_at, item.schedule_id))
        return [copy.deepcopy(item) for item in queued[:max(1, int(limit))]]

    def run_ready(
        self,
        *,
        current_tick: int,
        limit: int = 10,
        planner_fn: PlannerFn | None = None,
        step_runner: StepRunnerFn | None = None,
        resume_runner: StepRunnerFn | None = None,
    ) -> list[RuntimeNativeScheduleItem]:
        results = []
        for item in self.ready_items(current_tick=current_tick, limit=limit):
            results.append(
                self.run_item(
                    item.schedule_id,
                    current_tick=current_tick,
                    planner_fn=planner_fn,
                    step_runner=step_runner,
                    resume_runner=resume_runner,
                )
            )
        return results

    def run_item(
        self,
        schedule_id: str,
        *,
        current_tick: int,
        planner_fn: PlannerFn | None = None,
        step_runner: StepRunnerFn | None = None,
        resume_runner: StepRunnerFn | None = None,
    ) -> RuntimeNativeScheduleItem:
        item = self.get_item(schedule_id)
        if item.status not in {SCHEDULER_STATUS_QUEUED, SCHEDULER_STATUS_RECOVERY_QUEUED, SCHEDULER_STATUS_CONTINUATION_READY}:
            raise RuntimeNativeSchedulerRejected(f"schedule cannot run from status: {item.status!r}")

        running = self._replace_item(
            item,
            status=SCHEDULER_STATUS_RUNNING,
            attempts=item.attempts + 1,
        )
        self._append_event(
            "runtime_native_schedule_running",
            schedule_id=schedule_id,
            payload={"item": running.to_dict()},
        )

        try:
            result = self.mainline.run_goal(
                running.goal,
                planner_fn=planner_fn,
                step_runner=step_runner,
                resume_runner=resume_runner,
                current_tick=current_tick,
                task_id=running.task_id,
                metadata={
                    **copy.deepcopy(running.metadata),
                    "schedule_id": schedule_id,
                    "scheduler_source_session_id": running.source_session_id,
                    "scheduler_runtime_id": running.runtime_id,
                    "scheduler_owner_id": running.owner_id,
                },
            )
            result_payload = result.to_dict() if hasattr(result, "to_dict") else copy.deepcopy(result)
        except Exception as exc:
            result_payload = {
                "status": SCHEDULER_STATUS_FAILED,
                "final_result": {"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}},
            }

        status = str(result_payload.get("status") or "")
        if status == "completed":
            final_status = SCHEDULER_STATUS_COMPLETED
        elif status == "blocked":
            final_status = SCHEDULER_STATUS_BLOCKED
        elif running.attempts + 1 >= running.max_attempts:
            final_status = SCHEDULER_STATUS_FAILED
        else:
            final_status = SCHEDULER_STATUS_QUEUED

        loop_record = _copy_dict(result_payload.get("loop_record"))
        task_record = _copy_dict(loop_record.get("task"))
        continuation_ref = _copy_dict(task_record.get("continuation_ref"))
        recovery_ref = _copy_dict(task_record.get("recovery_ref"))

        recovery_ticket = _copy_dict(recovery_ref.get("recovery_ticket"))
        ticket_id = str(recovery_ticket.get("ticket_id") or "")
        if ticket_id:
            try:
                latest_ticket = self.mainline.orchestrator.queue.get_ticket(ticket_id)
                if hasattr(latest_ticket, "to_dict"):
                    recovery_ref["recovery_ticket"] = latest_ticket.to_dict()
            except Exception:
                pass

        updated = self._replace_item(
            running,
            status=final_status,
            mainline_result=result_payload,
            continuation_ref=continuation_ref,
            recovery_ref=recovery_ref,
            authority_ref=_copy_dict(result_payload.get("authority_decision")),
        )

        self._append_event(
            "runtime_native_schedule_completed",
            schedule_id=schedule_id,
            payload={"item": updated.to_dict()},
        )
        self.save()
        return copy.deepcopy(updated)

    def get_item(self, schedule_id: str) -> RuntimeNativeScheduleItem:
        schedule_id = self._validate_text("schedule_id", schedule_id)
        item = self._items.get(schedule_id)
        if item is None:
            raise RuntimeNativeSchedulerRejected(f"schedule does not exist: {schedule_id!r}")
        return copy.deepcopy(item)

    def list_items(self) -> list[RuntimeNativeScheduleItem]:
        return [copy.deepcopy(self._items[item_id]) for item_id in self._order if item_id in self._items]

    def list_events(self) -> list[RuntimeNativeSchedulerEvent]:
        return [copy.deepcopy(event) for event in self._events]

    def health(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for item in self._items.values():
            counts[item.status] = counts.get(item.status, 0) + 1
        return {
            "ok": True,
            "runtime_phase": "runtime_native_scheduler_health",
            "items": len(self._items),
            "counts": counts,
            "events": len(self._events),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_phase": "runtime_native_scheduler",
            "items": [self._items[item_id].to_dict() for item_id in self._order if item_id in self._items],
            "events": [event.to_dict() for event in self._events[-500:]],
        }

    def load(self) -> None:
        if self.storage_path is None or not self.storage_path.exists():
            return
        payload = self.persistence_service.read_json(
            self.storage_path,
            default={},
        )
        self._items = {}
        self._order = []
        self._events = []
        if not isinstance(payload, dict):
            return

        for item in payload.get("items") or []:
            if isinstance(item, dict):
                schedule_item = RuntimeNativeScheduleItem.from_dict(item)
                if schedule_item.schedule_id:
                    self._items[schedule_item.schedule_id] = schedule_item
                    self._order.append(schedule_item.schedule_id)

        for item in payload.get("events") or []:
            if isinstance(item, dict):
                event = RuntimeNativeSchedulerEvent.from_dict(item)
                if event.event_id:
                    self._events.append(event)

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.persistence_service.write_json(
            self.storage_path,
            self.to_dict(),
            reason="runtime_native_scheduler_save",
            metadata={"runtime_native_scheduler": True},
        )

    def _replace_item(self, item: RuntimeNativeScheduleItem, **updates: Any) -> RuntimeNativeScheduleItem:
        latest = self._items.get(item.schedule_id, item)
        payload = latest.to_dict()
        payload.update(copy.deepcopy(updates))
        payload["updated_at"] = utc_timestamp()
        updated = RuntimeNativeScheduleItem.from_dict(payload)
        self._items[updated.schedule_id] = updated
        self.save()
        return copy.deepcopy(updated)

    def _append_event(
        self,
        event_type: str,
        *,
        schedule_id: str = "",
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event_id = "runtime-native-scheduler-event-" + stable_scheduler_fingerprint(
            {
                "event_type": event_type,
                "schedule_id": schedule_id,
                "sequence": len(self._events) + 1,
            }
        )[:16]
        event = RuntimeNativeSchedulerEvent(
            event_id=event_id,
            event_type=event_type,
            schedule_id=str(schedule_id or ""),
            payload=copy.deepcopy(payload or {}),
            metadata=copy.deepcopy(metadata or {}),
        )
        self._events.append(event)

        for target in (self.audit, self.journal):
            if target is None:
                continue
            try:
                if hasattr(target, "append"):
                    target.append(event.to_dict())
                elif hasattr(target, "record_event"):
                    target.record_event(event.to_dict())
                elif hasattr(target, "record"):
                    target.record(event.to_dict())
                elif hasattr(target, "append_record"):
                    target.append_record("runtime_native_scheduler", event.to_dict())
            except Exception:
                pass

    def _validate_text(self, field_name: str, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise RuntimeNativeSchedulerRejected(f"{field_name}_required")
        return text
