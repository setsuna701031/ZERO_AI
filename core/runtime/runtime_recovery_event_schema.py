from __future__ import annotations

import copy
import json
from typing import Any


RUNTIME_RECOVERY_EVENT_SCHEMA = "zero.runtime.recovery_event.v1"
RUNTIME_RECOVERY_OPERATOR_SUMMARY_EVENT = "runtime.recovery.operator_summary"


def build_runtime_recovery_event(
    *,
    event_type: str = RUNTIME_RECOVERY_OPERATOR_SUMMARY_EVENT,
    event_id: str = "",
    task_id: str = "",
    recovery_id: str = "",
    readiness: str = "",
    status: str = "",
    summary: str = "",
    blockers: Any = None,
    operator_summary: Any = None,
    source: Any = None,
) -> dict[str, Any]:
    payload = _payload(source)
    operator = _safe_mapping(operator_summary) or _safe_mapping(payload.get("operator_summary"))

    event = {
        "ok": bool(operator.get("ok", status == "ready")),
        "schema": RUNTIME_RECOVERY_EVENT_SCHEMA,
        "event_type": _safe_text(event_type),
        "event_id": _safe_text(event_id),
        "task_id": _safe_text(task_id),
        "recovery_id": _safe_text(recovery_id),
        "read_only": True,
        "executes_recovery": False,
        "executes_rollback": False,
        "executes_repair": False,
        "invokes_scheduler": False,
        "adds_persistence": False,
        "uses_network": False,
        "readiness": _safe_text(readiness or operator.get("readiness") or payload.get("readiness")),
        "status": _safe_text(status or operator.get("status") or payload.get("status")),
        "summary": _safe_text(summary or operator.get("summary") or payload.get("summary")),
        "blockers": _safe_list(blockers if blockers is not None else operator.get("blockers") or payload.get("blockers")),
        "operator_summary": operator,
    }
    return _json_safe(event)


def _payload(source: Any) -> dict[str, Any]:
    if isinstance(source, dict):
        return copy.deepcopy(source)

    payload = getattr(source, "payload", None)
    if isinstance(payload, dict):
        return copy.deepcopy(payload)

    return {}


def _safe_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip() if value is not None else ""
    return [text] if text else []


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _json_safe(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {}
    encoded = json.dumps(
        payload,
        default=str,
        sort_keys=True,
        separators=(",", ":"),
    )
    return json.loads(encoded)


__all__ = [
    "RUNTIME_RECOVERY_EVENT_SCHEMA",
    "RUNTIME_RECOVERY_OPERATOR_SUMMARY_EVENT",
    "build_runtime_recovery_event",
]
