from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.memory.work_package_memory import WorkPackageMemoryStore
from core.tasks.work_package_model import WORK_PACKAGE_TERMINAL_STATUSES, WorkPackage
from core.tasks.scheduler_runtime_contract import (
    SCHEDULER_RUNTIME_TRANSITIONS,
    validate_scheduler_lifecycle_transition,
)


QUEUE_SCHEMA = "zero.runtime.work_package_queue.v1"
SESSION_RESUME_SCHEMA = "zero.runtime.work_package_session_resume.v1"
ACTIVE_STATUSES = frozenset({"queued", "running", "paused", "blocked"})
RUNTIME_TRANSITIONS = SCHEDULER_RUNTIME_TRANSITIONS


class RuntimePackageQueueError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def work_package_execution_path() -> dict[str, Any]:
    return {
        "direct_execution": False,
        "runtime_owns_execution": True,
        "taskrunner_required": True,
        "step_executor_endpoint_only": True,
        "authority_path": (
            "WorkPackageIntake -> RuntimePackageQueue -> "
            "AgentExecutionRuntime -> TaskRunner -> StepExecutor"
        ),
        "runtime_endpoint": "AgentExecutionRuntime.run_task",
    }


class RuntimePackageQueue:
    def __init__(
        self,
        *,
        repo_root: str | Path = ".",
        state_dir: str | Path = "workspace/runtime_work_packages",
        memory_store: WorkPackageMemoryStore | None = None,
    ) -> None:
        root = Path(repo_root)
        self.repo_root = root
        candidate = Path(state_dir)
        self.state_dir = candidate if candidate.is_absolute() else root / candidate
        self.memory_store = memory_store or WorkPackageMemoryStore(
            root / "workspace" / "work_package_memory"
        )

    def _path(self, package_id: str) -> Path:
        safe = "".join(
            char if char.isalnum() or char in "-_." else "_" for char in str(package_id)
        ).strip("._-")
        if not safe:
            raise RuntimePackageQueueError("package_id_required")
        return self.state_dir / f"{safe}.json"

    def _read(self, package_id: str) -> dict[str, Any]:
        path = self._path(package_id)
        if not path.is_file():
            raise RuntimePackageQueueError(f"work_package_not_found:{package_id}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimePackageQueueError(f"invalid_work_package_record:{package_id}")
        return payload

    def _write(self, record: Mapping[str, Any]) -> dict[str, Any]:
        payload = copy.deepcopy(dict(record))
        path = self._path(str(payload.get("package_id") or ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return payload

    def _session_resume_contract(self, record: Mapping[str, Any]) -> dict[str, Any]:
        progress = record.get("progress") if isinstance(record.get("progress"), Mapping) else {}
        runtime_state = (
            copy.deepcopy(dict(record.get("runtime_state")))
            if isinstance(record.get("runtime_state"), Mapping)
            else {}
        )
        queue_item = (
            copy.deepcopy(dict(record.get("runtime_queue_item")))
            if isinstance(record.get("runtime_queue_item"), Mapping)
            else {}
        )
        active_steps = copy.deepcopy(queue_item.get("steps") or runtime_state.get("steps") or [])
        feedback = record.get("step_feedback") if isinstance(record.get("step_feedback"), list) else []
        completed_step_ids = [
            str(item.get("step_id") or "")
            for item in feedback
            if isinstance(item, Mapping) and item.get("ok") and str(item.get("step_id") or "")
        ]
        failed_step_ids = [
            str(item.get("step_id") or "")
            for item in feedback
            if isinstance(item, Mapping) and not item.get("ok") and str(item.get("step_id") or "")
        ]
        return {
            "schema": SESSION_RESUME_SCHEMA,
            "session_id": record.get("session_id"),
            "task_id": record.get("task_id"),
            "package_id": record.get("package_id"),
            "active_graph": {
                "task_graph": copy.deepcopy(record.get("task_graph") or {}),
                "steps": active_steps,
                "cursor": int(progress.get("current_step") or record.get("current_step") or 0),
            },
            "completed_steps": {
                "count": int(progress.get("completed_steps") or 0),
                "step_ids": completed_step_ids,
            },
            "failed_steps": {
                "count": int(progress.get("failed_steps") or 0),
                "step_ids": failed_step_ids,
            },
            "replan_history": copy.deepcopy(record.get("replan_history") or []),
            "memory_summary": {
                "status": record.get("memory_status") or "pending",
                "memory_record_id": record.get("memory_record_id"),
                "evidence_count": len(record.get("execution_evidence") or []),
                "replan_count": len(record.get("replan_history") or []),
            },
            "last_runtime_state": runtime_state,
            "captured_at": _now(),
            "resume_policy": {
                "queue_is_session_owner": True,
                "do_not_replan": True,
                "do_not_recreate_package": True,
                "do_not_repeat_completed_steps": True,
                "preserve_evidence": True,
            },
        }

    def _checkpoint_session(self, record: Mapping[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(dict(record))
        result["session_resume_contract"] = self._session_resume_contract(result)
        return result

    def _commit_terminal_memory(self, record: Mapping[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(dict(record))
        status = str(result.get("status") or "").lower()
        if status not in {"completed", "blocked", "failed", "cancelled"}:
            result["memory_status"] = "pending"
            return result
        memory = self.memory_store.commit_terminal(result)
        result["memory_status"] = "committed"
        result["memory_record_id"] = memory["memory_record_id"]
        result["memory_committed_at"] = memory["committed_at"]
        return result

    def _transition(
        self,
        record: Mapping[str, Any],
        to_status: str,
        *,
        reason: str,
        runtime_state: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = copy.deepcopy(dict(record))
        from_status = str(result.get("status") or "")
        if from_status in WORK_PACKAGE_TERMINAL_STATUSES:
            raise RuntimePackageQueueError(f"terminal_package_cannot_transition:{from_status}")
        timestamp = _now()
        transition = {
            "from": from_status,
            "to": to_status,
            "reason": reason,
            "timestamp": timestamp,
            "session_id": result.get("session_id"),
            "task_id": result.get("task_id"),
        }
        result["status"] = to_status
        result["lifecycle_state"] = to_status
        result["updated_at"] = timestamp
        result["last_transition"] = transition
        result.setdefault("transition_history", []).append(copy.deepcopy(transition))
        if runtime_state is not None:
            result["runtime_state"] = copy.deepcopy(dict(runtime_state))
        else:
            result["runtime_state"] = copy.deepcopy(
                result.get("runtime_state")
                if isinstance(result.get("runtime_state"), Mapping)
                else {}
            )
            result["runtime_state"]["status"] = to_status
        result = self._commit_terminal_memory(result)
        result["progress_snapshot"] = self._progress_snapshot(result)
        return self._write(result)

    def _runtime_transition(
        self,
        record: Mapping[str, Any],
        to_state: str,
        *,
        reason: str,
    ) -> dict[str, Any]:
        result = copy.deepcopy(dict(record))
        from_state = str(result.get("runtime_lifecycle_state") or "")
        if not validate_scheduler_lifecycle_transition(from_state, to_state):
            raise RuntimePackageQueueError(
                f"invalid_runtime_lifecycle_transition:{from_state}:{to_state}"
            )
        transition = {
            "from": from_state,
            "to": to_state,
            "reason": reason,
            "timestamp": _now(),
            "package_id": result.get("package_id"),
            "session_id": result.get("session_id"),
            "task_id": result.get("task_id"),
        }
        result["runtime_lifecycle_state"] = to_state
        result["runtime_last_transition"] = transition
        result.setdefault("runtime_lifecycle_history", []).append(copy.deepcopy(transition))
        result["updated_at"] = transition["timestamp"]
        return result

    def enqueue(self, package: WorkPackage | Mapping[str, Any]) -> dict[str, Any]:
        package_record = package.to_dict() if isinstance(package, WorkPackage) else dict(package)
        package_id = str(package_record.get("package_id") or "")
        path = self._path(package_id)
        if path.exists():
            return self._read(package_id)
        timestamp = _now()
        transition = {
            "from": None,
            "to": "queued",
            "reason": "package_submitted",
            "timestamp": timestamp,
            "session_id": package_record.get("session_id"),
            "task_id": package_record.get("task_id"),
        }
        record = {
            **copy.deepcopy(package_record),
            "schema": QUEUE_SCHEMA,
            "status": "queued",
            "lifecycle_state": "queued",
            "runtime_state": {
                "status": "queued",
                "execution_path": work_package_execution_path(),
            },
            "transition_history": [transition],
            "last_transition": transition,
            "progress_snapshot": self._progress_snapshot(package_record, status="queued"),
            "execution_path": work_package_execution_path(),
        }
        return self._write(record)

    def claim_next(self) -> dict[str, Any] | None:
        record = self.next_planned()
        if record is not None:
            return self.claim(str(record["package_id"]))
        return None

    dequeue = claim_next

    def next_planned(self) -> dict[str, Any] | None:
        for record in self.list_packages(status="queued"):
            if record.get("planning_status") == "planned" and isinstance(
                record.get("runtime_queue_item"), Mapping
            ):
                return record
        return None

    def claim(self, package_id: str) -> dict[str, Any]:
        record = self._read(package_id)
        if record.get("planning_status") != "planned":
            raise RuntimePackageQueueError("package_not_planned")
        runtime_queue_item = record.get("runtime_queue_item")
        if not isinstance(runtime_queue_item, Mapping):
            raise RuntimePackageQueueError("planned_package_missing_runtime_queue_item")
        if record.get("runtime_lifecycle_state") == "claimed":
            return record
        record = self._runtime_transition(record, "claimed", reason="runtime_claimed_package")
        return self._transition(
            record,
            "running",
            reason="runtime_claimed_package",
            runtime_state={
                "status": "claimed",
                "task": copy.deepcopy(dict(runtime_queue_item)),
                "steps": copy.deepcopy(runtime_queue_item.get("steps") or []),
                "execution_path": work_package_execution_path(),
            },
        )

    def pause(self, package_id: str) -> dict[str, Any]:
        record = self._read(package_id)
        if record["status"] not in {"queued", "running", "blocked"}:
            raise RuntimePackageQueueError(f"package_cannot_pause:{record['status']}")
        runtime_state = str(record.get("runtime_lifecycle_state") or "")
        if runtime_state in {"planned", "claimed", "executing"}:
            record = self._runtime_transition(record, "paused", reason="operator_paused_package")
        return self._transition(record, "paused", reason="operator_paused_package")

    def resume(self, package_id: str) -> dict[str, Any]:
        record = self._read(package_id)
        if record["status"] in WORK_PACKAGE_TERMINAL_STATUSES:
            raise RuntimePackageQueueError(f"terminal_package_cannot_resume:{record['status']}")
        if record["status"] not in {"paused", "blocked"}:
            return record
        runtime_state = str(record.get("runtime_lifecycle_state") or "")
        if runtime_state in {"paused", "blocked"}:
            record = self._runtime_transition(record, "planned", reason="operator_resumed_package")
        return self._transition(record, "queued", reason="operator_resumed_package")

    def cancel(self, package_id: str) -> dict[str, Any]:
        record = self._read(package_id)
        if record["status"] in WORK_PACKAGE_TERMINAL_STATUSES:
            return record
        return self._transition(record, "cancelled", reason="operator_cancelled_package")

    def block(self, package_id: str, *, reason: str) -> dict[str, Any]:
        record = self._read(package_id)
        record["blocked_reason"] = str(reason or "runtime_blocked")
        return self._transition(record, "blocked", reason=record["blocked_reason"])

    def complete(self, package_id: str, *, validation_summary: Any = None) -> dict[str, Any]:
        record = self._read(package_id)
        runtime_state = str(record.get("runtime_lifecycle_state") or "queued")
        if not record.get("runtime_lifecycle_state"):
            timestamp = _now()
            transition = {
                "from": None,
                "to": "queued",
                "reason": "legacy_completion_runtime_admission",
                "timestamp": timestamp,
                "package_id": record.get("package_id"),
                "session_id": record.get("session_id"),
                "task_id": record.get("task_id"),
            }
            record["runtime_lifecycle_state"] = "queued"
            record["runtime_last_transition"] = transition
            record["runtime_lifecycle_history"] = [transition]
        completion_path = {
            "queued": ("planned", "claimed", "executing"),
            "planned": ("claimed", "executing"),
            "claimed": ("executing",),
            "executing": (),
        }
        if runtime_state not in completion_path:
            raise RuntimePackageQueueError(
                f"runtime_completion_requires_executable_path:{runtime_state}"
            )
        for state in completion_path[runtime_state]:
            record = self._runtime_transition(
                record,
                state,
                reason="legacy_completion_runtime_admission",
            )
        progress = dict(record.get("progress") or {})
        progress["completion_percent"] = 100
        progress["validation_summary"] = copy.deepcopy(validation_summary)
        record["progress"] = progress
        record = self._runtime_transition(record, "completed", reason="runtime_completed_package")
        return self._transition(record, "completed", reason="runtime_completed_package")

    def fail(self, package_id: str, *, reason: str) -> dict[str, Any]:
        record = self._read(package_id)
        record["blocked_reason"] = str(reason or "runtime_failed")
        return self._transition(record, "failed", reason=record["blocked_reason"])

    def update_progress(self, package_id: str, progress: Mapping[str, Any]) -> dict[str, Any]:
        record = self._read(package_id)
        if record["status"] in WORK_PACKAGE_TERMINAL_STATUSES:
            raise RuntimePackageQueueError(f"terminal_package_cannot_update:{record['status']}")
        record["progress"] = {**dict(record.get("progress") or {}), **copy.deepcopy(dict(progress))}
        record["current_step"] = int(
            record["progress"].get("current_step") or record.get("current_step") or 0
        )
        record["updated_at"] = _now()
        record["progress_snapshot"] = self._progress_snapshot(record)
        return self._write(record)

    def record_planning(self, package_id: str, planning_snapshot: Mapping[str, Any]) -> dict[str, Any]:
        record = self._read(package_id)
        if record["status"] in WORK_PACKAGE_TERMINAL_STATUSES:
            raise RuntimePackageQueueError(f"terminal_package_cannot_plan:{record['status']}")
        snapshot = copy.deepcopy(dict(planning_snapshot))
        record["planning_snapshot"] = snapshot
        record["planning_status"] = str(snapshot.get("planning_status") or "failed")
        record["task_graph"] = copy.deepcopy(snapshot.get("task_graph") or {})
        record["task_graph_summary"] = copy.deepcopy(snapshot.get("task_graph_summary") or {})
        record["memory_context_used"] = copy.deepcopy(snapshot.get("memory_context_used") or [])
        record["runtime_queue_item"] = copy.deepcopy(snapshot.get("runtime_queue_item"))
        record["updated_at"] = _now()
        if record["planning_status"] != "planned":
            errors = snapshot.get("errors") if isinstance(snapshot.get("errors"), list) else []
            record["blocked_reason"] = str(errors[0] if errors else "work_package_planning_failed")
            return self._transition(record, "blocked", reason=record["blocked_reason"])
        if not record.get("runtime_lifecycle_state"):
            record["runtime_lifecycle_state"] = "planned"
            transition = {
                "from": None,
                "to": "planned",
                "reason": "work_package_planned",
                "timestamp": _now(),
                "package_id": record.get("package_id"),
                "session_id": record.get("session_id"),
                "task_id": record.get("task_id"),
            }
            record["runtime_last_transition"] = transition
            record["runtime_lifecycle_history"] = [transition]
        record["progress_snapshot"] = self._progress_snapshot(record)
        return self._write(record)

    def start_execution_session(self, package_id: str, *, task: Mapping[str, Any]) -> dict[str, Any]:
        record = self._read(package_id)
        record = self._runtime_transition(record, "executing", reason="execution_session_started")
        record["execution_session"] = {
            "package_id": record.get("package_id"),
            "session_id": record.get("session_id"),
            "task_id": record.get("task_id"),
            "started_at": _now(),
            "status": "executing",
            "authority": copy.deepcopy(task.get("execution_authority")),
        }
        record["runtime_state"] = {
            **copy.deepcopy(record.get("runtime_state") or {}),
            "status": "executing",
            "task": copy.deepcopy(dict(task)),
        }
        record["progress"] = {
            **copy.deepcopy(record.get("progress") or {}),
            "current_step": 0,
            "step_count": len(task.get("steps") or []),
            "completed_steps": 0,
            "failed_steps": 0,
            "completion_percent": 0,
            "remaining_steps": len(task.get("steps") or []),
        }
        record["progress_snapshot"] = self._progress_snapshot(record)
        return self._write(self._checkpoint_session(record))

    def record_step_feedback(self, package_id: str, feedback: Mapping[str, Any]) -> dict[str, Any]:
        record = self._read(package_id)
        if record.get("runtime_lifecycle_state") != "executing":
            raise RuntimePackageQueueError("step_feedback_requires_executing_package")
        item = copy.deepcopy(dict(feedback))
        evidence = copy.deepcopy(item.get("evidence"))
        record.setdefault("step_feedback", []).append(item)
        record.setdefault("execution_evidence", []).append(
            {
                "step_index": item.get("step_index"),
                "step_id": item.get("step_id"),
                "step_type": item.get("step_type"),
                "ok": bool(item.get("ok")),
                "failed": bool(item.get("failed")),
                "blocked": bool(item.get("blocked")),
                "root_cause": item.get("root_cause"),
                "output_summary": item.get("output_summary"),
                "next_action": item.get("next_action"),
                "timestamp": item.get("timestamp") or _now(),
                "evidence": evidence,
                "authority": copy.deepcopy(item.get("authority")),
            }
        )
        progress = dict(record.get("progress") or {})
        total = int(progress.get("step_count") or len(record.get("runtime_queue_item", {}).get("steps") or []))
        completed = int(progress.get("completed_steps") or 0) + (1 if item.get("ok") else 0)
        failed = int(progress.get("failed_steps") or 0) + (0 if item.get("ok") else 1)
        current = max(int(progress.get("current_step") or 0), int(item.get("current_step") or completed + failed))
        progress.update(
            {
                "current_step": current,
                "step_count": total,
                "completed_steps": completed,
                "failed_steps": failed,
                "remaining_steps": max(0, total - completed - failed),
                "completion_percent": round(((completed + failed) / total) * 100, 2) if total else 0,
            }
        )
        record["progress"] = progress
        record["current_step"] = current
        record["runtime_state"] = {
            **copy.deepcopy(record.get("runtime_state") or {}),
            "status": "executing" if item.get("ok") else item.get("runtime_status") or "failed",
            "last_step_feedback": item,
        }
        runtime_task = copy.deepcopy(record["runtime_state"].get("task") or {})
        runtime_task["steps"] = copy.deepcopy(
            (record.get("runtime_queue_item") or {}).get("steps") or runtime_task.get("steps") or []
        )
        runtime_task["current_step_index"] = current
        runtime_task["status"] = "running"
        record["runtime_state"]["task"] = runtime_task
        record["runtime_state"]["steps"] = copy.deepcopy(runtime_task["steps"])
        record["runtime_state"]["current_step_index"] = current
        record = self._runtime_transition(record, "executing", reason="runtime_step_feedback_recorded")
        record["progress_snapshot"] = self._progress_snapshot(record)
        return self._write(self._checkpoint_session(record))

    def record_replan_request(
        self,
        package_id: str,
        request: Mapping[str, Any],
    ) -> dict[str, Any]:
        record = self._read(package_id)
        if record.get("runtime_lifecycle_state") != "executing":
            raise RuntimePackageQueueError("replan_request_requires_executing_package")
        item = copy.deepcopy(dict(request))
        record.setdefault("replan_requests", []).append(item)
        record["active_replan_request"] = item
        record["updated_at"] = _now()
        return self._write(self._checkpoint_session(record))

    def append_replan_steps(
        self,
        package_id: str,
        *,
        request: Mapping[str, Any],
        steps: list[Any],
        replan_snapshot: Mapping[str, Any],
    ) -> dict[str, Any]:
        record = self._read(package_id)
        if record.get("runtime_lifecycle_state") != "executing":
            raise RuntimePackageQueueError("replan_append_requires_executing_package")
        queue_item = copy.deepcopy(record.get("runtime_queue_item") or {})
        original_steps = copy.deepcopy(queue_item.get("steps") or [])
        replan_number = len(record.get("replan_history") or []) + 1
        appended_steps: list[dict[str, Any]] = []
        for offset, raw_step in enumerate(steps, start=1):
            if not isinstance(raw_step, Mapping):
                continue
            step = copy.deepcopy(dict(raw_step))
            original_id = str(step.get("id") or step.get("step_id") or f"step-{offset}")
            step["id"] = f"replan-{replan_number}:{original_id}"
            step["replan_origin_id"] = original_id
            step["replan_request_id"] = request.get("request_id")
            appended_steps.append(step)
        if not appended_steps:
            raise RuntimePackageQueueError("replan_append_requires_steps")
        merged_steps = [*original_steps, *appended_steps]
        queue_item["steps"] = merged_steps
        record["runtime_queue_item"] = queue_item
        task_graph = copy.deepcopy(record.get("task_graph_summary") or {})
        step_types = [str(step.get("type") or "") for step in merged_steps if isinstance(step, Mapping)]
        task_graph.update(
            {
                "node_count": len(merged_steps),
                "edge_count": max(0, len(merged_steps) - 1),
                "step_types": step_types,
            }
        )
        record["task_graph_summary"] = task_graph
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        previous = ""
        for index, step in enumerate(merged_steps):
            node_id = str(step.get("id") or step.get("step_id") or f"step-{index}")
            nodes.append(
                {
                    "node_id": node_id,
                    "task_id": record.get("task_id"),
                    "step_index": index,
                    "step_type": str(step.get("type") or step.get("action") or ""),
                    "depends_on": [previous] if previous else [],
                }
            )
            if previous:
                edges.append({"from": previous, "to": node_id})
            previous = node_id
        record["task_graph"] = {"nodes": nodes, "edges": edges}
        event = {
            "request_id": request.get("request_id"),
            "root_cause": request.get("root_cause"),
            "original_step_count": len(original_steps),
            "appended_step_count": len(appended_steps),
            "appended_step_ids": [step["id"] for step in appended_steps],
            "previous_evidence_preserved": True,
            "lifecycle_history_preserved": True,
            "timestamp": _now(),
            "replan_snapshot_summary": {
                "schema": replan_snapshot.get("schema"),
                "planning_status": replan_snapshot.get("planning_status"),
                "errors": copy.deepcopy(replan_snapshot.get("errors") or []),
            },
        }
        record.setdefault("replan_history", []).append(event)
        record["last_replan_appended_steps"] = appended_steps
        progress = copy.deepcopy(record.get("progress") or {})
        progress["step_count"] = len(merged_steps)
        progress["remaining_steps"] = max(
            0,
            len(merged_steps)
            - int(progress.get("completed_steps") or 0)
            - int(progress.get("failed_steps") or 0),
        )
        record["progress"] = progress
        runtime_state = copy.deepcopy(record.get("runtime_state") or {})
        runtime_task = copy.deepcopy(runtime_state.get("task") or {})
        runtime_task["steps"] = merged_steps
        runtime_state["task"] = runtime_task
        runtime_state["steps"] = merged_steps
        runtime_state["status"] = "executing"
        record["runtime_state"] = runtime_state
        record["updated_at"] = _now()
        record["progress_snapshot"] = self._progress_snapshot(record)
        return self._write(self._checkpoint_session(record))

    def capture_session_resume(self, package_id: str, *, reason: str = "runtime_interrupted") -> dict[str, Any]:
        record = self._read(package_id)
        if record.get("runtime_lifecycle_state") != "executing":
            raise RuntimePackageQueueError("session_resume_capture_requires_executing_package")
        record["session_resume_reason"] = str(reason or "runtime_interrupted")
        record["session_resume_count"] = int(record.get("session_resume_count") or 0)
        record["updated_at"] = _now()
        return self._write(self._checkpoint_session(record))

    def load_session_resume(self, package_id: str) -> dict[str, Any]:
        record = self._read(package_id)
        if record.get("runtime_lifecycle_state") != "executing" or record.get("status") != "running":
            raise RuntimePackageQueueError("work_package_session_not_resumable")
        contract = record.get("session_resume_contract")
        if not isinstance(contract, Mapping):
            record = self._write(self._checkpoint_session(record))
            contract = record.get("session_resume_contract")
        return copy.deepcopy(dict(contract or {}))

    def mark_session_resumed(self, package_id: str) -> dict[str, Any]:
        record = self._read(package_id)
        if record.get("runtime_lifecycle_state") != "executing" or record.get("status") != "running":
            raise RuntimePackageQueueError("work_package_session_not_resumable")
        record["session_resume_count"] = int(record.get("session_resume_count") or 0) + 1
        record["last_session_resumed_at"] = _now()
        record["updated_at"] = record["last_session_resumed_at"]
        return self._write(self._checkpoint_session(record))

    def list_resumable_sessions(self) -> list[dict[str, Any]]:
        return [
            self._session_resume_contract(record)
            for record in self.list_packages(status="running")
            if record.get("runtime_lifecycle_state") == "executing"
        ]

    def record_runtime_failure(
        self,
        package_id: str,
        *,
        root_cause: str,
        evidence: Mapping[str, Any],
        blocked: bool,
    ) -> dict[str, Any]:
        record = self._read(package_id)
        target = "blocked" if blocked else "failed"
        record["root_cause"] = str(root_cause or "runtime_failure")
        record["blocked_reason"] = record["root_cause"]
        last_feedback = (
            record.get("step_feedback")[-1]
            if isinstance(record.get("step_feedback"), list) and record.get("step_feedback")
            else {}
        )
        evidence_already_recorded = bool(
            isinstance(last_feedback, Mapping)
            and evidence.get("step_index") == last_feedback.get("step_index")
            and evidence.get("timestamp") == last_feedback.get("timestamp")
        )
        if not evidence_already_recorded:
            record.setdefault("execution_evidence", []).append(copy.deepcopy(dict(evidence)))
        record = self._runtime_transition(record, target, reason=record["root_cause"])
        if target == "blocked":
            result = self._transition(record, "blocked", reason=record["root_cause"])
        else:
            result = self._transition(record, "failed", reason=record["root_cause"])
        return self._write(self._checkpoint_session(result))

    def record_runtime_completed(self, package_id: str) -> dict[str, Any]:
        record = self._read(package_id)
        record = self._runtime_transition(record, "completed", reason="all_runtime_steps_completed")
        progress = dict(record.get("progress") or {})
        total = int(progress.get("step_count") or 0)
        failed = int(progress.get("failed_steps") or 0)
        completed = int(progress.get("completed_steps") or 0)
        progress.update(
            {
                "current_step": total,
                "completed_steps": max(completed, total - failed),
                "failed_steps": failed,
                "remaining_steps": 0,
                "completion_percent": 100,
            }
        )
        record["progress"] = progress
        record["runtime_state"] = {
            **copy.deepcopy(record.get("runtime_state") or {}),
            "status": "completed",
        }
        result = self._transition(record, "completed", reason="all_runtime_steps_completed")
        return self._write(self._checkpoint_session(result))

    def runtime_progress(self, package_id: str) -> dict[str, Any]:
        return self._progress_snapshot(self._read(package_id))

    def status(self, package_id: str) -> dict[str, Any]:
        record = self._read(package_id)
        record["progress_snapshot"] = self._progress_snapshot(record)
        return record

    def list_packages(self, *, status: str | None = None, active_only: bool = False) -> list[dict[str, Any]]:
        if not self.state_dir.exists():
            return []
        records = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self.state_dir.glob("*.json"))
        ]
        if status:
            records = [record for record in records if record.get("status") == status]
        if active_only:
            records = [record for record in records if record.get("status") in ACTIVE_STATUSES]
        return records

    def list_active_packages(self) -> list[dict[str, Any]]:
        return self.list_packages(active_only=True)

    @staticmethod
    def _progress_snapshot(record: Mapping[str, Any], *, status: str | None = None) -> dict[str, Any]:
        progress = record.get("progress") if isinstance(record.get("progress"), Mapping) else {}
        current_step = int(record.get("current_step") or progress.get("current_step") or 0)
        step_count = int(progress.get("step_count") or len(record.get("requirements") or []))
        completion_percent = float(
            progress.get("completion_percent")
            or (100 if (status or record.get("status")) == "completed" else 0)
        )
        runtime_state = (
            record.get("runtime_state") if isinstance(record.get("runtime_state"), Mapping) else {}
        )
        return {
            "package_id": record.get("package_id"),
            "status": status or record.get("status"),
            "current_step": current_step,
            "step_count": step_count,
            "completion_percent": completion_percent,
            "lifecycle_state": record.get("lifecycle_state") or status or record.get("status"),
            "last_transition": copy.deepcopy(record.get("last_transition")),
            "runtime_state": copy.deepcopy(runtime_state),
            "blocked_reason": record.get("blocked_reason"),
            "validation_summary": copy.deepcopy(progress.get("validation_summary")),
            "non_mainline_findings": copy.deepcopy(progress.get("non_mainline_findings") or []),
            "planning_status": record.get("planning_status") or "pending",
            "planning_errors": copy.deepcopy(
                (record.get("planning_snapshot") or {}).get("errors") or []
            ),
            "planning_warnings": copy.deepcopy(
                (record.get("planning_snapshot") or {}).get("warnings") or []
            ),
            "task_graph_summary": copy.deepcopy(record.get("task_graph_summary") or {}),
            "runtime_queue_item": copy.deepcopy(record.get("runtime_queue_item")),
            "runtime_status": record.get("runtime_lifecycle_state") or "pending",
            "completed_steps": int(progress.get("completed_steps") or 0),
            "failed_steps": int(progress.get("failed_steps") or 0),
            "remaining_steps": int(
                progress.get("remaining_steps")
                if progress.get("remaining_steps") is not None
                else max(0, step_count - int(progress.get("completed_steps") or 0))
            ),
            "percent": completion_percent,
            "root_cause": record.get("root_cause"),
            "memory_status": record.get("memory_status") or "pending",
            "memory_record_id": record.get("memory_record_id"),
            "memory_context_used": copy.deepcopy(record.get("memory_context_used") or []),
        }


__all__ = [
    "ACTIVE_STATUSES",
    "QUEUE_SCHEMA",
    "SESSION_RESUME_SCHEMA",
    "RuntimePackageQueue",
    "RuntimePackageQueueError",
    "work_package_execution_path",
]
