from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.runtime.task_runner import TaskRunner
from core.runtime.task_runtime import TaskRuntime
from core.runtime.work_package_queue import RuntimePackageQueue, RuntimePackageQueueError
from core.tasks.scheduler_runtime_contract import (
    SCHEDULER_RUNTIME_TRANSITIONS,
    seal_scheduler_runtime_contract,
    validate_scheduler_lifecycle_transition,
)


RUNTIME_DISPATCH_SCHEMA = "zero.runtime.work_package_dispatch.v1"
RUNTIME_LIFECYCLE_STATES = frozenset(
    {"planned", "claimed", "executing", "paused", "blocked", "failed", "completed"}
)
RUNTIME_TERMINAL_STATES = frozenset({"failed", "completed"})
RUNTIME_TRANSITIONS = SCHEDULER_RUNTIME_TRANSITIONS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_runtime_transition(from_state: str, to_state: str) -> bool:
    return validate_scheduler_lifecycle_transition(from_state, to_state)


class RuntimeDispatcher:
    """Runtime-owned autonomous package dispatcher through TaskRunner."""

    def __init__(
        self,
        *,
        queue: RuntimePackageQueue,
        task_runner: Any = None,
        workspace_root: str | Path = "workspace",
    ) -> None:
        self.queue = queue
        self.workspace_root = Path(workspace_root)
        self.task_runner = task_runner or TaskRunner(
            task_runtime=TaskRuntime(workspace_root=str(self.workspace_root))
        )

    def dispatch(self, package_id: str) -> dict[str, Any]:
        record = self.queue.claim(package_id)
        task = self._execution_task(record)
        session = self.queue.start_execution_session(package_id, task=task)
        steps = task["steps"]

        for tick in range(len(steps)):
            current = self.queue.status(package_id)
            if current.get("status") == "paused":
                return current
            try:
                result = self.task_runner.run_task(task=task, current_tick=tick)
            except Exception as exc:
                root_cause = f"taskrunner_dispatch_failed:{type(exc).__name__}:{exc}"
                return self.queue.record_runtime_failure(
                    package_id,
                    root_cause=root_cause,
                    evidence={"tick": tick, "exception": root_cause},
                    blocked=False,
                )

            feedback = self._step_feedback(task=task, result=result, tick=tick)
            record = self.queue.record_step_feedback(package_id, feedback)
            if not feedback["ok"]:
                blocked = feedback["runtime_status"] in {"blocked", "waiting", "paused"}
                return self.queue.record_runtime_failure(
                    package_id,
                    root_cause=feedback["root_cause"],
                    evidence=feedback,
                    blocked=blocked,
                )
            task = self._next_task(task, result, feedback)

        return self.queue.record_runtime_completed(package_id)

    def dispatch_next(self) -> dict[str, Any] | None:
        record = self.queue.next_planned()
        if record is None:
            return None
        return self.dispatch(str(record["package_id"]))

    def progress(self, package_id: str) -> dict[str, Any]:
        return self.queue.runtime_progress(package_id)

    def _execution_task(self, record: Mapping[str, Any]) -> dict[str, Any]:
        item = record.get("runtime_queue_item")
        if not isinstance(item, Mapping):
            raise RuntimePackageQueueError("planned_package_missing_runtime_queue_item")
        package_id = str(record.get("package_id") or "")
        task_id = str(record.get("task_id") or "")
        task_dir = self.workspace_root / "runtime_packages" / package_id / task_id
        authority = {
            "task_id": task_id,
            "step_id": f"{task_id}:runtime-dispatch",
            "authority_source": "runtime_dispatcher",
            "authority_status": "allowed",
            "execution_authority_endpoint": "step_executor",
            "action_type": "runtime_execution",
            "ownership_source": "core.runtime.runtime_dispatcher",
            "runtime_session": str(record.get("session_id") or ""),
            "approval_state": "approved",
            "policy_result": {"allowed": True, "source": "runtime_dispatcher"},
            "trace_id": f"trace:{package_id}:{task_id}",
        }
        task = {
            **copy.deepcopy(dict(item)),
            "id": task_id,
            "task_id": task_id,
            "task_name": task_id,
            "package_id": package_id,
            "session_id": str(record.get("session_id") or ""),
            "status": "queued",
            "task_dir": str(task_dir),
            "runtime_state_file": str(task_dir / "runtime_state.json"),
            "current_step_index": 0,
            "results": [],
            "max_auto_ticks": 1,
            "execution_authority": authority,
            "authority_context": {
                "authority_layer": "runtime",
                "authority_role": "runtime_owner",
                "authority_source": "runtime_dispatcher",
                "execution_authority": copy.deepcopy(authority),
                "authority_chain": [
                    {
                        "layer": "runtime_dispatcher",
                        "authority_role": "runtime_owner",
                        "execution_authority_granted": False,
                        "can_execute_privileged_step": False,
                    }
                ],
            },
            "authority_propagation_required": True,
        }
        task["scheduler_runtime_contract"] = seal_scheduler_runtime_contract(
            task,
            lifecycle_state="claimed",
            dispatch_path="RuntimeDispatcher -> TaskRunner -> Scheduler -> step_executor",
            require_package_identity=True,
            require_session_identity=True,
            require_authority_metadata=True,
        )
        return task

    @staticmethod
    def _step_feedback(*, task: Mapping[str, Any], result: Any, tick: int) -> dict[str, Any]:
        payload = copy.deepcopy(dict(result)) if isinstance(result, Mapping) else {"ok": False}
        state = payload.get("runtime_state") if isinstance(payload.get("runtime_state"), Mapping) else {}
        current = int(
            payload.get("current_step_index")
            or state.get("current_step_index")
            or task.get("current_step_index")
            or 0
        )
        status = str(payload.get("status") or state.get("status") or "").lower()
        ok = bool(payload.get("ok")) and status not in {"failed", "blocked", "cancelled"}
        error = payload.get("error") or state.get("last_error")
        return {
            "schema": RUNTIME_DISPATCH_SCHEMA,
            "timestamp": _now(),
            "tick": tick,
            "step_index": max(0, current - 1 if current else tick),
            "current_step": current,
            "ok": ok,
            "runtime_status": status or ("executing" if ok else "failed"),
            "root_cause": "" if ok else str(error or "runtime_step_failed"),
            "evidence": payload,
            "authority": copy.deepcopy(task.get("execution_authority")),
        }

    @staticmethod
    def _next_task(
        task: Mapping[str, Any],
        result: Mapping[str, Any],
        feedback: Mapping[str, Any],
    ) -> dict[str, Any]:
        next_task = copy.deepcopy(dict(task))
        result_task = result.get("task") if isinstance(result.get("task"), Mapping) else {}
        next_task.update(copy.deepcopy(dict(result_task)))
        next_task["current_step_index"] = int(feedback.get("current_step") or 0)
        next_task["status"] = "running"
        return next_task


__all__ = [
    "RUNTIME_DISPATCH_SCHEMA",
    "RUNTIME_LIFECYCLE_STATES",
    "RUNTIME_TERMINAL_STATES",
    "RuntimeDispatcher",
    "validate_runtime_transition",
]
