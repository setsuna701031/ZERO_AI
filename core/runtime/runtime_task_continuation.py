from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from core.runtime.runtime_session_resume import (
    RESUMABLE_TASK_STATUSES,
    TASK_STATUS_BLOCKED,
    TASK_STATUS_REVIEW_REQUIRED,
    build_runtime_resume_plan,
    extract_task_id,
    is_resumable_task_status,
    normalize_task_status,
    stable_resume_fingerprint,
)

CONTINUATION_ACTION_REQUEUE = "requeue"
CONTINUATION_ACTION_WAIT = "wait"
CONTINUATION_ACTION_SKIP = "skip"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RuntimeTaskContinuationDecision:
    task_id: str
    status: str
    action: str
    reason: str
    task: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeTaskContinuationPlan:
    ok: bool
    decisions: list[RuntimeTaskContinuationDecision]
    requeue_task_ids: list[str]
    waiting_task_ids: list[str]
    skipped_task_ids: list[str]
    fingerprint: str
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "decisions": [item.to_dict() for item in self.decisions],
            "requeue_task_ids": list(self.requeue_task_ids),
            "waiting_task_ids": list(self.waiting_task_ids),
            "skipped_task_ids": list(self.skipped_task_ids),
            "fingerprint": self.fingerprint,
            "created_at": self.created_at,
        }


class RuntimeTaskContinuation:
    """Convert resume candidates into scheduler-safe continuation decisions.

    Boundary:
    - Requeue runnable non-terminal tasks.
    - Preserve blocked/review tasks as waiting.
    - Skip terminal or unknown non-resumable tasks.
    - Do not execute, mutate, or mark repository state directly.
    """

    def build_plan(self, tasks: Iterable[Mapping[str, Any]]) -> RuntimeTaskContinuationPlan:
        decisions: list[RuntimeTaskContinuationDecision] = []
        for task in tasks or []:
            if not isinstance(task, Mapping):
                continue
            task_id = extract_task_id(task)
            status = normalize_task_status(task.get("status"))
            task_copy = copy.deepcopy(dict(task))
            if not task_id:
                task_id = "task:" + stable_resume_fingerprint(task_copy)[:16]
                task_copy.setdefault("task_id", task_id)

            if status in {TASK_STATUS_BLOCKED, TASK_STATUS_REVIEW_REQUIRED}:
                decision = RuntimeTaskContinuationDecision(
                    task_id=task_id,
                    status=status,
                    action=CONTINUATION_ACTION_WAIT,
                    reason="blocked_or_review_required_task_must_remain_waiting",
                    task=task_copy,
                )
            elif is_resumable_task_status(status):
                decision = RuntimeTaskContinuationDecision(
                    task_id=task_id,
                    status=status,
                    action=CONTINUATION_ACTION_REQUEUE,
                    reason="resumable_non_terminal_task",
                    task=task_copy,
                )
            else:
                decision = RuntimeTaskContinuationDecision(
                    task_id=task_id,
                    status=status,
                    action=CONTINUATION_ACTION_SKIP,
                    reason="terminal_or_non_resumable_task",
                    task=task_copy,
                )
            decisions.append(decision)

        requeue = [item.task_id for item in decisions if item.action == CONTINUATION_ACTION_REQUEUE]
        waiting = [item.task_id for item in decisions if item.action == CONTINUATION_ACTION_WAIT]
        skipped = [item.task_id for item in decisions if item.action == CONTINUATION_ACTION_SKIP]
        fingerprint = stable_resume_fingerprint([item.to_dict() for item in decisions])
        return RuntimeTaskContinuationPlan(
            ok=bool(requeue or waiting),
            decisions=decisions,
            requeue_task_ids=requeue,
            waiting_task_ids=waiting,
            skipped_task_ids=skipped,
            fingerprint=fingerprint,
        )


def build_task_continuation_plan(tasks: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    return RuntimeTaskContinuation().build_plan(tasks).to_dict()


def build_persistent_task_resume_and_continuation(tasks: Iterable[Mapping[str, Any]], *, workspace_root: str = ".", storage_path: str | None = None, session_id: str | None = None) -> dict[str, Any]:
    task_list = [copy.deepcopy(dict(item)) for item in tasks or [] if isinstance(item, Mapping)]
    resume_plan = build_runtime_resume_plan(task_list, workspace_root=workspace_root, storage_path=storage_path, session_id=session_id)
    continuation_plan = build_task_continuation_plan(task_list)
    return {
        "ok": bool(resume_plan.get("ok") or continuation_plan.get("ok")),
        "resume_plan": resume_plan,
        "continuation_plan": continuation_plan,
        "resumable_statuses": sorted(RESUMABLE_TASK_STATUSES),
        "fingerprint": stable_resume_fingerprint({"resume_plan": resume_plan, "continuation_plan": continuation_plan}),
        "created_at": utc_timestamp(),
    }
