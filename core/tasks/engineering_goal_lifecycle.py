from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any, Mapping


GOAL_LIFECYCLE_SCHEMA = "zero.engineering_task.goal_lifecycle.v1"
GOAL_STATE_SCHEMA = "zero.engineering_task.goal_state.v1"


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _safe_state_id(value: Any) -> str:
    text = _clean_text(value, "engineering_goal")
    safe = []
    for char in text:
        if char.isalnum() or char in ("-", "_", "."):
            safe.append(char)
        else:
            safe.append("_")
    cleaned = "".join(safe).strip("._-")
    return cleaned[:120] or "engineering_goal"


def lifecycle_enabled(payload: Mapping[str, Any]) -> bool:
    task = payload.get("package") if isinstance(payload.get("package"), Mapping) else payload
    if not isinstance(task, Mapping):
        return False
    return bool(
        task.get("engineering_goal_lifecycle")
        or task.get("goal_lifecycle")
        or task.get("manage_engineering_goal")
    )


def _task_id(step: Mapping[str, Any], index: int) -> str:
    return _clean_text(step.get("package_id") or step.get("task_id"), f"goal_task_{index}")


def _task_summary(step: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {
        "task_id": _task_id(step, index),
        "goal": _clean_text(step.get("goal") or step.get("title"), _task_id(step, index)),
        "step_index": index,
    }


def _task_bucket_record(step: Mapping[str, Any], index: int) -> dict[str, Any]:
    return {
        "summary": _task_summary(step, index),
        "task_payload": copy.deepcopy(dict(step)),
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _memory_refs(relevant_memory: Mapping[str, Any], memory_record: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for record in relevant_memory.get("records") if isinstance(relevant_memory.get("records"), list) else []:
        if not isinstance(record, Mapping):
            continue
        refs.append(
            {
                "memory_id": _clean_text(record.get("memory_id")),
                "task_id": _clean_text(record.get("task_id")),
                "source": "retrieved_memory",
            }
        )
    if isinstance(memory_record, Mapping) and memory_record:
        refs.append(
            {
                "memory_id": _clean_text(memory_record.get("memory_id")),
                "task_id": _clean_text(memory_record.get("task_id")),
                "source": "updated_memory",
            }
        )
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for ref in refs:
        key = (ref["memory_id"], ref["task_id"], ref["source"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(ref)
    return unique


class EngineeringGoalLifecycle:
    """State-only lifecycle manager for long-running engineering goals."""

    def __init__(
        self,
        *,
        repo_root: str | Path,
        payload: Mapping[str, Any],
        plan: Mapping[str, Any],
        raw_steps: list[dict[str, Any]],
    ) -> None:
        task = payload.get("package") if isinstance(payload.get("package"), Mapping) else payload
        task = task if isinstance(task, Mapping) else {}
        package_id = _clean_text(plan.get("package_id") or task.get("package_id") or task.get("task_id"), "engineering_goal")
        self.repo_root = Path(repo_root)
        self.goal_id = _clean_text(task.get("goal_id"), package_id)
        self.goal = _clean_text(plan.get("goal") or task.get("goal"), self.goal_id)
        self.raw_steps = raw_steps
        self.task_summaries = [_task_summary(step, index) for index, step in enumerate(raw_steps, start=1)]
        self.path = self.repo_root / "workspace" / "work_packages" / f"{_safe_state_id(self.goal_id)}.engineering_goal_state.json"

    def _base_state(self, relevant_memory: Mapping[str, Any]) -> dict[str, Any]:
        task_ids = [item["task_id"] for item in self.task_summaries]
        state = {
            "schema": GOAL_STATE_SCHEMA,
            "goal_id": self.goal_id,
            "goal_state": "goal_created",
            "progress": {
                "total_tasks": len(task_ids),
                "completed_count": 0,
                "blocked_count": 0,
                "remaining_count": len(task_ids),
                "percent_complete": 0.0,
            },
            "completed_tasks": [],
            "remaining_tasks": task_ids,
            "blocked_tasks": [],
            "failed_tasks": [],
            "goal_summary": {
                "goal": self.goal,
                "latest_task_id": "",
                "latest_status": "goal_created",
                "task_count": len(task_ids),
            },
            "memory_refs": _memory_refs(relevant_memory),
            "result_bundle": {},
            "task_catalog": copy.deepcopy(self.task_summaries),
            "task_buckets": {
                "pending": [_task_bucket_record(step, index) for index, step in enumerate(self.raw_steps, start=1)],
                "running": [],
                "completed": [],
                "blocked": [],
                "failed": [],
                "cancelled": [],
            },
            "adaptive_planning_decisions": [],
            "lifecycle_events": [],
            "created_at": time.time(),
            "updated_at": time.time(),
            "state_path": str(self.path),
        }
        self._append_event(state, "goal_created")
        self._append_event(state, "running")
        state["goal_state"] = "running"
        return state

    def _append_event(self, state: dict[str, Any], event: str, **fields: Any) -> None:
        state.setdefault("lifecycle_events", []).append(
            {
                "event": event,
                "created_at": time.time(),
                **copy.deepcopy(fields),
            }
        )

    def load_or_create(self, relevant_memory: Mapping[str, Any]) -> dict[str, Any]:
        existing = _read_json(self.path)
        if existing.get("schema") == GOAL_STATE_SCHEMA:
            existing["memory_refs"] = _memory_refs(relevant_memory)
            existing["state_path"] = str(self.path)
            existing.setdefault("task_catalog", copy.deepcopy(self.task_summaries))
            existing.setdefault("adaptive_planning_decisions", [])
            existing.setdefault(
                "task_buckets",
                {
                    "pending": [
                        _task_bucket_record(step, index)
                        for index, step in enumerate(self.raw_steps, start=1)
                        if _task_id(step, index) not in set(existing.get("completed_tasks") or [])
                        and _task_id(step, index) not in set(existing.get("blocked_tasks") or [])
                        and _task_id(step, index) not in set(existing.get("failed_tasks") or [])
                    ],
                    "running": [],
                    "completed": [],
                    "blocked": [],
                    "failed": [],
                    "cancelled": [],
                },
            )
            existing["updated_at"] = time.time()
            _write_json(self.path, existing)
            return existing
        state = self._base_state(relevant_memory)
        _write_json(self.path, state)
        return state

    def record_adaptive_decision(
        self,
        *,
        state: Mapping[str, Any],
        decision: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Persist an adaptive evaluator decision without planning or executing."""

        mutable = copy.deepcopy(dict(state))
        decision_record = copy.deepcopy(dict(decision))
        mutable.setdefault("adaptive_planning_decisions", []).append(decision_record)
        mutable["latest_adaptive_planning_decision"] = decision_record
        mutable["updated_at"] = time.time()
        self._append_event(
            mutable,
            "adaptive_planning_evaluated",
            decision=_clean_text(decision_record.get("decision")),
            reason=_clean_text(decision_record.get("reason")),
        )
        _write_json(self.path, mutable)
        return mutable

    def apply_adaptive_terminal_decision(
        self,
        *,
        state: Mapping[str, Any],
        decision: Mapping[str, Any],
        completion_attestation: Any = None,
    ) -> dict[str, Any]:
        """Persist evaluator-owned terminal intent through lifecycle state."""

        mutable = copy.deepcopy(dict(state))
        decision_name = _clean_text(decision.get("decision")).lower()
        reason = _clean_text(decision.get("reason"), "adaptive_planning_decision")
        if decision_name not in {"block", "complete"}:
            return self.record_adaptive_decision(state=mutable, decision=decision)
        if decision_name == "complete":
            from core.goals.goal_completion_authority import is_accepted_goal_completion_result

            attestation = completion_attestation or decision.get("goal_completion_authority_result")
            if not is_accepted_goal_completion_result(attestation, goal_id=self.goal_id):
                mutable = self.record_adaptive_decision(state=mutable, decision=decision)
                mutable["completion_rejected"] = True
                mutable["completion_rejected_reason"] = (
                    "lifecycle_bound_goal_completion_attestation_required"
                )
                _write_json(self.path, mutable)
                return mutable

        mutable = self.record_adaptive_decision(state=mutable, decision=decision)
        all_task_ids = [
            _clean_text(item.get("task_id"))
            for item in mutable.get("task_catalog", [])
            if isinstance(item, Mapping) and _clean_text(item.get("task_id"))
        ]
        completed_tasks = [str(item) for item in mutable.get("completed_tasks") or []]
        blocked_tasks = [str(item) for item in mutable.get("blocked_tasks") or []]
        failed_tasks = [str(item) for item in mutable.get("failed_tasks") or []]
        superseded_tasks = [str(item) for item in mutable.get("superseded_tasks") or []]
        cancelled_tasks = [str(item) for item in mutable.get("cancelled_tasks") or []]

        if decision_name == "complete":
            for task_id in all_task_ids:
                if task_id not in completed_tasks and task_id not in superseded_tasks:
                    completed_tasks.append(task_id)
            remaining_tasks: list[str] = []
            goal_state = "completed"
        else:
            selected = _as_mapping(mutable.get("selected_task"))
            selected_task_id = _clean_text(selected.get("task_id"))
            if selected_task_id and selected_task_id not in blocked_tasks:
                blocked_tasks.append(selected_task_id)
            remaining_tasks = [str(item) for item in mutable.get("remaining_tasks") or []]
            goal_state = "blocked"

        total = len(all_task_ids)
        resolved_count = len([item for item in completed_tasks if item in set(all_task_ids)]) + len(
            [item for item in superseded_tasks if item in set(all_task_ids)]
        )
        mutable.update(
            {
                "goal_state": goal_state,
                "completed_tasks": completed_tasks,
                "blocked_tasks": blocked_tasks,
                "failed_tasks": failed_tasks,
                "remaining_tasks": remaining_tasks,
                "adaptive_stop_reason": reason,
                "goal_summary": {
                    "goal": self.goal,
                    "latest_task_id": _clean_text(_as_mapping(mutable.get("selected_task")).get("task_id")),
                    "latest_status": goal_state,
                    "task_count": total,
                },
                "progress": {
                    "total_tasks": total,
                    "completed_count": len(completed_tasks),
                    "blocked_count": len(blocked_tasks),
                    "remaining_count": len(remaining_tasks),
                    "percent_complete": round((resolved_count / total) if total else 1.0, 4),
                },
                "updated_at": time.time(),
            }
        )
        buckets = mutable.get("task_buckets") if isinstance(mutable.get("task_buckets"), dict) else {}
        if decision_name == "complete":
            mutable["task_buckets"] = {
                "pending": [],
                "running": [],
                "completed": [dict(item) for item in buckets.get("completed", []) if isinstance(item, Mapping)]
                + [dict(item) for item in buckets.get("pending", []) if isinstance(item, Mapping)]
                + [dict(item) for item in buckets.get("running", []) if isinstance(item, Mapping)],
                "blocked": [dict(item) for item in buckets.get("blocked", []) if isinstance(item, Mapping)],
                "failed": [dict(item) for item in buckets.get("failed", []) if isinstance(item, Mapping)],
                "cancelled": [dict(item) for item in buckets.get("cancelled", []) if isinstance(item, Mapping)],
            }
        else:
            mutable["task_buckets"] = {
                "pending": [dict(item) for item in buckets.get("pending", []) if isinstance(item, Mapping)],
                "running": [],
                "completed": [dict(item) for item in buckets.get("completed", []) if isinstance(item, Mapping)],
                "blocked": [dict(item) for item in buckets.get("blocked", []) if isinstance(item, Mapping)]
                + [dict(item) for item in buckets.get("running", []) if isinstance(item, Mapping)],
                "failed": [dict(item) for item in buckets.get("failed", []) if isinstance(item, Mapping)],
                "cancelled": [dict(item) for item in buckets.get("cancelled", []) if isinstance(item, Mapping)],
            }
        self._append_event(mutable, f"adaptive_planning_{goal_state}", reason=reason)
        self._append_event(mutable, goal_state)
        _write_json(self.path, mutable)
        return mutable

    def select_next_task(self, state: Mapping[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        mutable = copy.deepcopy(dict(state))
        completed = set(str(item) for item in mutable.get("completed_tasks") or [])
        blocked = set(str(item) for item in mutable.get("blocked_tasks") or [])
        failed = set(str(item) for item in mutable.get("failed_tasks") or [])
        cancelled = set(str(item) for item in mutable.get("cancelled_tasks") or [])
        superseded = set(str(item) for item in mutable.get("superseded_tasks") or [])
        for index, step in enumerate(self.raw_steps, start=1):
            task_id = _task_id(step, index)
            if task_id in completed or task_id in blocked or task_id in failed or task_id in cancelled or task_id in superseded:
                continue
            mutable["goal_state"] = "task_selected"
            mutable["selected_task"] = _task_summary(step, index)
            buckets = mutable.get("task_buckets") if isinstance(mutable.get("task_buckets"), dict) else {}
            running_record = _task_bucket_record(step, index)
            pending = [
                item
                for item in buckets.get("pending", [])
                if isinstance(item, Mapping)
                and _clean_text(_as_mapping(item.get("summary")).get("task_id")) != task_id
            ]
            buckets.update(
                {
                    "pending": pending,
                    "running": [running_record],
                    "completed": [dict(item) for item in buckets.get("completed", []) if isinstance(item, Mapping)],
                    "blocked": [dict(item) for item in buckets.get("blocked", []) if isinstance(item, Mapping)],
                    "failed": [dict(item) for item in buckets.get("failed", []) if isinstance(item, Mapping)],
                    "cancelled": [dict(item) for item in buckets.get("cancelled", []) if isinstance(item, Mapping)],
                }
            )
            mutable["task_buckets"] = buckets
            mutable["updated_at"] = time.time()
            self._append_event(mutable, "task_selected", task_id=task_id)
            _write_json(self.path, mutable)
            return copy.deepcopy(step), mutable
        return None, mutable

    def append_planned_tasks(
        self,
        *,
        state: Mapping[str, Any],
        new_steps: list[dict[str, Any]],
        reason: str,
        supersede_task_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Persist replanned task buckets without executing them."""

        mutable = copy.deepcopy(dict(state))
        existing_catalog = [dict(item) for item in mutable.get("task_catalog", []) if isinstance(item, Mapping)]
        existing_ids = {
            _clean_text(item.get("task_id"))
            for item in existing_catalog
            if _clean_text(item.get("task_id"))
        }
        start_index = len(existing_catalog) + 1
        appended_steps: list[dict[str, Any]] = []
        appended_summaries: list[dict[str, Any]] = []
        for offset, step in enumerate(new_steps, start=0):
            if not isinstance(step, Mapping):
                continue
            record = copy.deepcopy(dict(step))
            task_id = _task_id(record, start_index + offset)
            if task_id in existing_ids:
                continue
            appended_steps.append(record)
            summary = _task_summary(record, start_index + offset)
            appended_summaries.append(summary)
            existing_catalog.append(summary)
            existing_ids.add(task_id)

        superseded = [str(item) for item in mutable.get("superseded_tasks") or []]
        blocked_tasks = [str(item) for item in mutable.get("blocked_tasks") or []]
        for task_id in supersede_task_ids or []:
            cleaned = _clean_text(task_id)
            if not cleaned:
                continue
            if cleaned not in superseded:
                superseded.append(cleaned)
            blocked_tasks = [item for item in blocked_tasks if item != cleaned]

        completed = set(str(item) for item in mutable.get("completed_tasks") or [])
        failed = set(str(item) for item in mutable.get("failed_tasks") or [])
        cancelled = set(str(item) for item in mutable.get("cancelled_tasks") or [])
        terminal = completed | failed | cancelled | set(superseded)
        all_task_ids = [item["task_id"] for item in existing_catalog if _clean_text(item.get("task_id"))]
        remaining = [task_id for task_id in all_task_ids if task_id not in terminal and task_id not in set(blocked_tasks)]
        total = len(all_task_ids)
        completed_count = len(completed)

        buckets = mutable.get("task_buckets") if isinstance(mutable.get("task_buckets"), dict) else {}
        pending = [dict(item) for item in buckets.get("pending", []) if isinstance(item, Mapping)]
        pending_ids = {
            _clean_text(_as_mapping(item.get("summary")).get("task_id"))
            for item in pending
        }
        for index, step in enumerate(appended_steps, start=start_index):
            task_id = _task_id(step, index)
            if task_id not in pending_ids:
                pending.append(_task_bucket_record(step, index))
                pending_ids.add(task_id)

        mutable.update(
            {
                "goal_state": "running" if appended_steps else _clean_text(mutable.get("goal_state"), "running"),
                "task_catalog": existing_catalog,
                "remaining_tasks": remaining,
                "blocked_tasks": blocked_tasks,
                "superseded_tasks": superseded,
                "progress": {
                    "total_tasks": total,
                    "completed_count": completed_count,
                    "blocked_count": len(blocked_tasks),
                    "remaining_count": len(remaining),
                    "percent_complete": round((completed_count / total) if total else 1.0, 4),
                },
                "task_buckets": {
                    "pending": pending,
                    "running": [],
                    "completed": [dict(item) for item in buckets.get("completed", []) if isinstance(item, Mapping)],
                    "blocked": [
                        item
                        for item in buckets.get("blocked", [])
                        if isinstance(item, Mapping)
                        and _clean_text(_as_mapping(item.get("summary")).get("task_id")) not in set(superseded)
                    ],
                    "failed": [dict(item) for item in buckets.get("failed", []) if isinstance(item, Mapping)],
                    "cancelled": [dict(item) for item in buckets.get("cancelled", []) if isinstance(item, Mapping)],
                },
                "updated_at": time.time(),
            }
        )
        self._append_event(
            mutable,
            "tasks_replanned",
            reason=_clean_text(reason),
            appended_tasks=appended_summaries,
            superseded_tasks=superseded,
        )
        _write_json(self.path, mutable)
        return mutable

    def finish_execution(
        self,
        *,
        state: Mapping[str, Any],
        result_bundle: Mapping[str, Any],
        memory_record: Mapping[str, Any],
        relevant_memory: Mapping[str, Any],
    ) -> dict[str, Any]:
        mutable = copy.deepcopy(dict(state))
        selected = _as_mapping(mutable.get("selected_task"))
        task_id = _clean_text(selected.get("task_id"))
        observations = result_bundle.get("observations") if isinstance(result_bundle.get("observations"), list) else []
        latest_observation = _as_mapping(observations[-1]) if observations else {}
        ok = bool(result_bundle.get("ok"))
        blocked = bool(latest_observation.get("blocked"))
        failed = (not ok) and not blocked

        self._append_event(mutable, "task_executed", task_id=task_id, ok=ok)
        self._append_event(mutable, "observation_recorded", task_id=task_id, observation=latest_observation)
        self._append_event(mutable, "memory_updated", task_id=task_id, memory_id=_clean_text(memory_record.get("memory_id")))

        completed_tasks = [str(item) for item in mutable.get("completed_tasks") or []]
        blocked_tasks = [str(item) for item in mutable.get("blocked_tasks") or []]
        failed_tasks = [str(item) for item in mutable.get("failed_tasks") or []]
        if ok and task_id and task_id not in completed_tasks:
            completed_tasks.append(task_id)
        elif blocked and task_id and task_id not in blocked_tasks:
            blocked_tasks.append(task_id)
        elif failed and task_id and task_id not in failed_tasks:
            failed_tasks.append(task_id)

        all_task_ids = [item["task_id"] for item in self.task_summaries]
        superseded_tasks = [str(item) for item in mutable.get("superseded_tasks") or []]
        cancelled_tasks = [str(item) for item in mutable.get("cancelled_tasks") or []]
        terminal = set(completed_tasks) | set(blocked_tasks) | set(failed_tasks) | set(superseded_tasks) | set(cancelled_tasks)
        remaining_tasks = [item for item in all_task_ids if item not in terminal]
        total = len(all_task_ids)
        completed_count = len(completed_tasks)
        resolved_count = completed_count + len([item for item in superseded_tasks if item in all_task_ids])

        if blocked_tasks:
            goal_state = "blocked"
        elif failed_tasks:
            goal_state = "failed"
        elif total > 0 and resolved_count >= total:
            goal_state = "completed"
        else:
            goal_state = "next_task_generated"

        mutable.update(
            {
                "goal_state": goal_state,
                "completed_tasks": completed_tasks,
                "remaining_tasks": remaining_tasks,
                "blocked_tasks": blocked_tasks,
                "failed_tasks": failed_tasks,
                "progress": {
                    "total_tasks": total,
                    "completed_count": completed_count,
                    "blocked_count": len(blocked_tasks),
                    "remaining_count": len(remaining_tasks),
                    "percent_complete": round((resolved_count / total) if total else 1.0, 4),
                },
                "goal_summary": {
                    "goal": self.goal,
                    "latest_task_id": task_id,
                    "latest_status": goal_state,
                    "task_count": total,
                },
                "memory_refs": _memory_refs(relevant_memory, memory_record),
                "result_bundle": {
                    "schema": _clean_text(result_bundle.get("schema")),
                    "ok": ok,
                    "status": _clean_text(result_bundle.get("status")),
                    "package_id": _clean_text(result_bundle.get("package_id")),
                    "state_path": _clean_text(result_bundle.get("state_path")),
                },
                "updated_at": time.time(),
            }
        )
        buckets = mutable.get("task_buckets") if isinstance(mutable.get("task_buckets"), dict) else {}
        running = [dict(item) for item in buckets.get("running", []) if isinstance(item, Mapping)]
        selected_record = running[0] if running else {"summary": selected, "task_payload": {}}
        def without_task(items: Any) -> list[dict[str, Any]]:
            records = [dict(item) for item in items if isinstance(item, Mapping)] if isinstance(items, list) else []
            return [
                item
                for item in records
                if _clean_text(_as_mapping(item.get("summary")).get("task_id")) != task_id
            ]

        bucket_name = "completed" if ok else "blocked" if blocked else "failed"
        terminal_bucket = without_task(buckets.get(bucket_name, []))
        terminal_bucket.append(copy.deepcopy(selected_record))
        mutable["task_buckets"] = {
            "pending": [
                _task_bucket_record(step, index)
                for index, step in enumerate(self.raw_steps, start=1)
                if _task_id(step, index) in remaining_tasks
            ],
            "running": [],
            "completed": terminal_bucket if bucket_name == "completed" else without_task(buckets.get("completed", [])),
            "blocked": terminal_bucket if bucket_name == "blocked" else without_task(buckets.get("blocked", [])),
            "failed": terminal_bucket if bucket_name == "failed" else without_task(buckets.get("failed", [])),
            "cancelled": without_task(buckets.get("cancelled", [])),
        }
        self._append_event(mutable, "progress_evaluated", progress=mutable["progress"])
        if goal_state in {"completed", "blocked", "failed"}:
            self._append_event(mutable, goal_state)
        else:
            next_task = remaining_tasks[0] if remaining_tasks else ""
            mutable["next_task"] = next_task
            self._append_event(mutable, "next_task_generated", task_id=next_task)
        _write_json(self.path, mutable)
        return mutable


__all__ = [
    "EngineeringGoalLifecycle",
    "GOAL_LIFECYCLE_SCHEMA",
    "GOAL_STATE_SCHEMA",
    "lifecycle_enabled",
]
