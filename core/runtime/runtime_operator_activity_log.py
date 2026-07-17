from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

RUNTIME_OPERATOR_ACTIVITY_LOG_SCHEMA = "zero.runtime.operator_activity_log.v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return deepcopy(value)
    if isinstance(value, tuple):
        return list(deepcopy(value))
    return []


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _extract_changed_files(result: Mapping[str, Any]) -> list[str]:
    payload = _mapping(result)
    direct = _list(payload.get("changed_files"))
    if direct:
        return [str(item) for item in direct]

    operator_result = _mapping(payload.get("operator_result"))
    direct_operator = _list(operator_result.get("changed_files"))
    if direct_operator:
        return [str(item) for item in direct_operator]

    controlled = _mapping(operator_result.get("controlled_mutation_result"))
    changed = _list(controlled.get("changed_files"))
    if changed:
        return [str(item) for item in changed]

    governed = _mapping(operator_result.get("governed_runtime_result"))
    return [str(item) for item in _list(governed.get("applied_paths"))]


def _extract_rollback_completed(result: Mapping[str, Any]) -> bool:
    payload = _mapping(result)
    if payload.get("rollback_completed") is True:
        return True
    operator_result = _mapping(payload.get("operator_result"))
    if operator_result.get("rollback_completed") is True:
        return True
    controlled = _mapping(operator_result.get("controlled_mutation_result"))
    return controlled.get("rollback_completed") is True


def _extract_repair_attempted(result: Mapping[str, Any]) -> bool:
    payload = _mapping(result)
    if payload.get("repair_attempted") is True:
        return True
    repair_loop = _mapping(payload.get("repair_loop_result"))
    return repair_loop.get("repair_attempted") is True


def _extract_status(result: Mapping[str, Any]) -> str:
    payload = _mapping(result)
    if payload.get("ok") is True:
        return "completed"
    operator_result = _mapping(payload.get("operator_result"))
    controlled = _mapping(operator_result.get("controlled_mutation_result"))
    if controlled.get("rollback_completed") is True:
        return "rolled_back"
    return "failed"


@dataclass
class RuntimeOperatorActivityLog:
    log_path: str | Path = "workspace/operator_activity/activity.jsonl"

    def append(
        self,
        *,
        goal: Any,
        result: Mapping[str, Any],
        task_id: Any = "",
        source: Any = "runtime",
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_goal = _text(goal)
        if not normalized_goal:
            return {
                "schema": RUNTIME_OPERATOR_ACTIVITY_LOG_SCHEMA,
                "ok": False,
                "activity_status": "denied",
                "denial_reason": "goal_required",
                "record": {},
                "log_path": str(self.log_path),
            }

        payload = _mapping(result)
        operator_result = _mapping(payload.get("operator_result"))
        record = {
            "schema": RUNTIME_OPERATOR_ACTIVITY_LOG_SCHEMA,
            "recorded_at": _utc_now(),
            "task_id": _text(task_id)
            or _text(payload.get("task_id"))
            or _text(operator_result.get("task_id")),
            "goal": normalized_goal,
            "source": _text(source) or "runtime",
            "status": _extract_status(payload),
            "ok": payload.get("ok") is True,
            "changed_files": _extract_changed_files(payload),
            "rollback_completed": _extract_rollback_completed(payload),
            "repair_attempted": _extract_repair_attempted(payload),
            "denial_reason": _text(payload.get("denial_reason"))
            or _text(operator_result.get("denial_reason")),
            "metadata": _mapping(metadata),
        }

        path = Path(self.log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str))
            handle.write("\n")

        return {
            "schema": RUNTIME_OPERATOR_ACTIVITY_LOG_SCHEMA,
            "ok": True,
            "activity_status": "recorded",
            "record": record,
            "log_path": str(path),
        }

    def read_all(self) -> dict[str, Any]:
        path = Path(self.log_path)
        if not path.exists():
            return {
                "schema": RUNTIME_OPERATOR_ACTIVITY_LOG_SCHEMA,
                "ok": True,
                "activity_status": "empty",
                "records": [],
                "record_count": 0,
                "log_path": str(path),
            }

        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                records.append(payload)

        return {
            "schema": RUNTIME_OPERATOR_ACTIVITY_LOG_SCHEMA,
            "ok": True,
            "activity_status": "loaded",
            "records": records,
            "record_count": len(records),
            "log_path": str(path),
        }


__all__ = [
    "RUNTIME_OPERATOR_ACTIVITY_LOG_SCHEMA",
    "RuntimeOperatorActivityLog",
]
