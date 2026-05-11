from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


DEFAULT_PLANNER_TRACE_PATH = Path("workspace") / "logs" / "planner_contract_trace.jsonl"


@dataclass(frozen=True)
class PlannerContractTraceEvent:
    event: str
    ok: bool
    action: str = "noop"
    source: str = ""
    reason: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


def build_planner_contract_trace_event(
    *,
    event: str,
    payload: Optional[Mapping[str, Any]] = None,
    ok: Optional[bool] = None,
    source: str = "",
    reason: str = "",
    errors: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    safe_payload = payload if isinstance(payload, Mapping) else {}

    resolved_errors = list(errors or _list_from_payload(safe_payload, "contract_errors"))
    resolved_warnings = list(warnings or _list_from_payload(safe_payload, "contract_warnings"))

    if ok is None:
        if "planner_gateway_ok" in safe_payload:
            resolved_ok = bool(safe_payload.get("planner_gateway_ok"))
        elif "runtime_entry_ok" in safe_payload:
            resolved_ok = bool(safe_payload.get("runtime_entry_ok"))
        elif "adapter_ok" in safe_payload:
            resolved_ok = bool(safe_payload.get("adapter_ok"))
        elif "is_valid" in safe_payload:
            resolved_ok = bool(safe_payload.get("is_valid"))
        else:
            resolved_ok = not resolved_errors
    else:
        resolved_ok = bool(ok)

    event_payload = {
        "ts": time.time(),
        "event": str(event or "planner_contract_event"),
        "ok": resolved_ok,
        "source": str(source or ""),
        "action": str(safe_payload.get("action") or "noop"),
        "raw_action": str(safe_payload.get("raw_action") or ""),
        "reason": str(reason or safe_payload.get("reason") or ""),
        "goal": str(safe_payload.get("goal") or ""),
        "target_path": safe_payload.get("target_path"),
        "contract_version": str(safe_payload.get("contract_version") or ""),
        "is_valid": bool(safe_payload.get("is_valid", resolved_ok)),
        "contract_errors": resolved_errors,
        "contract_warnings": resolved_warnings,
        "adapter_ok": _optional_bool(safe_payload.get("adapter_ok")),
        "runtime_entry_ok": _optional_bool(safe_payload.get("runtime_entry_ok")),
        "runtime_entry_invoked": _optional_bool(safe_payload.get("runtime_entry_invoked")),
        "planner_gateway_ok": _optional_bool(safe_payload.get("planner_gateway_ok")),
        "scheduler_planner_gateway_used": _optional_bool(safe_payload.get("scheduler_planner_gateway_used")),
        "scheduler_planner_legacy_fallback_used": _optional_bool(
            safe_payload.get("scheduler_planner_legacy_fallback_used")
        ),
        "scheduler_planner_runtime_ok": _optional_bool(safe_payload.get("scheduler_planner_runtime_ok")),
        "metadata": _clean_metadata(metadata or safe_payload.get("metadata")),
    }

    return event_payload


def write_planner_contract_trace_event(
    event: Mapping[str, Any],
    *,
    trace_path: Optional[Any] = None,
) -> Optional[str]:
    if not isinstance(event, Mapping):
        return None

    path = Path(trace_path) if trace_path is not None else DEFAULT_PLANNER_TRACE_PATH

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(_json_safe_dict(dict(event)), ensure_ascii=False, sort_keys=True) + "\n")
        return str(path)
    except Exception:
        return None


def trace_planner_contract_payload(
    *,
    event: str,
    payload: Optional[Mapping[str, Any]] = None,
    ok: Optional[bool] = None,
    source: str = "",
    reason: str = "",
    errors: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
    trace_path: Optional[Any] = None,
) -> Dict[str, Any]:
    trace_event = build_planner_contract_trace_event(
        event=event,
        payload=payload,
        ok=ok,
        source=source,
        reason=reason,
        errors=errors,
        warnings=warnings,
        metadata=metadata,
    )
    written_path = write_planner_contract_trace_event(trace_event, trace_path=trace_path)
    trace_event["trace_path"] = written_path
    return trace_event


def summarize_planner_contract_trace(
    events: Any,
) -> Dict[str, Any]:
    if not isinstance(events, list):
        return {
            "ok": False,
            "event_count": 0,
            "invalid_count": 0,
            "fallback_count": 0,
            "noop_count": 0,
            "error_count": 0,
            "warning_count": 0,
        }

    invalid_count = 0
    fallback_count = 0
    noop_count = 0
    error_count = 0
    warning_count = 0

    for item in events:
        if not isinstance(item, Mapping):
            continue

        if not bool(item.get("ok", False)) or bool(item.get("is_valid")) is False:
            invalid_count += 1

        if bool(item.get("scheduler_planner_legacy_fallback_used", False)):
            fallback_count += 1

        if str(item.get("action") or "").strip().lower() == "noop":
            noop_count += 1

        errors = item.get("contract_errors")
        if isinstance(errors, list):
            error_count += len(errors)

        warnings = item.get("contract_warnings")
        if isinstance(warnings, list):
            warning_count += len(warnings)

    return {
        "ok": True,
        "event_count": len([item for item in events if isinstance(item, Mapping)]),
        "invalid_count": invalid_count,
        "fallback_count": fallback_count,
        "noop_count": noop_count,
        "error_count": error_count,
        "warning_count": warning_count,
    }


def load_planner_contract_trace(
    *,
    trace_path: Optional[Any] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    path = Path(trace_path) if trace_path is not None else DEFAULT_PLANNER_TRACE_PATH
    if not path.exists():
        return []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []

    selected = lines[-max(1, int(limit)):]
    events: List[Dict[str, Any]] = []

    for line in selected:
        text = str(line or "").strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except Exception:
            continue
        if isinstance(item, dict):
            events.append(item)

    return events


def _list_from_payload(payload: Mapping[str, Any], key: str) -> List[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _optional_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    return bool(value)


def _clean_metadata(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}

    cleaned: Dict[str, Any] = {}
    for key, item in value.items():
        clean_key = str(key or "").strip()
        if not clean_key:
            continue

        if isinstance(item, (str, int, float, bool)) or item is None:
            cleaned[clean_key] = item
        elif isinstance(item, list):
            cleaned[clean_key] = [
                entry for entry in item if isinstance(entry, (str, int, float, bool)) or entry is None
            ]
        elif isinstance(item, Mapping):
            nested: Dict[str, Any] = {}
            for nested_key, nested_value in item.items():
                clean_nested_key = str(nested_key or "").strip()
                if not clean_nested_key:
                    continue
                if isinstance(nested_value, (str, int, float, bool)) or nested_value is None:
                    nested[clean_nested_key] = nested_value
            cleaned[clean_key] = nested

    return cleaned


def _json_safe_dict(value: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, (str, int, float, bool)) or item is None:
            safe[str(key)] = item
        elif isinstance(item, list):
            safe[str(key)] = [
                entry if isinstance(entry, (str, int, float, bool)) or entry is None else str(entry)
                for entry in item
            ]
        elif isinstance(item, dict):
            safe[str(key)] = _json_safe_dict(item)
        else:
            safe[str(key)] = str(item)
    return safe