from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from core.runtime.runtime_autonomous_operator_bridge import (
    RuntimeAutonomousOperatorBridge,
)
from core.runtime.runtime_operator_activity_log import RuntimeOperatorActivityLog


RUNTIME_AUTONOMOUS_SENTINEL_SCHEMA = "zero.runtime.autonomous_sentinel.v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _task_from_result(result: Mapping[str, Any]) -> dict[str, Any]:
    task = result.get("task")
    return _mapping(task)


def _activity_result_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    payload = _mapping(result.get("result"))
    if payload:
        return payload
    return _mapping(result)


@dataclass
class RuntimeAutonomousSentinel:
    bridge: RuntimeAutonomousOperatorBridge
    max_cycles: int = 10
    on_idle: Callable[[int], None] | None = None
    activity_log: RuntimeOperatorActivityLog | None = None
    cycle_log: list[dict[str, Any]] = field(default_factory=list)

    def _record_activity(self, result: Mapping[str, Any]) -> dict[str, Any]:
        if self.activity_log is None:
            return {
                "schema": "zero.runtime.operator_activity_log.v1",
                "ok": True,
                "activity_status": "disabled",
                "record": {},
                "log_path": "",
            }

        status = _text(result.get("bridge_status"))
        if status not in {"completed", "failed"}:
            return {
                "schema": "zero.runtime.operator_activity_log.v1",
                "ok": True,
                "activity_status": "skipped",
                "record": {},
                "log_path": str(self.activity_log.log_path),
            }

        task = _task_from_result(result)
        goal = _text(task.get("goal"))
        task_id = _text(task.get("task_id"))
        task_result = _activity_result_payload(result)

        return self.activity_log.append(
            goal=goal,
            task_id=task_id,
            source="runtime_autonomous_sentinel",
            result=task_result,
            metadata={
                "bridge_status": status,
                "task_status": _text(task.get("status")),
                "attempts": int(task.get("attempts") or 0),
            },
        )

    def tick(self) -> dict[str, Any]:
        result = self.bridge.run_once()
        status = _text(result.get("bridge_status")) or "unknown"
        activity_result = self._record_activity(result)

        cycle = {
            "cycle": len(self.cycle_log) + 1,
            "status": status,
            "ok": result.get("ok") is True,
            "result": result,
            "activity_result": activity_result,
        }
        self.cycle_log.append(cycle)

        return {
            "schema": RUNTIME_AUTONOMOUS_SENTINEL_SCHEMA,
            "ok": result.get("ok") is True or status == "idle",
            "sentinel_status": status,
            "cycle": cycle["cycle"],
            "result": result,
            "activity_recorded": activity_result.get("activity_status") == "recorded",
            "activity_result": activity_result,
            "cycle_log": list(self.cycle_log),
        }

    def run(self) -> dict[str, Any]:
        cycles: list[dict[str, Any]] = []

        for cycle_index in range(1, max(1, self.max_cycles) + 1):
            tick_result = self.tick()
            cycles.append(tick_result)

            if tick_result.get("sentinel_status") == "idle":
                if self.on_idle is not None:
                    self.on_idle(cycle_index)
                break

        failed = [
            cycle
            for cycle in cycles
            if cycle.get("sentinel_status") == "failed"
        ]
        completed = [
            cycle
            for cycle in cycles
            if cycle.get("sentinel_status") == "completed"
        ]
        idle = [
            cycle
            for cycle in cycles
            if cycle.get("sentinel_status") == "idle"
        ]
        activity_records = [
            cycle
            for cycle in cycles
            if cycle.get("activity_recorded") is True
        ]

        return {
            "schema": RUNTIME_AUTONOMOUS_SENTINEL_SCHEMA,
            "ok": not failed,
            "sentinel_status": "idle" if idle else "max_cycles_reached",
            "cycles": cycles,
            "cycle_count": len(cycles),
            "completed_count": len(completed),
            "failed_count": len(failed),
            "idle_count": len(idle),
            "activity_record_count": len(activity_records),
            "cycle_log": list(self.cycle_log),
        }


__all__ = [
    "RUNTIME_AUTONOMOUS_SENTINEL_SCHEMA",
    "RuntimeAutonomousSentinel",
]
