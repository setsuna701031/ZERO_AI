from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional


DEFAULT_EXECUTION_TRACE_PATH = Path("workspace") / "logs" / "execution_contract_trace.jsonl"


def build_execution_contract_trace_event(
    *,
    event: str,
    step: Optional[Mapping[str, Any]] = None,
    result: Optional[Mapping[str, Any]] = None,
    ok: Optional[bool] = None,
    source: str = "",
    reason: str = "",
    errors: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    safe_step = step if isinstance(step, Mapping) else {}
    safe_result = result if isinstance(result, Mapping) else {}

    resolved_errors = list(errors or _list_from_payload(safe_step, "contract_errors"))
    resolved_warnings = list(warnings or _list_from_payload(safe_step, "contract_warnings"))

    if ok is None:
        if "execution_runtime_entry_ok" in safe_step:
            resolved_ok = bool(safe_step.get("execution_runtime_entry_ok"))
        elif "execution_adapter_ok" in safe_step:
            resolved_ok = bool(safe_step.get("execution_adapter_ok"))
        elif "is_valid" in safe_step:
            resolved_ok = bool(safe_step.get("is_valid"))
        elif "ok" in safe_result:
            resolved_ok = bool(safe_result.get("ok"))
        else:
            resolved_ok = not resolved_errors
    else:
        resolved_ok = bool(ok)

    return {
        "ts": time.time(),
        "event": str(event or "execution_contract_event"),
        "ok": resolved_ok,
        "source": str(source or ""),
        "type": str(safe_step.get("type") or "noop"),
        "action": str(safe_result.get("action") or safe_step.get("type") or "noop"),
        "reason": str(reason or safe_step.get("reason") or safe_result.get("error") or ""),
        "description": str(safe_step.get("description") or ""),
        "path": safe_step.get("path"),
        "target_path": safe_step.get("target_path"),
        "command": str(safe_step.get("command") or ""),
        "contract_version": str(safe_step.get("contract_version") or ""),
        "is_valid": bool(safe_step.get("is_valid", resolved_ok)),
        "contract_errors": resolved_errors,
        "contract_warnings": resolved_warnings,
        "execution_adapter_ok": _optional_bool(safe_step.get("execution_adapter_ok")),
        "execution_runtime_entry_step_ok": _optional_bool(safe_step.get("execution_runtime_entry_step_ok")),
        "execution_runtime_entry_invoked": _optional_bool(safe_step.get("execution_runtime_entry_invoked")),
        "execution_runtime_entry_ok": _optional_bool(safe_step.get("execution_runtime_entry_ok")),
        "execution_runtime_entry_error": safe_step.get("execution_runtime_entry_error"),
        "result_ok": _optional_bool(safe_result.get("ok")),
        "result_error": str(safe_result.get("error") or ""),
        "metadata": _clean_metadata(metadata or safe_step.get("metadata")),
    }


def write_execution_contract_trace_event(
    event: Mapping[str, Any],
    *,
    trace_path: Optional[Any] = None,
) -> Optional[str]:
    if not isinstance(event, Mapping):
        return None

    path = Path(trace_path) if trace_path is not None else DEFAULT_EXECUTION_TRACE_PATH

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(_json_safe_dict(dict(event)), ensure_ascii=False, sort_keys=True) + "\n")
        return str(path)
    except Exception:
        return None


def trace_execution_contract_payload(
    *,
    event: str,
    step: Optional[Mapping[str, Any]] = None,
    result: Optional[Mapping[str, Any]] = None,
    ok: Optional[bool] = None,
    source: str = "",
    reason: str = "",
    errors: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
    trace_path: Optional[Any] = None,
) -> Dict[str, Any]:
    trace_event = build_execution_contract_trace_event(
        event=event,
        step=step,
        result=result,
        ok=ok,
        source=source,
        reason=reason,
        errors=errors,
        warnings=warnings,
        metadata=metadata,
    )
    written_path = write_execution_contract_trace_event(trace_event, trace_path=trace_path)
    trace_event["trace_path"] = written_path
    return trace_event


def load_execution_contract_trace(
    *,
    trace_path: Optional[Any] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    path = Path(trace_path) if trace_path is not None else DEFAULT_EXECUTION_TRACE_PATH
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


def summarize_execution_contract_trace(events: Any) -> Dict[str, Any]:
    if not isinstance(events, list):
        return {
            "ok": False,
            "event_count": 0,
            "invalid_count": 0,
            "rejected_count": 0,
            "invocation_failed_count": 0,
            "noop_count": 0,
            "error_count": 0,
            "warning_count": 0,
        }

    event_count = 0
    invalid_count = 0
    rejected_count = 0
    invocation_failed_count = 0
    noop_count = 0
    error_count = 0
    warning_count = 0

    for item in events:
        if not isinstance(item, Mapping):
            continue

        event_count += 1

        if not bool(item.get("ok", False)) or bool(item.get("is_valid")) is False:
            invalid_count += 1

        event_name = str(item.get("event") or "").strip().lower()
        action = str(item.get("action") or "").strip().lower()
        step_type = str(item.get("type") or "").strip().lower()

        if event_name == "execution_step_rejected" or action == "execution_step_rejected":
            rejected_count += 1

        if event_name == "execution_invocation_failed" or action == "execution_invocation_failed":
            invocation_failed_count += 1

        if step_type == "noop" or action == "noop":
            noop_count += 1

        errors = item.get("contract_errors")
        if isinstance(errors, list):
            error_count += len(errors)

        warnings = item.get("contract_warnings")
        if isinstance(warnings, list):
            warning_count += len(warnings)

        if str(item.get("result_error") or "").strip():
            error_count += 1

    return {
        "ok": True,
        "event_count": event_count,
        "invalid_count": invalid_count,
        "rejected_count": rejected_count,
        "invocation_failed_count": invocation_failed_count,
        "noop_count": noop_count,
        "error_count": error_count,
        "warning_count": warning_count,
    }


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