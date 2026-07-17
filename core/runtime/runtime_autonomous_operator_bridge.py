from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from core.runtime.runtime_autonomous_task_loop import (
    RUNTIME_AUTONOMOUS_TASK_LOOP_SCHEMA,
    RuntimeAutonomousTaskLoop,
    RuntimeAutonomousTaskQueue,
)


RUNTIME_AUTONOMOUS_OPERATOR_BRIDGE_SCHEMA = (
    "zero.runtime.autonomous_operator_bridge.v1"
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _default_runner_unavailable(goal: str) -> dict[str, Any]:
    return {
        "schema": RUNTIME_AUTONOMOUS_OPERATOR_BRIDGE_SCHEMA,
        "ok": False,
        "natural_task": goal,
        "denial_reason": "natural_task_runner_unavailable",
        "operator_result": {
            "controlled_mutation_result": {
                "ok": False,
                "mutation_completed": False,
                "validation_passed": False,
                "denial_reason": "natural_task_runner_unavailable",
            }
        },
    }


@dataclass
class RuntimeAutonomousOperatorBridge:
    runner: Callable[[str], Mapping[str, Any]] | None = None
    queue: RuntimeAutonomousTaskQueue = field(
        default_factory=RuntimeAutonomousTaskQueue
    )
    max_tasks: int = 10
    controlled: bool = True
    self_repair: bool = True

    def _runner(self, goal: str) -> Mapping[str, Any]:
        if self.runner is not None:
            return self.runner(goal)

        try:
            from cli.zero_natural_task import run_natural_task
        except Exception:
            return _default_runner_unavailable(goal)

        return run_natural_task(
            goal,
            controlled=self.controlled,
            self_repair=self.self_repair,
        )

    def submit(
        self,
        goal: Any,
        *,
        task_id: Any = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        queued = self.queue.add_task(
            goal,
            task_id=task_id,
            metadata=metadata,
        )
        return {
            "schema": RUNTIME_AUTONOMOUS_OPERATOR_BRIDGE_SCHEMA,
            "ok": queued.get("ok") is True,
            "bridge_status": queued.get("queue_status") or "denied",
            "task": _mapping(queued.get("task")),
            "queue_depth": queued.get("queue_depth") or 0,
            "denial_reason": _text(queued.get("denial_reason")),
        }

    def run_once(self) -> dict[str, Any]:
        loop = RuntimeAutonomousTaskLoop(
            runner=self._runner,
            queue=self.queue,
            max_tasks=self.max_tasks,
            self_repair=self.self_repair,
        )
        result = loop.run_once()
        return {
            "schema": RUNTIME_AUTONOMOUS_OPERATOR_BRIDGE_SCHEMA,
            "ok": result.get("ok") is True,
            "bridge_status": result.get("loop_status") or "",
            "loop_schema": result.get("schema")
            or RUNTIME_AUTONOMOUS_TASK_LOOP_SCHEMA,
            "task": _mapping(result.get("task")),
            "result": _mapping(result.get("result")),
            "queue": result.get("queue") or [],
        }

    def run_until_idle(self) -> dict[str, Any]:
        loop = RuntimeAutonomousTaskLoop(
            runner=self._runner,
            queue=self.queue,
            max_tasks=self.max_tasks,
            self_repair=self.self_repair,
        )
        result = loop.run_until_idle()
        return {
            "schema": RUNTIME_AUTONOMOUS_OPERATOR_BRIDGE_SCHEMA,
            "ok": result.get("ok") is True,
            "bridge_status": result.get("loop_status") or "",
            "loop_schema": result.get("schema")
            or RUNTIME_AUTONOMOUS_TASK_LOOP_SCHEMA,
            "cycles": result.get("cycles") or [],
            "completed_count": result.get("completed_count") or 0,
            "failed_count": result.get("failed_count") or 0,
            "queued_count": result.get("queued_count") or 0,
            "queue": result.get("queue") or [],
        }


__all__ = [
    "RUNTIME_AUTONOMOUS_OPERATOR_BRIDGE_SCHEMA",
    "RuntimeAutonomousOperatorBridge",
]
