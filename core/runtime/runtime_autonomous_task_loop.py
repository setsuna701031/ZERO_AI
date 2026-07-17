from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Callable, Mapping

from core.runtime.task_runtime import project_runtime_status


RUNTIME_AUTONOMOUS_TASK_LOOP_SCHEMA = "zero.runtime.autonomous_task_loop.v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _stable_id(prefix: str, *parts: Any) -> str:
    body = "|".join(_text(part) for part in parts if _text(part))
    digest = sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _result_ok(result: Mapping[str, Any]) -> bool:
    payload = _mapping(result)
    if payload.get("ok") is not True:
        return False

    if payload.get("repair_loop_status") in {"repaired", "completed"}:
        return True

    repair_loop_result = _mapping(payload.get("repair_loop_result"))
    if repair_loop_result:
        return repair_loop_result.get("ok") is True

    operator_result = _mapping(payload.get("operator_result"))
    mutation_result = _mapping(operator_result.get("controlled_mutation_result"))
    if mutation_result:
        return (
            mutation_result.get("ok") is True
            and mutation_result.get("mutation_completed") is True
            and mutation_result.get("validation_passed") is True
        )

    return True


@dataclass
class RuntimeAutonomousTaskQueue:
    tasks: list[dict[str, Any]] = field(default_factory=list)

    def add_task(
        self,
        goal: Any,
        *,
        task_id: Any = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_goal = _text(goal)
        if not normalized_goal:
            return {
                "schema": RUNTIME_AUTONOMOUS_TASK_LOOP_SCHEMA,
                "ok": False,
                "queue_status": "denied",
                "denial_reason": "task_goal_required",
                "task": {},
            }

        task = {
            "task_id": _text(task_id)
            or _stable_id("autonomous-task", normalized_goal, len(self.tasks)),
            "goal": normalized_goal,
            "status": "queued",
            "attempts": 0,
            "metadata": _mapping(metadata),
        }
        self.tasks.append(task)

        return {
            "schema": RUNTIME_AUTONOMOUS_TASK_LOOP_SCHEMA,
            "ok": True,
            "queue_status": "queued",
            "task": deepcopy(task),
            "queue_depth": len(self.tasks),
        }

    def next_task(self) -> dict[str, Any] | None:
        for task in self.tasks:
            if task.get("status") == "queued":
                return task
        return None

    def snapshot(self) -> list[dict[str, Any]]:
        return deepcopy(self.tasks)


@dataclass
class RuntimeAutonomousTaskLoop:
    runner: Callable[[str], Mapping[str, Any]]
    queue: RuntimeAutonomousTaskQueue = field(
        default_factory=RuntimeAutonomousTaskQueue
    )
    max_tasks: int = 10
    self_repair: bool = True

    def submit(
        self,
        goal: Any,
        *,
        task_id: Any = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.queue.add_task(
            goal,
            task_id=task_id,
            metadata=metadata,
        )

    def run_once(self) -> dict[str, Any]:
        task = self.queue.next_task()
        if task is None:
            return {
                "schema": RUNTIME_AUTONOMOUS_TASK_LOOP_SCHEMA,
                "ok": True,
                "loop_status": "idle",
                "task": {},
                "result": {},
                "queue": self.queue.snapshot(),
            }

        project_runtime_status(task, "running")
        task["attempts"] = int(task.get("attempts") or 0) + 1

        result = _mapping(self.runner(_text(task.get("goal"))))
        task["last_result"] = result

        if _result_ok(result):
            project_runtime_status(task, "completed")
            task["completed"] = True
        else:
            project_runtime_status(task, "failed")
            task["completed"] = False
            task["denial_reason"] = _text(result.get("denial_reason"))

        return {
            "schema": RUNTIME_AUTONOMOUS_TASK_LOOP_SCHEMA,
            "ok": task["status"] == "completed",
            "loop_status": task["status"],
            "task": deepcopy(task),
            "result": result,
            "queue": self.queue.snapshot(),
        }

    def run_until_idle(self) -> dict[str, Any]:
        cycles: list[dict[str, Any]] = []

        for _ in range(max(1, self.max_tasks)):
            cycle = self.run_once()
            cycles.append(cycle)
            if cycle.get("loop_status") == "idle":
                break

        completed = [
            task for task in self.queue.tasks if task.get("status") == "completed"
        ]
        failed = [
            task for task in self.queue.tasks if task.get("status") == "failed"
        ]
        queued = [
            task for task in self.queue.tasks if task.get("status") == "queued"
        ]

        return {
            "schema": RUNTIME_AUTONOMOUS_TASK_LOOP_SCHEMA,
            "ok": not failed and not queued,
            "loop_status": "idle" if not queued else "max_tasks_reached",
            "cycles": cycles,
            "completed_count": len(completed),
            "failed_count": len(failed),
            "queued_count": len(queued),
            "queue": self.queue.snapshot(),
        }


__all__ = [
    "RUNTIME_AUTONOMOUS_TASK_LOOP_SCHEMA",
    "RuntimeAutonomousTaskLoop",
    "RuntimeAutonomousTaskQueue",
]
