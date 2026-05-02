from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List


WORKER_TASK_FIELDS = {
    "task_id",
    "parent_task_id",
    "role",
    "objective",
    "input_context",
}

WORKER_FORBIDDEN_STRATEGY_FIELDS = {
    "constraints",
    "expected_output",
    "retry_policy",
    "policy",
    "strategy",
    "planner_decision",
}

PARENT_TASK_FIELDS = {
    "task_id",
    "objective",
    "input_context",
    "decomposition_mode",
}

WORKER_RESULT_FIELDS = {
    "task_id",
    "status",
    "summary",
    "result",
    "artifacts",
    "trace",
    "open_questions",
    "confidence",
}

WORKER_RESULT_STATUSES = {"success", "partial", "failed", "blocked"}

WORKER_STATE_SNAPSHOT_FIELDS = {
    "active_tasks",
    "completed_tasks",
    "blocked_tasks",
    "artifacts_index",
    "last_decision",
    "handoff_notes",
}

AGGREGATION_STRATEGIES = {"concat", "select", "synthesize"}
AGGREGATION_CONFLICT_HANDLING = {"preserve_all", "prefer_success", "mark_conflict"}
AGGREGATION_FALLBACKS = {"partial_success", "fail_closed"}

AGGREGATION_CONTRACT_FIELDS = {
    "strategy",
    "conflict_handling",
    "fallback",
}

FINAL_RESULT_FIELDS = {
    "status",
    "summary",
    "result",
    "artifacts",
    "trace",
    "open_questions",
    "confidence",
    "source_task_ids",
    "aggregation",
}

SCHEDULER_QUEUE_STATUSES = {"pending", "running", "done", "failed"}

SCHEDULER_QUEUE_ITEM_FIELDS = {
    "task",
    "status",
    "attempts",
    "max_retries",
    "last_result",
}

SCHEDULER_STATE_FIELDS = {
    "queue",
    "done",
    "failed",
    "tick_count",
    "last_event",
}


@dataclass(frozen=True)
class ParentTask:
    task_id: str
    objective: str = ""
    input_context: Dict[str, Any] = field(default_factory=dict)
    decomposition_mode: str = "manual"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "objective": self.objective,
            "input_context": copy.deepcopy(self.input_context),
            "decomposition_mode": self.decomposition_mode,
        }


@dataclass(frozen=True)
class WorkerTask:
    task_id: str
    parent_task_id: str = ""
    role: str = "worker"
    objective: str = ""
    input_context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "parent_task_id": self.parent_task_id,
            "role": self.role,
            "objective": self.objective,
            "input_context": copy.deepcopy(self.input_context),
        }


@dataclass(frozen=True)
class WorkerResult:
    task_id: str
    status: str = "success"
    summary: str = ""
    result: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    trace: List[Dict[str, Any]] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "summary": self.summary,
            "result": copy.deepcopy(self.result),
            "artifacts": copy.deepcopy(self.artifacts),
            "trace": copy.deepcopy(self.trace),
            "open_questions": copy.deepcopy(self.open_questions),
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class WorkerStateSnapshot:
    active_tasks: List[Dict[str, Any]] = field(default_factory=list)
    completed_tasks: List[Dict[str, Any]] = field(default_factory=list)
    blocked_tasks: List[Dict[str, Any]] = field(default_factory=list)
    artifacts_index: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    last_decision: str = ""
    handoff_notes: str = ""
    snapshot_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_tasks": copy.deepcopy(self.active_tasks),
            "completed_tasks": copy.deepcopy(self.completed_tasks),
            "blocked_tasks": copy.deepcopy(self.blocked_tasks),
            "artifacts_index": copy.deepcopy(self.artifacts_index),
            "last_decision": self.last_decision,
            "handoff_notes": self.handoff_notes,
            "snapshot_at": self.snapshot_at,
        }


@dataclass(frozen=True)
class AggregationContract:
    strategy: str = "concat"
    conflict_handling: str = "preserve_all"
    fallback: str = "partial_success"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "conflict_handling": self.conflict_handling,
            "fallback": self.fallback,
        }


@dataclass(frozen=True)
class FinalResult:
    status: str
    summary: str = ""
    result: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    trace: List[Dict[str, Any]] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    confidence: float = 0.0
    source_task_ids: List[str] = field(default_factory=list)
    aggregation: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "result": copy.deepcopy(self.result),
            "artifacts": copy.deepcopy(self.artifacts),
            "trace": copy.deepcopy(self.trace),
            "open_questions": copy.deepcopy(self.open_questions),
            "confidence": self.confidence,
            "source_task_ids": copy.deepcopy(self.source_task_ids),
            "aggregation": copy.deepcopy(self.aggregation),
        }


@dataclass(frozen=True)
class SchedulerQueueItem:
    task: Dict[str, Any]
    status: str = "pending"
    attempts: int = 0
    max_retries: int = 0
    last_result: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": copy.deepcopy(self.task),
            "status": self.status,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "last_result": copy.deepcopy(self.last_result),
        }


@dataclass(frozen=True)
class SchedulerState:
    queue: List[Dict[str, Any]] = field(default_factory=list)
    done: List[Dict[str, Any]] = field(default_factory=list)
    failed: List[Dict[str, Any]] = field(default_factory=list)
    tick_count: int = 0
    last_event: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "queue": copy.deepcopy(self.queue),
            "done": copy.deepcopy(self.done),
            "failed": copy.deepcopy(self.failed),
            "tick_count": self.tick_count,
            "last_event": self.last_event,
        }


def create_worker_task(
    *,
    task_id: str,
    parent_task_id: str = "",
    role: str = "worker",
    objective: str = "",
    input_context: Dict[str, Any] | None = None,
    **strategy_fields: Any,
) -> WorkerTask:
    forbidden = sorted(key for key in strategy_fields if key in WORKER_FORBIDDEN_STRATEGY_FIELDS)
    if forbidden:
        raise ValueError(f"worker_task cannot contain strategy fields: {forbidden}")

    task = WorkerTask(
        task_id=_required_text("task_id", task_id),
        parent_task_id=str(parent_task_id or "").strip(),
        role=str(role or "worker").strip(),
        objective=_required_text("objective", objective),
        input_context=copy.deepcopy(input_context) if isinstance(input_context, dict) else {},
    )
    ensure_worker_task_contract(task.to_dict())
    return task


def create_parent_task(
    *,
    task_id: str,
    objective: str = "",
    input_context: Dict[str, Any] | None = None,
    decomposition_mode: str = "manual",
) -> ParentTask:
    normalized_mode = str(decomposition_mode or "manual").strip().lower()
    if normalized_mode != "manual":
        raise ValueError("parent_task decomposition_mode must be manual")

    task = ParentTask(
        task_id=_required_text("task_id", task_id),
        objective=_required_text("objective", objective),
        input_context=copy.deepcopy(input_context) if isinstance(input_context, dict) else {},
        decomposition_mode=normalized_mode,
    )
    ensure_parent_task_contract(task.to_dict())
    return task


def create_worker_result(
    *,
    task_id: str,
    status: str = "success",
    summary: str = "",
    result: Dict[str, Any] | None = None,
    artifacts: List[Dict[str, Any]] | None = None,
    trace: List[Dict[str, Any]] | None = None,
    open_questions: List[str] | None = None,
    confidence: float = 1.0,
) -> WorkerResult:
    normalized_status = str(status or "success").strip().lower()
    if normalized_status not in WORKER_RESULT_STATUSES:
        normalized_status = "failed"

    worker_result = WorkerResult(
        task_id=_required_text("task_id", task_id),
        status=normalized_status,
        summary=str(summary or "").strip(),
        result=copy.deepcopy(result) if isinstance(result, dict) else {},
        artifacts=[copy.deepcopy(item) for item in artifacts or [] if isinstance(item, dict)],
        trace=[copy.deepcopy(item) for item in trace or [] if isinstance(item, dict)],
        open_questions=[str(item).strip() for item in open_questions or [] if str(item).strip()],
        confidence=_clamp_confidence(confidence),
    )
    ensure_worker_result_contract(worker_result.to_dict())
    return worker_result


def create_worker_state_snapshot(
    *,
    active_tasks: List[Dict[str, Any]] | None = None,
    completed_tasks: List[Dict[str, Any]] | None = None,
    blocked_tasks: List[Dict[str, Any]] | None = None,
    artifacts_index: Dict[str, List[Dict[str, Any]]] | None = None,
    last_decision: str = "",
    handoff_notes: str = "",
) -> WorkerStateSnapshot:
    snapshot = WorkerStateSnapshot(
        active_tasks=[copy.deepcopy(item) for item in active_tasks or [] if isinstance(item, dict)],
        completed_tasks=[copy.deepcopy(item) for item in completed_tasks or [] if isinstance(item, dict)],
        blocked_tasks=[copy.deepcopy(item) for item in blocked_tasks or [] if isinstance(item, dict)],
        artifacts_index=_normalize_artifacts_index(artifacts_index),
        last_decision=str(last_decision or "").strip(),
        handoff_notes=str(handoff_notes or "").strip(),
    )
    ensure_worker_state_snapshot_contract(snapshot.to_dict())
    return snapshot


def create_aggregation_contract(
    *,
    strategy: str = "concat",
    conflict_handling: str = "preserve_all",
    fallback: str = "partial_success",
) -> AggregationContract:
    contract = AggregationContract(
        strategy=_normalize_choice("strategy", strategy, AGGREGATION_STRATEGIES),
        conflict_handling=_normalize_choice(
            "conflict_handling",
            conflict_handling,
            AGGREGATION_CONFLICT_HANDLING,
        ),
        fallback=_normalize_choice("fallback", fallback, AGGREGATION_FALLBACKS),
    )
    ensure_aggregation_contract(contract.to_dict())
    return contract


def create_final_result(
    *,
    status: str,
    summary: str = "",
    result: Dict[str, Any] | None = None,
    artifacts: List[Dict[str, Any]] | None = None,
    trace: List[Dict[str, Any]] | None = None,
    open_questions: List[str] | None = None,
    confidence: float = 0.0,
    source_task_ids: List[str] | None = None,
    aggregation: Dict[str, Any] | None = None,
) -> FinalResult:
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in WORKER_RESULT_STATUSES:
        normalized_status = "failed"

    final_result = FinalResult(
        status=normalized_status,
        summary=str(summary or "").strip(),
        result=copy.deepcopy(result) if isinstance(result, dict) else {},
        artifacts=[copy.deepcopy(item) for item in artifacts or [] if isinstance(item, dict)],
        trace=[copy.deepcopy(item) for item in trace or [] if isinstance(item, dict)],
        open_questions=[str(item).strip() for item in open_questions or [] if str(item).strip()],
        confidence=_clamp_confidence(confidence),
        source_task_ids=[str(item).strip() for item in source_task_ids or [] if str(item).strip()],
        aggregation=copy.deepcopy(aggregation) if isinstance(aggregation, dict) else {},
    )
    ensure_final_result_contract(final_result.to_dict())
    return final_result


def create_scheduler_queue_item(
    *,
    task: Dict[str, Any],
    status: str = "pending",
    attempts: int = 0,
    max_retries: int = 0,
    last_result: Dict[str, Any] | None = None,
) -> SchedulerQueueItem:
    task_payload = ensure_worker_task_contract(task)
    normalized_status = _normalize_choice("status", status, SCHEDULER_QUEUE_STATUSES)
    item = SchedulerQueueItem(
        task=task_payload,
        status=normalized_status,
        attempts=max(0, int(attempts or 0)),
        max_retries=max(0, int(max_retries or 0)),
        last_result=copy.deepcopy(last_result) if isinstance(last_result, dict) else {},
    )
    ensure_scheduler_queue_item_contract(item.to_dict())
    return item


def create_scheduler_state(
    *,
    queue: List[Dict[str, Any]] | None = None,
    done: List[Dict[str, Any]] | None = None,
    failed: List[Dict[str, Any]] | None = None,
    tick_count: int = 0,
    last_event: str = "",
) -> SchedulerState:
    state = SchedulerState(
        queue=[ensure_scheduler_queue_item_contract(item) for item in queue or [] if isinstance(item, dict)],
        done=[ensure_scheduler_queue_item_contract(item) for item in done or [] if isinstance(item, dict)],
        failed=[ensure_scheduler_queue_item_contract(item) for item in failed or [] if isinstance(item, dict)],
        tick_count=max(0, int(tick_count or 0)),
        last_event=str(last_event or "").strip(),
    )
    ensure_scheduler_state_contract(state.to_dict())
    return state


def ensure_worker_task_contract(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("worker_task must be a dict")

    forbidden = sorted(key for key in payload if key in WORKER_FORBIDDEN_STRATEGY_FIELDS)
    if forbidden:
        raise ValueError(f"worker_task cannot contain strategy fields: {forbidden}")

    extra = sorted(key for key in payload if key not in WORKER_TASK_FIELDS)
    if extra:
        raise ValueError(f"worker_task contains unknown fields: {extra}")

    for key in ("task_id", "objective"):
        if not str(payload.get(key) or "").strip():
            raise ValueError(f"worker_task missing required field: {key}")

    if not isinstance(payload.get("input_context"), dict):
        raise ValueError("worker_task.input_context must be a dict")

    return copy.deepcopy(payload)


def ensure_parent_task_contract(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("parent_task must be a dict")

    extra = sorted(key for key in payload if key not in PARENT_TASK_FIELDS)
    if extra:
        raise ValueError(f"parent_task contains unknown fields: {extra}")

    for key in ("task_id", "objective"):
        if not str(payload.get(key) or "").strip():
            raise ValueError(f"parent_task missing required field: {key}")

    if not isinstance(payload.get("input_context"), dict):
        raise ValueError("parent_task.input_context must be a dict")

    mode = str(payload.get("decomposition_mode") or "").strip().lower()
    if mode != "manual":
        raise ValueError("parent_task.decomposition_mode must be manual")

    return copy.deepcopy(payload)


def ensure_worker_result_contract(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("worker_result must be a dict")

    missing = sorted(key for key in WORKER_RESULT_FIELDS if key not in payload)
    if missing:
        raise ValueError(f"worker_result missing fields: {missing}")

    status = str(payload.get("status") or "").strip().lower()
    if status not in WORKER_RESULT_STATUSES:
        raise ValueError(f"worker_result.status is invalid: {status}")

    if not str(payload.get("task_id") or "").strip():
        raise ValueError("worker_result missing required field: task_id")

    if not isinstance(payload.get("result"), dict):
        raise ValueError("worker_result.result must be a dict")
    if not isinstance(payload.get("artifacts"), list):
        raise ValueError("worker_result.artifacts must be a list")
    if not isinstance(payload.get("trace"), list):
        raise ValueError("worker_result.trace must be a list")
    if not isinstance(payload.get("open_questions"), list):
        raise ValueError("worker_result.open_questions must be a list")

    return copy.deepcopy(payload)


def ensure_worker_state_snapshot_contract(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("worker_state_snapshot must be a dict")

    missing = sorted(key for key in WORKER_STATE_SNAPSHOT_FIELDS if key not in payload)
    if missing:
        raise ValueError(f"worker_state_snapshot missing fields: {missing}")

    for key in ("active_tasks", "completed_tasks", "blocked_tasks"):
        if not isinstance(payload.get(key), list):
            raise ValueError(f"worker_state_snapshot.{key} must be a list")

    if not isinstance(payload.get("artifacts_index"), dict):
        raise ValueError("worker_state_snapshot.artifacts_index must be a dict")

    return copy.deepcopy(payload)


def ensure_aggregation_contract(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("aggregation_contract must be a dict")

    missing = sorted(key for key in AGGREGATION_CONTRACT_FIELDS if key not in payload)
    if missing:
        raise ValueError(f"aggregation_contract missing fields: {missing}")

    _normalize_choice("strategy", payload.get("strategy"), AGGREGATION_STRATEGIES)
    _normalize_choice(
        "conflict_handling",
        payload.get("conflict_handling"),
        AGGREGATION_CONFLICT_HANDLING,
    )
    _normalize_choice("fallback", payload.get("fallback"), AGGREGATION_FALLBACKS)
    return copy.deepcopy(payload)


def ensure_final_result_contract(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("final_result must be a dict")

    missing = sorted(key for key in FINAL_RESULT_FIELDS if key not in payload)
    if missing:
        raise ValueError(f"final_result missing fields: {missing}")

    status = str(payload.get("status") or "").strip().lower()
    if status not in WORKER_RESULT_STATUSES:
        raise ValueError(f"final_result.status is invalid: {status}")

    if not isinstance(payload.get("result"), dict):
        raise ValueError("final_result.result must be a dict")
    if not isinstance(payload.get("artifacts"), list):
        raise ValueError("final_result.artifacts must be a list")
    if not isinstance(payload.get("trace"), list):
        raise ValueError("final_result.trace must be a list")
    if not isinstance(payload.get("open_questions"), list):
        raise ValueError("final_result.open_questions must be a list")
    if not isinstance(payload.get("source_task_ids"), list):
        raise ValueError("final_result.source_task_ids must be a list")
    if not isinstance(payload.get("aggregation"), dict):
        raise ValueError("final_result.aggregation must be a dict")

    return copy.deepcopy(payload)


def ensure_scheduler_queue_item_contract(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("scheduler_queue_item must be a dict")

    missing = sorted(key for key in SCHEDULER_QUEUE_ITEM_FIELDS if key not in payload)
    if missing:
        raise ValueError(f"scheduler_queue_item missing fields: {missing}")

    ensure_worker_task_contract(payload.get("task"))
    _normalize_choice("status", payload.get("status"), SCHEDULER_QUEUE_STATUSES)

    try:
        attempts = int(payload.get("attempts") or 0)
        max_retries = int(payload.get("max_retries") or 0)
    except Exception as exc:
        raise ValueError(f"scheduler_queue_item attempts/max_retries must be integers: {exc}") from exc

    if attempts < 0 or max_retries < 0:
        raise ValueError("scheduler_queue_item attempts/max_retries must be >= 0")
    if not isinstance(payload.get("last_result"), dict):
        raise ValueError("scheduler_queue_item.last_result must be a dict")

    return copy.deepcopy(payload)


def ensure_scheduler_state_contract(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("scheduler_state must be a dict")

    missing = sorted(key for key in SCHEDULER_STATE_FIELDS if key not in payload)
    if missing:
        raise ValueError(f"scheduler_state missing fields: {missing}")

    for key in ("queue", "done", "failed"):
        value = payload.get(key)
        if not isinstance(value, list):
            raise ValueError(f"scheduler_state.{key} must be a list")
        for item in value:
            ensure_scheduler_queue_item_contract(item)

    try:
        tick_count = int(payload.get("tick_count") or 0)
    except Exception as exc:
        raise ValueError(f"scheduler_state.tick_count must be an integer: {exc}") from exc
    if tick_count < 0:
        raise ValueError("scheduler_state.tick_count must be >= 0")

    return copy.deepcopy(payload)


def _required_text(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _clamp_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except Exception:
        confidence = 0.0
    return max(0.0, min(1.0, confidence))


def _normalize_artifacts_index(value: Any) -> Dict[str, List[Dict[str, Any]]]:
    if not isinstance(value, dict):
        return {}

    normalized: Dict[str, List[Dict[str, Any]]] = {}
    for key, items in value.items():
        if not isinstance(items, list):
            continue
        normalized[str(key)] = [copy.deepcopy(item) for item in items if isinstance(item, dict)]
    return normalized


def _normalize_choice(name: str, value: Any, allowed: set[str]) -> str:
    text = str(value or "").strip().lower()
    if text not in allowed:
        raise ValueError(f"{name} must be one of {sorted(allowed)}")
    return text
