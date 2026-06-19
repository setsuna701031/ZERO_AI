from __future__ import annotations

from core.runtime.task_runtime import project_runtime_status
import copy
import inspect
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from core.runtime.runtime_session_resume import (
    RuntimeSessionResume,
    RuntimeSessionResumeRecord,
    RuntimeTaskResumeSnapshot,
    is_resumable_task_status,
    is_terminal_task_status,
    normalize_task_status,
    stable_resume_fingerprint,
)
from core.runtime.runtime_task_continuation import (
    CONTINUATION_ACTION_REQUEUE,
    CONTINUATION_ACTION_SKIP,
    CONTINUATION_ACTION_WAIT,
    RuntimeTaskContinuation,
)
from core.runtime.persistent_queue_contract import extract_queue_lineage
from core.goals.goal_lineage_contract import canonical_work_identity, extract_runtime_identity

try:
    from core.runtime.persistent_engineering_session import PersistentEngineeringSession
except Exception:  # pragma: no cover - optional during partial boot/import tests
    PersistentEngineeringSession = None  # type: ignore[assignment]


SCHEMA = "zero.aer.persistent_runtime_orchestrator.v1"

RESUME_TO_QUEUE_STATUSES = {
    "created",
    "queued",
    "ready",
    "running",
    "retry",
    "retrying",
    "needs_resume",
    "recoverable",
}

WAITING_STATUSES = {
    "blocked",
    "review_required",
    "waiting",
    "waiting_review",
    "waiting_blocker",
    "paused",
    "needs_observation",
}

TERMINAL_STATUSES = {
    "finished",
    "done",
    "success",
    "completed",
    "failed",
    "error",
    "cancelled",
    "canceled",
    "rejected_terminal",
    "blocked_terminal",
}


def _now() -> float:
    return time.time()


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_dict(value: Any) -> Dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> List[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp.replace(path)


def _repo_root_from_workspace(workspace_dir: Path) -> Path:
    resolved = workspace_dir.resolve(strict=False)
    if resolved.name.lower() == "workspace":
        return resolved.parent
    return Path.cwd().resolve(strict=False)


def _call_first(obj: Any, names: Iterable[str], *args: Any, **kwargs: Any) -> Any:
    for name in names:
        fn = getattr(obj, name, None)
        if callable(fn):
            return fn(*args, **kwargs)
    raise AttributeError("no compatible method found: " + ", ".join(names))


def should_route_persistent_runtime(task: Any, *, force: bool = False) -> bool:
    """Return True when a task/plan belongs to the persistent runtime path.

    This is a compatibility contract used by planner-runtime dispatch and
    persistent-runtime tests. It is intentionally read-only: it only inspects
    stable routing markers and never mutates the task.
    """
    if force:
        return True
    if not isinstance(task, Mapping):
        return False
    if bool(task.get("persistent_runtime")):
        return True

    cycles = task.get("cycles")
    if isinstance(cycles, list) and cycles:
        return True

    for key in ("multi_cycle", "long_running", "long_runtime", "aer_runtime"):
        if bool(task.get(key)):
            return True

    mode = _clean_text(
        task.get("mode")
        or task.get("runtime_mode")
        or task.get("planner_mode")
        or task.get("execution_mode")
    ).lower()
    if mode in {
        "persistent_runtime",
        "long_running",
        "multi_cycle",
        "aer_persistent_runtime",
        "persistent_autonomous_engineering_runtime",
    }:
        return True

    goal = _clean_text(
        task.get("goal")
        or task.get("title")
        or task.get("summary")
        or task.get("task")
        or task.get("description")
    ).lower()
    routing_phrases = (
        "persistent autonomous engineering runtime",
        "persistent runtime",
        "failure recovery resume",
        "runtime recovery resume",
        "recovery resume",
        "multi-cycle engineering",
        "multi cycle engineering",
    )
    return any(phrase in goal for phrase in routing_phrases)


def _cycle_id_for(cycle: Mapping[str, Any], index: int) -> str:
    return _clean_text(cycle.get("cycle_id") or cycle.get("id") or cycle.get("name")) or f"cycle_{index + 1}"


def _simulate_persistent_runtime_orchestrator_contract(
    *,
    repo_root: str | Path = ".",
    workspace_dir: str | Path | None = None,
    task: Mapping[str, Any],
    force: bool = False,
    fail_cycle_index: int | None = None,
    fail_group_index: int | None = None,
) -> Dict[str, Any]:
    """Execute the lightweight persistent-runtime contract path.

    This path is used when callers pass a task/plan directly instead of a
    TaskRepository. It models the multi-cycle orchestration contract and writes
    a durable session record, but it does not execute tools, mutate gateways,
    or modify source files.
    """
    root = Path(repo_root).resolve(strict=False)
    workspace = Path(workspace_dir).resolve(strict=False) if workspace_dir is not None else root / "workspace"
    records_dir = workspace / "runtime_session_orchestrator"
    records_dir.mkdir(parents=True, exist_ok=True)

    routed = should_route_persistent_runtime(task, force=force)
    task_id = _clean_text(task.get("task_id") or task.get("id") or task.get("name")) or "persistent_runtime_task"
    session_record_path = records_dir / f"{task_id}_session_record.json"
    boundary = {
        "delegates_to_multi_cycle_engineering_loop": True,
        "does_not_modify_execution_gateway": True,
        "does_not_modify_step_executor": True,
        "does_not_execute_steps_directly": True,
    }

    if not routed:
        orchestrator = {
            "ok": False,
            "schema": SCHEMA,
            "status": "not_persistent_runtime_task",
            "routed": False,
            "reason": "persistent_runtime_route_not_selected",
            "cycle_count": 0,
            "cycle_result_count": 0,
            "closure_count": 0,
            "boundary": boundary,
            "session_record_path": str(session_record_path),
            "multi_cycle_engineering_loop": {
                "ok": False,
                "status": "not_persistent_runtime_task",
                "cycle_results": [],
                "closure_results": [],
            },
        }
        record = {
            "schema": SCHEMA,
            "status": "not_persistent_runtime_task",
            "task_id": task_id,
            "boundary": boundary,
            "multi_cycle_engineering_loop": orchestrator["multi_cycle_engineering_loop"],
        }
        _write_json(session_record_path, record)
        return {"ok": False, "persistent_runtime_orchestrator": orchestrator}

    raw_cycles = task.get("cycles")
    cycles = [copy.deepcopy(item) for item in raw_cycles if isinstance(item, Mapping)] if isinstance(raw_cycles, list) else []
    if not cycles:
        cycles = [
            {
                "cycle_id": "default",
                "goal": _clean_text(task.get("goal") or task_id),
                "target_groups": [],
            }
        ]

    cycle_results: List[Dict[str, Any]] = []
    closure_results: List[Dict[str, Any]] = []

    for index, cycle in enumerate(cycles):
        cycle_id = _cycle_id_for(cycle, index)
        target_groups = cycle.get("target_groups") if isinstance(cycle.get("target_groups"), list) else []
        should_fail = fail_cycle_index is not None and int(fail_cycle_index) == index
        runtime_status = "recoverable_failure" if should_fail else "finished"

        group_results: List[Dict[str, Any]] = []
        for group_index, group in enumerate(target_groups):
            group_failed = should_fail and fail_group_index is not None and int(fail_group_index) == group_index
            group_results.append(
                {
                    "ok": not group_failed,
                    "group_index": group_index,
                    "target_group": copy.deepcopy(group),
                    "status": "recoverable_failure" if group_failed else "finished",
                }
            )

        cycle_result = {
            "ok": True,
            "cycle_id": cycle_id,
            "cycle_index": index,
            "goal": _clean_text(cycle.get("goal") or cycle_id),
            "runtime": {
                "ok": not should_fail,
                "status": runtime_status,
                "failed_group_index": fail_group_index if should_fail else None,
            },
            "group_results": group_results,
        }
        cycle_results.append(cycle_result)

        if should_fail:
            closure_results.append(
                {
                    "cycle_id": cycle_id,
                    "cycle_index": index,
                    "closure": {
                        "ok": True,
                        "status": "closed",
                        "reason": "failure_recovery_resume_continue",
                        "failed_group_index": fail_group_index,
                    },
                }
            )

    runtime_ok = all(
        bool(cycle_result.get("runtime", {}).get("ok"))
        and all(bool(group.get("ok")) for group in cycle_result.get("group_results", []))
        for cycle_result in cycle_results
    )
    runtime_status = "finished" if runtime_ok else "recoverable_failure"
    terminal_status = runtime_status
    loop = {
        "ok": runtime_ok,
        "status": terminal_status,
        "cycle_results": cycle_results,
        "closure_results": closure_results,
    }
    orchestrator = {
        "ok": runtime_ok,
        "schema": SCHEMA,
        "status": terminal_status,
        "routed": True,
        "task_id": task_id,
        "cycle_count": len(cycles),
        "cycle_result_count": len(cycle_results),
        "closure_count": len(closure_results),
        "boundary": boundary,
        "session_record_path": str(session_record_path),
        "multi_cycle_engineering_loop": loop,
    }
    record = {
        "schema": SCHEMA,
        "status": terminal_status,
        "task_id": task_id,
        "boundary": boundary,
        "multi_cycle_engineering_loop": loop,
    }
    _write_json(session_record_path, record)
    return {"ok": runtime_ok, "persistent_runtime_orchestrator": orchestrator}


def _execute_persistent_runtime_task_with_executor(
    *,
    repo_root: str | Path = ".",
    workspace_dir: str | Path | None = None,
    task: Mapping[str, Any],
    executor: Any,
    force: bool = False,
    fail_group_index: int | None = None,
) -> Dict[str, Any]:
    """Run a planner persistent-runtime task through LongEngineeringRuntime.

    This preserves the public PersistentRuntimeOrchestrator contract while
    allowing the long runtime to deliver each normalized planner step to the
    StepExecutor endpoint.
    """
    root = Path(repo_root).resolve(strict=False)
    workspace = Path(workspace_dir).resolve(strict=False) if workspace_dir is not None else root / "workspace"
    records_dir = workspace / "runtime_session_orchestrator"
    records_dir.mkdir(parents=True, exist_ok=True)

    task_payload = copy.deepcopy(dict(task))
    routed = should_route_persistent_runtime(task_payload, force=force)
    task_id = _clean_text(task_payload.get("task_id") or task_payload.get("id") or task_payload.get("name")) or "persistent_runtime_task"
    goal = _clean_text(task_payload.get("goal") or task_payload.get("title") or task_id)
    session_record_path = records_dir / f"{task_id}_session_record.json"
    boundary = {
        "delegates_to_multi_cycle_engineering_loop": True,
        "delegates_to_long_engineering_runtime": True,
        "does_not_modify_execution_gateway": True,
        "does_not_modify_step_executor": True,
        "does_not_execute_steps_directly": True,
        "step_executor_remains_execution_endpoint": True,
    }

    if not routed:
        orchestrator = {
            "ok": False,
            "schema": SCHEMA,
            "status": "not_persistent_runtime_task",
            "routed": False,
            "reason": "persistent_runtime_route_not_selected",
            "cycle_count": 0,
            "cycle_result_count": 0,
            "closure_count": 0,
            "boundary": boundary,
            "session_record_path": str(session_record_path),
            "multi_cycle_engineering_loop": {
                "ok": False,
                "status": "not_persistent_runtime_task",
                "cycle_results": [],
                "closure_results": [],
                "closure_count": 0,
            },
        }
        _write_json(
            session_record_path,
            {
                "schema": SCHEMA,
                "status": "not_persistent_runtime_task",
                "task_id": task_id,
                "boundary": boundary,
                "multi_cycle_engineering_loop": orchestrator["multi_cycle_engineering_loop"],
            },
        )
        return {"ok": False, "persistent_runtime_orchestrator": orchestrator}

    try:
        from core.runtime.long_engineering_runtime import LongEngineeringRuntime
    except Exception as exc:
        orchestrator = {
            "ok": False,
            "schema": SCHEMA,
            "status": "long_engineering_runtime_unavailable",
            "routed": True,
            "reason": f"{exc.__class__.__name__}: {exc}",
            "cycle_count": 0,
            "cycle_result_count": 0,
            "closure_count": 0,
            "boundary": boundary,
            "session_record_path": str(session_record_path),
            "multi_cycle_engineering_loop": {
                "ok": False,
                "status": "long_engineering_runtime_unavailable",
                "cycle_results": [],
                "closure_results": [],
                "closure_count": 0,
            },
        }
        _write_json(session_record_path, orchestrator)
        return {"ok": False, "persistent_runtime_orchestrator": orchestrator}

    runtime = LongEngineeringRuntime(
        repo_root=root,
        task=task_payload,
        task_id=task_id,
        goal=goal,
    )
    runtime_result = runtime.run(
        executor=executor,
        fail_group_index=(-1 if fail_group_index is None else int(fail_group_index)),
    )

    runtime_ok = bool(runtime_result.get("ok"))
    runtime_status = _clean_text(runtime_result.get("status")) or ("finished" if runtime_ok else "recoverable_failure")
    recoverable = bool(runtime_result.get("recoverable")) or runtime_status == "recoverable_failure"
    executed_group_count = int(runtime_result.get("executed_group_count") or 0)
    plan_group_count = int(runtime_result.get("plan_group_count") or executed_group_count or 0)
    failure_count = int(runtime_result.get("failure_count") or (1 if recoverable else 0))

    runtime_payload = copy.deepcopy(runtime_result)
    runtime_payload.setdefault("executed_group_count", executed_group_count)
    runtime_payload.setdefault("plan_group_count", plan_group_count)
    runtime_payload.setdefault("failure_count", failure_count)
    runtime_payload.setdefault("status", runtime_status)

    cycle_result = {
        "ok": runtime_ok,
        "cycle_id": "planner_cycle_1",
        "cycle_index": 0,
        "goal": goal,
        "runtime": runtime_payload,
        "group_results": copy.deepcopy(runtime_result.get("executed_groups") or []),
    }

    closure_results: List[Dict[str, Any]] = []
    if recoverable or not runtime_ok:
        closure_results.append(
            {
                "cycle_id": "planner_cycle_1",
                "cycle_index": 0,
                "closure": {
                    "ok": True,
                    "status": "closed",
                    "reason": "failure_recovery_resume_continue",
                    "failed_group_index": runtime_result.get("latest_checkpoint", {}).get("group_index", fail_group_index),
                    "recovery_marker_path": runtime_result.get("recovery_marker_path", ""),
                },
            }
        )

    terminal_status = "finished" if runtime_ok and runtime_status == "finished" else runtime_status
    loop = {
        "ok": runtime_ok,
        "status": terminal_status,
        "cycle_results": [cycle_result],
        "closure_results": closure_results,
        "closure_count": len(closure_results),
        "executed_group_count": executed_group_count,
        "plan_group_count": plan_group_count,
    }

    orchestrator = {
        "ok": runtime_ok,
        "schema": SCHEMA,
        "status": terminal_status,
        "routed": True,
        "task_id": task_id,
        "cycle_count": 1,
        "cycle_result_count": 1,
        "closure_count": len(closure_results),
        "boundary": boundary,
        "session_record_path": str(session_record_path),
        "multi_cycle_engineering_loop": loop,
        "long_engineering_runtime": runtime_payload,
    }

    record = {
        "schema": SCHEMA,
        "status": terminal_status,
        "task_id": task_id,
        "boundary": boundary,
        "multi_cycle_engineering_loop": loop,
        "persistent_runtime_orchestrator": orchestrator,
    }
    _write_json(session_record_path, record)
    return {"ok": runtime_ok, "persistent_runtime_orchestrator": orchestrator}


class PersistentRuntimeOrchestrator:
    """Boot-time bridge from durable resume state back into ZERO runtime.

    Ownership boundary:
    - Reads RuntimeSessionResume records and TaskRepository tasks.
    - Converts resumable task snapshots into continuation decisions.
    - Requeues runnable tasks through Scheduler submit/enqueue APIs.
    - Preserves blocked/review tasks as waiting records.
    - Does not execute steps directly.
    - Does not call ToolRegistry.
    - Does not modify project source files.
    """

    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        workspace_dir: str | Path = "workspace",
        resume_store_path: str | Path | None = None,
        audit_path: str | Path | None = None,
        auto_create_resume_record: bool = True,
    ) -> None:
        self.workspace_dir = Path(workspace_dir).resolve(strict=False)
        self.repo_root = Path(repo_root).resolve(strict=False)
        if str(repo_root or ".") == "." and self.workspace_dir.name.lower() == "workspace":
            self.repo_root = _repo_root_from_workspace(self.workspace_dir)
        self.resume_store_path = (
            Path(resume_store_path).resolve(strict=False)
            if resume_store_path is not None
            else self.workspace_dir / "runtime_session_resume.json"
        )
        self.audit_path = (
            Path(audit_path).resolve(strict=False)
            if audit_path is not None
            else self.workspace_dir / "persistent_runtime_orchestrator.json"
        )
        self.auto_create_resume_record = bool(auto_create_resume_record)

    def resume_last_session(
        self,
        *,
        task_repository: Any,
        scheduler: Any = None,
        agent_loop: Any = None,
        session_id: str | None = None,
        persist: bool = True,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Resume the latest durable runtime session into the scheduler queue.

        This method is intentionally orchestration-only. It may update task
        status back to queued/waiting and may call scheduler.submit_existing_task
        or enqueue_task, but it never runs task steps.
        """
        started_at = _now()
        tasks = self._list_repo_tasks(task_repository)
        resume_runtime = self._build_runtime_resume_store()
        latest_record = resume_runtime.get_record(session_id) if session_id else resume_runtime.latest_record()
        record_source = "existing_runtime_session_resume_record"
        record: RuntimeSessionResumeRecord | None = latest_record

        if record is None and self.auto_create_resume_record:
            resumable_tasks = [task for task in tasks if self._is_resumable_repo_task(task)]
            if resumable_tasks:
                record = resume_runtime.create_session_record(
                    tasks=resumable_tasks,
                    metadata={
                        "source": "persistent_runtime_orchestrator_bootstrap",
                        "created_by": SCHEMA,
                    },
                )
                record_source = "created_from_task_repository"

        if record is None:
            result = self._result(
                ok=True,
                action="nothing_to_resume",
                reason="no_resume_record_or_resumable_task",
                record_source="none",
                started_at=started_at,
                tasks_seen=len(tasks),
            )
            self._append_audit(result)
            return result

        resume_plan = resume_runtime.build_resume_plan(
            session_id=record.session_id,
            include_terminal=False,
            persist=persist,
        )
        if resume_plan.get("already_resumed"):
            result = self._result(
                ok=True,
                action="idempotent_resume_skip",
                reason="session_already_resumed",
                record_source=record_source,
                session_id=record.session_id,
                resume_plan=resume_plan,
                requeued_task_ids=[],
                waiting_task_ids=[],
                skipped_task_ids=[],
                requeued_count=0,
                waiting_count=0,
                skipped_count=0,
                tasks_seen=len(tasks),
                started_at=started_at,
            )
            self._append_audit(result)
            return result
        snapshots = self._snapshots_from_record(record)
        candidate_tasks, terminal_guard_skipped = self._candidate_tasks_from_snapshots(snapshots)
        if not candidate_tasks:
            candidate_tasks = [task for task in tasks if self._is_resumable_repo_task(task)]
        candidate_tasks, repo_terminal_skipped = self._filter_terminal_runtime_state_tasks(candidate_tasks)
        terminal_guard_skipped.extend(repo_terminal_skipped)

        continuation_plan_obj = RuntimeTaskContinuation().build_plan(candidate_tasks)
        continuation_plan = continuation_plan_obj.to_dict()
        if terminal_guard_skipped:
            continuation_plan = self._append_terminal_guard_skips(
                continuation_plan=continuation_plan,
                skipped_tasks=terminal_guard_skipped,
            )

        repository_updates = self._apply_continuation_to_repository(
            task_repository=task_repository,
            continuation_plan=continuation_plan,
        )
        scheduler_updates = self._requeue_with_scheduler(
            scheduler=scheduler,
            continuation_plan=continuation_plan,
            force=force,
        )
        engineering_session = self._record_persistent_engineering_resume(
            agent_loop=agent_loop,
            record=record,
            resume_plan=resume_plan,
            continuation_plan=continuation_plan,
            repository_updates=repository_updates,
            scheduler_updates=scheduler_updates,
        )

        requeued = [item for item in scheduler_updates if isinstance(item, dict) and item.get("ok")]
        waiting = list(continuation_plan.get("waiting_task_ids") or [])
        skipped = list(continuation_plan.get("skipped_task_ids") or [])

        if persist and (requeued or waiting):
            try:
                resume_runtime.mark_resumed(
                    record.session_id,
                    metadata={
                        "resumed_by": SCHEMA,
                        "resumed_at": _now(),
                        "requeued_task_ids": list(continuation_plan.get("requeue_task_ids") or []),
                        "waiting_task_ids": waiting,
                    },
                )
            except Exception:
                pass

        result = self._result(
            ok=True,
            action="resume_last_session",
            reason="resume_plan_applied",
            record_source=record_source,
            session_id=record.session_id,
            resume_plan=resume_plan,
            continuation_plan=continuation_plan,
            repository_updates=repository_updates,
            scheduler_updates=scheduler_updates,
            persistent_engineering_session=engineering_session,
            requeued_task_ids=list(continuation_plan.get("requeue_task_ids") or []),
            waiting_task_ids=waiting,
            skipped_task_ids=skipped,
            terminal_guard_skipped_task_ids=[
                item.get("task_id") for item in terminal_guard_skipped if isinstance(item, dict)
            ],
            requeued_count=len(requeued),
            waiting_count=len(waiting),
            skipped_count=len(skipped),
            tasks_seen=len(tasks),
            started_at=started_at,
        )
        self._append_audit(result)
        return result

    def capture_current_session(
        self,
        *,
        task_repository: Any,
        session_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        tasks = self._list_repo_tasks(task_repository)
        runtime_resume = self._build_runtime_resume_store()
        record = runtime_resume.create_session_record(
            session_id=session_id,
            tasks=[task for task in tasks if self._is_resumable_repo_task(task)],
            metadata={
                "source": "persistent_runtime_orchestrator_capture",
                **_safe_dict(metadata),
            },
        )
        result = {
            "ok": True,
            "schema": SCHEMA,
            "action": "capture_current_session",
            "session_id": record.session_id,
            "snapshot_count": len(record.snapshots),
            "resume_plan": record.resume_plan,
            "created_at": _now(),
        }
        self._append_audit(result)
        return result

    def status(self) -> Dict[str, Any]:
        runtime_resume = self._build_runtime_resume_store()
        latest = runtime_resume.latest_record()
        audit = _read_json(self.audit_path)
        events = audit.get("events") if isinstance(audit.get("events"), list) else []
        return {
            "ok": True,
            "schema": SCHEMA,
            "workspace_dir": str(self.workspace_dir),
            "repo_root": str(self.repo_root),
            "resume_store_path": str(self.resume_store_path),
            "audit_path": str(self.audit_path),
            "has_latest_record": latest is not None,
            "latest_session_id": latest.session_id if latest is not None else "",
            "latest_status": latest.status if latest is not None else "",
            "audit_event_count": len(events),
        }

    def _build_runtime_resume_store(self) -> RuntimeSessionResume:
        return RuntimeSessionResume(
            workspace_root=self.repo_root,
            storage_path=self.resume_store_path,
        )

    def _list_repo_tasks(self, task_repository: Any) -> List[Dict[str, Any]]:
        if task_repository is None:
            return []
        try:
            tasks = _call_first(task_repository, ("list_tasks", "all_tasks", "tasks"))
        except Exception:
            tasks = getattr(task_repository, "tasks", [])
        if not isinstance(tasks, list):
            return []
        return [copy.deepcopy(item) for item in tasks if isinstance(item, dict)]

    def _snapshots_from_record(self, record: RuntimeSessionResumeRecord) -> List[RuntimeTaskResumeSnapshot]:
        snapshots = list(record.snapshots or [])
        return [item for item in snapshots if is_resumable_task_status(item.status)]

    def _candidate_tasks_from_snapshots(
        self,
        snapshots: Iterable[RuntimeTaskResumeSnapshot],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        candidate_tasks: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        seen_identities: set[tuple[str, ...] | tuple[str, str]] = set()
        for snapshot in snapshots:
            task = _safe_dict(snapshot.task)
            if not task:
                continue
            task.setdefault("task_id", snapshot.task_id)
            task_id = _clean_text(task.get("task_id"))
            identity = canonical_work_identity(task) or ("task_id", task_id)
            if identity in seen_identities:
                continue
            seen_identities.add(identity)
            runtime_status = self._runtime_state_status_for_task(task)
            if runtime_status and self._is_terminal_status(runtime_status):
                project_runtime_status(task, runtime_status, owner="core/runtime/persistent_runtime_orchestrator.py")
                skipped.append(
                    {
                        "ok": True,
                        "task_id": _clean_text(task.get("task_id")),
                        "action": CONTINUATION_ACTION_SKIP,
                        "reason": "terminal_runtime_state_guard",
                        "status": runtime_status,
                    }
                )
                continue
            candidate_tasks.append(task)
        return candidate_tasks, skipped

    def _filter_terminal_runtime_state_tasks(
        self,
        tasks: Iterable[Mapping[str, Any]],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        filtered: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        for item in tasks:
            task = _safe_dict(item)
            if not task:
                continue
            runtime_status = self._runtime_state_status_for_task(task)
            task_id = _clean_text(task.get("task_id"))
            if runtime_status and self._is_terminal_status(runtime_status):
                skipped.append(
                    {
                        "ok": True,
                        "task_id": task_id,
                        "action": CONTINUATION_ACTION_SKIP,
                        "reason": "terminal_runtime_state_guard",
                        "status": runtime_status,
                    }
                )
                continue
            filtered.append(task)
        return filtered, skipped

    def _append_terminal_guard_skips(
        self,
        *,
        continuation_plan: Mapping[str, Any],
        skipped_tasks: Iterable[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        plan = _safe_dict(continuation_plan)
        skipped_ids = list(plan.get("skipped_task_ids") or []) if isinstance(plan.get("skipped_task_ids"), list) else []
        decisions = list(plan.get("decisions") or []) if isinstance(plan.get("decisions"), list) else []
        requeue_ids = list(plan.get("requeue_task_ids") or []) if isinstance(plan.get("requeue_task_ids"), list) else []
        waiting_ids = list(plan.get("waiting_task_ids") or []) if isinstance(plan.get("waiting_task_ids"), list) else []

        for skipped in skipped_tasks:
            task_id = _clean_text(skipped.get("task_id")) if isinstance(skipped, Mapping) else ""
            if not task_id:
                continue
            if task_id not in skipped_ids:
                skipped_ids.append(task_id)
            requeue_ids = [item for item in requeue_ids if _clean_text(item) != task_id]
            waiting_ids = [item for item in waiting_ids if _clean_text(item) != task_id]
            decisions.append(
                {
                    "task_id": task_id,
                    "action": CONTINUATION_ACTION_SKIP,
                    "reason": skipped.get("reason", "terminal_runtime_state_guard"),
                    "status": skipped.get("status", ""),
                    "task": {"task_id": task_id, "status": skipped.get("status", "")},
                }
            )

        plan["skipped_task_ids"] = skipped_ids
        plan["requeue_task_ids"] = requeue_ids
        plan["waiting_task_ids"] = waiting_ids
        plan["decisions"] = decisions
        plan["terminal_runtime_state_guard_applied"] = bool(skipped_ids)
        plan["fingerprint"] = stable_resume_fingerprint(plan)
        return plan

    def _runtime_state_status_for_task(self, task: Mapping[str, Any]) -> str:
        runtime_state_path = self._runtime_state_path_for_task(task)
        if runtime_state_path is None or not runtime_state_path.exists():
            return ""
        payload = _read_json(runtime_state_path)
        if not payload:
            return ""
        return normalize_task_status(payload.get("status"))

    def _runtime_state_path_for_task(self, task: Mapping[str, Any]) -> Path | None:
        explicit = task.get("runtime_state_file")
        if explicit:
            return Path(str(explicit))
        task_dir = task.get("task_dir")
        if task_dir:
            return Path(str(task_dir)) / "runtime_state.json"
        task_id = _clean_text(task.get("task_id"))
        if task_id:
            return self.workspace_dir / "tasks" / task_id / "runtime_state.json"
        return None

    def _is_terminal_status(self, status: Any) -> bool:
        normalized = normalize_task_status(status)
        return normalized in TERMINAL_STATUSES or is_terminal_task_status(normalized)

    def _is_resumable_repo_task(self, task: Mapping[str, Any]) -> bool:
        runtime_status = self._runtime_state_status_for_task(task)
        if runtime_status and self._is_terminal_status(runtime_status):
            return False
        status = normalize_task_status(task.get("status"))
        if self._is_terminal_status(status):
            return False
        return is_resumable_task_status(status) or status in RESUME_TO_QUEUE_STATUSES or status in WAITING_STATUSES

    def _apply_continuation_to_repository(
        self,
        *,
        task_repository: Any,
        continuation_plan: Mapping[str, Any],
    ) -> List[Dict[str, Any]]:
        updates: List[Dict[str, Any]] = []
        decisions = continuation_plan.get("decisions")
        if not isinstance(decisions, list):
            return updates

        for decision in decisions:
            if not isinstance(decision, dict):
                continue
            task_id = _clean_text(decision.get("task_id"))
            action = _clean_text(decision.get("action"))
            task = _safe_dict(decision.get("task"))
            if not task_id or not task:
                continue

            runtime_status = self._runtime_state_status_for_task(task)
            if runtime_status and self._is_terminal_status(runtime_status):
                updates.append(
                    {
                        "ok": True,
                        "task_id": task_id,
                        "action": "skip_repository_update",
                        "reason": "terminal_runtime_state_guard",
                        "status": runtime_status,
                    }
                )
                continue

            status = normalize_task_status(task.get("status"))
            if action == CONTINUATION_ACTION_REQUEUE and status in RESUME_TO_QUEUE_STATUSES:
                project_runtime_status(task, "queued", owner="core/runtime/persistent_runtime_orchestrator.py")
                task["blocked_reason"] = ""
                task["waiting_reason"] = ""
                task["next_action"] = "run_next_tick"
            elif action == CONTINUATION_ACTION_WAIT:
                if status == "review_required":
                    project_runtime_status(task, "review_required", owner="core/runtime/persistent_runtime_orchestrator.py")
                    task["next_action"] = "wait_for_external_event"
                else:
                    project_runtime_status(task, "blocked", owner="core/runtime/persistent_runtime_orchestrator.py")
                    task.setdefault("blocked_reason", "persistent_runtime_resume_waiting")
                    task["next_action"] = "wait_for_external_event"
            elif action == CONTINUATION_ACTION_SKIP:
                updates.append(
                    {
                        "ok": True,
                        "task_id": task_id,
                        "action": "skip_repository_update",
                        "reason": decision.get("reason", "skip"),
                    }
                )
                continue

            task.setdefault("task_id", task_id)
            task.setdefault("history", [])
            if isinstance(task.get("history"), list):
                marker = f"persistent_resume:{task.get('status')}"
                if marker not in task["history"]:
                    task["history"].append(marker)

            try:
                updated = _call_first(task_repository, ("upsert_task", "add_or_update_task", "save_task"), task)
                updates.append(
                    {
                        "ok": bool(updated is not False),
                        "task_id": task_id,
                        "action": "repository_upsert",
                        "status": task.get("status"),
                    }
                )
            except Exception as exc:
                updates.append(
                    {
                        "ok": False,
                        "task_id": task_id,
                        "action": "repository_upsert_failed",
                        "status": task.get("status"),
                        "error": f"{exc.__class__.__name__}: {exc}",
                    }
                )
        return updates

    def _requeue_with_scheduler(
        self,
        *,
        scheduler: Any,
        continuation_plan: Mapping[str, Any],
        force: bool = False,
    ) -> List[Dict[str, Any]]:
        if scheduler is None:
            return []
        decisions = [
            item for item in (continuation_plan.get("decisions") or [])
            if isinstance(item, Mapping) and item.get("action") == CONTINUATION_ACTION_REQUEUE
        ]
        if not decisions:
            return []

        updates: List[Dict[str, Any]] = []
        for decision in decisions:
            task_id = _clean_text(decision.get("task_id"))
            if not task_id:
                continue
            task_payload = decision.get("task") if isinstance(decision.get("task"), Mapping) else {}
            runtime_status = self._runtime_state_status_for_task(task_payload or {"task_id": task_id})
            if runtime_status and self._is_terminal_status(runtime_status):
                updates.append(
                    {
                        "ok": True,
                        "task_id": task_id,
                        "action": "skip_scheduler_requeue",
                        "reason": "terminal_runtime_state_guard",
                        "status": runtime_status,
                    }
                )
                continue

            try:
                if hasattr(scheduler, "submit_existing_task"):
                    submit = scheduler.submit_existing_task
                    parameters = inspect.signature(submit).parameters
                    result = (
                        submit(task_id, goal_lineage=extract_queue_lineage(task_payload))
                        if "goal_lineage" in parameters
                        else submit(task_id)
                    )
                elif hasattr(scheduler, "enqueue_task"):
                    result = scheduler.enqueue_task(task_id)
                elif hasattr(scheduler, "enqueue"):
                    result = scheduler.enqueue(task_id)
                else:
                    result = {"ok": False, "error": "scheduler_has_no_submit_or_enqueue_api"}

                if isinstance(result, dict):
                    item = copy.deepcopy(result)
                    item.setdefault("task_id", task_id)
                    item.setdefault("action", "scheduler_requeue")
                else:
                    item = {
                        "ok": bool(result),
                        "task_id": task_id,
                        "action": "scheduler_requeue",
                        "result": result,
                    }
                item["lineage"] = extract_queue_lineage(task_payload if isinstance(task_payload, Mapping) else {})
                item["queue_identity_preserved"] = True
                updates.append(item)
            except Exception as exc:
                updates.append(
                    {
                        "ok": False,
                        "task_id": task_id,
                        "action": "scheduler_requeue_failed",
                        "error": f"{exc.__class__.__name__}: {exc}",
                    }
                )
        return updates

    def _record_persistent_engineering_resume(
        self,
        *,
        agent_loop: Any,
        record: RuntimeSessionResumeRecord,
        resume_plan: Mapping[str, Any],
        continuation_plan: Mapping[str, Any],
        repository_updates: List[Dict[str, Any]],
        scheduler_updates: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if PersistentEngineeringSession is None:
            return {"ok": False, "reason": "persistent_engineering_session_unavailable"}

        try:
            lineage_by_task_id = resume_plan.get("lineage_by_task_id")
            resume_identities = [
                extract_runtime_identity(item, reject_conflicts=True)
                for item in (lineage_by_task_id.values() if isinstance(lineage_by_task_id, Mapping) else [])
                if isinstance(item, Mapping)
            ]
            session_ids = {item.get("session_id", "") for item in resume_identities}
            session_ids.discard("")
            if len(session_ids) > 1 or (session_ids and record.session_id not in session_ids):
                raise ValueError("resume_plan_conflicting_session_identity")
            runtime_session_ids = {item.get("runtime_session_id", "") for item in resume_identities}
            runtime_session_ids.discard("")
            if len(runtime_session_ids) > 1:
                raise ValueError("resume_plan_conflicting_runtime_session_identity")
            runtime_session_id = next(iter(runtime_session_ids), "")
            session = PersistentEngineeringSession(
                repo_root=self.repo_root,
                workflow_id=record.session_id or "runtime_resume",
                session_id=f"resume_{stable_resume_fingerprint(record.to_dict())[:12]}",
                goal="Resume persistent runtime session",
            )
            session.initialize()
            resume_point = session.create_resume_point(
                reason="persistent_runtime_orchestrator_resume",
                cursor={
                    "session_id": record.session_id,
                    "runtime_session_id": runtime_session_id,
                    "resume_plan_fingerprint": resume_plan.get("fingerprint"),
                    "continuation_fingerprint": continuation_plan.get("fingerprint"),
                },
                required_inputs=[],
            )
            continuation = session.record_continuation(
                resume_id=str(resume_point.get("resume_id") or ""),
                continuation_result={
                    "resume_plan": _safe_dict(resume_plan),
                    "continuation_plan": _safe_dict(continuation_plan),
                    "repository_updates": _safe_list(repository_updates),
                    "scheduler_updates": _safe_list(scheduler_updates),
                    "agent_loop_attached": agent_loop is not None,
                },
                status="scheduler_requeue_requested",
            )
            return {
                "ok": True,
                "summary": session.summary(),
                "resume_point": resume_point,
                "continuation": continuation,
            }
        except Exception as exc:
            return {
                "ok": False,
                "reason": "persistent_engineering_session_record_failed",
                "error": f"{exc.__class__.__name__}: {exc}",
            }

    def _append_audit(self, event: Mapping[str, Any]) -> None:
        payload = _read_json(self.audit_path)
        if not payload:
            payload = {
                "ok": True,
                "schema": SCHEMA,
                "workspace_dir": str(self.workspace_dir),
                "repo_root": str(self.repo_root),
                "events": [],
                "created_at": _now(),
            }
        events = payload.setdefault("events", [])
        if not isinstance(events, list):
            payload["events"] = []
        events = payload["events"]
        item = _safe_dict(event)
        item.setdefault("created_at", _now())
        events.append(item)
        payload["updated_at"] = _now()
        _write_json(self.audit_path, payload)

    def _result(self, **fields: Any) -> Dict[str, Any]:
        started_at = float(fields.pop("started_at", _now()) or _now())
        payload = {
            "ok": bool(fields.pop("ok", True)),
            "schema": SCHEMA,
            "workspace_dir": str(self.workspace_dir),
            "repo_root": str(self.repo_root),
            "resume_store_path": str(self.resume_store_path),
            "audit_path": str(self.audit_path),
            "created_at": _now(),
            "elapsed_seconds": max(0.0, _now() - started_at),
        }
        payload.update(fields)
        return payload


def resume_last_persistent_runtime_session(
    *,
    task_repository: Any,
    scheduler: Any = None,
    agent_loop: Any = None,
    session_id: str | None = None,
    repo_root: str | Path = ".",
    workspace_dir: str | Path = "workspace",
    resume_store_path: str | Path | None = None,
    persist: bool = True,
    force: bool = False,
) -> Dict[str, Any]:
    orchestrator = PersistentRuntimeOrchestrator(
        repo_root=repo_root,
        workspace_dir=workspace_dir,
        resume_store_path=resume_store_path,
    )
    return orchestrator.resume_last_session(
        task_repository=task_repository,
        scheduler=scheduler,
        agent_loop=agent_loop,
        session_id=session_id,
        persist=persist,
        force=force,
    )


def run_persistent_runtime_orchestrator(
    *,
    task_repository: Any = None,
    scheduler: Any = None,
    agent_loop: Any = None,
    repo_root: str | Path = ".",
    workspace_dir: str | Path = "workspace",
    resume_store_path: str | Path | None = None,
    persist: bool = True,
    force: bool = False,
    task: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
    result: Mapping[str, Any] | None = None,
    executor: Any = None,
    fail_cycle_index: int | None = None,
    fail_group_index: int | None = None,
) -> Dict[str, Any]:
    """Compatibility entrypoint for planner/runtime dispatch.

    Supports both historical call styles:
    - repository resume: pass task_repository and optional scheduler/agent_loop
    - direct persistent-runtime contract: pass task/cycles for the multi-cycle
      orchestrator path used by planner dispatch tests.
    """
    if isinstance(task, Mapping):
        if executor is not None:
            return _execute_persistent_runtime_task_with_executor(
                repo_root=repo_root,
                workspace_dir=workspace_dir,
                task=task,
                executor=executor,
                force=force,
                fail_group_index=fail_group_index,
            )

        return _simulate_persistent_runtime_orchestrator_contract(
            repo_root=repo_root,
            workspace_dir=workspace_dir,
            task=task,
            force=force,
            fail_cycle_index=fail_cycle_index,
            fail_group_index=fail_group_index,
        )

    if task_repository is None:
        empty_task: Dict[str, Any] = {"goal": ""}
        return _simulate_persistent_runtime_orchestrator_contract(
            repo_root=repo_root,
            workspace_dir=workspace_dir,
            task=empty_task,
            force=force,
            fail_cycle_index=fail_cycle_index,
            fail_group_index=fail_group_index,
        )

    return resume_last_persistent_runtime_session(
        task_repository=task_repository,
        scheduler=scheduler,
        agent_loop=agent_loop,
        repo_root=repo_root,
        workspace_dir=workspace_dir,
        resume_store_path=resume_store_path,
        persist=persist,
        force=force,
    )


def run_adaptive_runtime_resume(*, task_runner: Any, task: Dict[str, Any], execution_contract: Any, current_tick: int = 0) -> Dict[str, Any]:
    """Delegate a completed adaptive execution contract to TaskRunner."""
    return task_runner.run_task_adaptive(
        task=task,
        execution_contract=execution_contract,
        current_tick=current_tick,
    )


__all__ = [
    "SCHEMA",
    "PersistentRuntimeOrchestrator",
    "should_route_persistent_runtime",
    "resume_last_persistent_runtime_session",
    "run_adaptive_runtime_resume",
    "run_persistent_runtime_orchestrator",
]
