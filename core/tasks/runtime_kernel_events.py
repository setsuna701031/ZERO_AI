from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from core.tasks.runtime_state_hygiene import freeze_runtime_export


KERNEL_EVENT_SOURCES = {"planner", "execution", "blocker", "repair", "runtime", "unknown"}

KERNEL_ACTION_TYPES = {
    "unknown",
    "run_python",
    "run_command",
    "write_file",
    "read_file",
    "verify",
    "repair_attempt",
    "planner_retry",
    "plan",
    "blocker",
    "runtime_step",
}


def normalize_runtime_kernel_event(event: Any, *, source: Optional[str] = None) -> Dict[str, Any]:
    raw = freeze_runtime_export(event)
    is_malformed = not isinstance(event, Mapping)
    payload = event if isinstance(event, Mapping) else {}
    resolved_source = _normalize_source(source) or _infer_source(payload)
    event_type = _event_type(payload)
    action_type = _classify_action(payload, resolved_source)
    status = _event_status(payload, resolved_source)

    return {
        "source": resolved_source,
        "event_type": event_type,
        "action_type": action_type,
        "status": status,
        "summary": "malformed event" if is_malformed else _event_summary(payload, resolved_source, event_type, action_type),
        "timestamp": _event_timestamp(payload),
        "raw": raw,
    }


def normalize_runtime_kernel_events(trace: Any, *, source: Optional[str] = None) -> List[Dict[str, Any]]:
    if trace is None:
        return []
    if isinstance(trace, list):
        return [normalize_runtime_kernel_event(item, source=source) for item in trace]
    if isinstance(trace, Mapping):
        return [normalize_runtime_kernel_event(trace, source=source)]
    return [normalize_runtime_kernel_event(trace, source=source)]


def summarize_normalized_kernel_events(events: Any) -> Dict[str, Any]:
    normalized = normalize_runtime_kernel_events(events)
    by_source = {source: 0 for source in sorted(KERNEL_EVENT_SOURCES)}
    by_status: Dict[str, int] = {}
    by_action = {action: 0 for action in sorted(KERNEL_ACTION_TYPES)}
    latest_event: Dict[str, Any] = {}

    for event in normalized:
        source = str(event.get("source") or "unknown")
        status = str(event.get("status") or "unknown")
        action_type = str(event.get("action_type") or "unknown")
        by_source[source] = by_source.get(source, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        by_action[action_type] = by_action.get(action_type, 0) + 1
        latest_event = event

    return {
        "ok": True,
        "event_count": len(normalized),
        "by_source": by_source,
        "by_status": by_status,
        "by_action": by_action,
        "latest_event": latest_event,
    }


def _normalize_source(source: Optional[str]) -> str:
    text = str(source or "").strip().lower()
    if text in KERNEL_EVENT_SOURCES:
        return text
    return ""


def _infer_source(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping):
        return "unknown"

    explicit = _normalize_source(str(payload.get("source") or ""))
    if explicit:
        return explicit

    lowered_event = " ".join(
        str(payload.get(key) or "").lower()
        for key in ("event", "event_type", "action", "type", "reason", "blocked_reason", "tool", "command")
    )
    keys = {str(key).lower() for key in payload.keys()}

    if "blocked_reason" in keys or "blocker" in lowered_event or "blocked" in lowered_event:
        return "blocker"
    if "repair" in lowered_event or any(key.startswith("repair") for key in keys):
        return "repair"
    if "current_step_index" in keys or "runtime_state" in keys or "runtime" in lowered_event:
        return "runtime"
    if "planner_gateway_ok" in keys or "raw_action" in keys or "intent" in keys or "plan" in keys:
        return "planner"
    if "execution_runtime_entry_ok" in keys or "result_ok" in keys or "result_error" in keys:
        return "execution"
    if "step" in keys or "result" in keys or "command" in keys or "tool" in keys:
        return "execution"
    return "unknown"


def _event_type(payload: Mapping[str, Any]) -> str:
    # Keep the public event_type contract stable. Classification is exposed through
    # action_type so timeline/replay tests and downstream consumers do not break.
    return _first_nonempty(
        payload.get("event"),
        payload.get("event_type"),
        payload.get("action"),
        payload.get("type"),
        "unknown_event",
    )


def _classify_action(payload: Mapping[str, Any], source: str) -> str:
    if source == "blocker":
        return "blocker"
    if source == "planner":
        return _classify_planner_action(payload)
    if source == "repair":
        return _classify_repair_action(payload)
    if source == "runtime":
        return _classify_runtime_action(payload)
    if source == "execution":
        return _classify_execution_action(payload)
    return "unknown"


def _classify_execution_action(payload: Mapping[str, Any]) -> str:
    text = _action_text(payload)

    command = _first_nonempty(payload.get("command"), _deep_find_string(payload, "command"))
    lowered_command = command.lower()
    if command:
        if "python" in lowered_command or lowered_command.endswith(".py"):
            return "run_python"
        if "pytest" in lowered_command:
            return "verify"
        return "run_command"

    if _contains_any(text, ("write_file", "write file", "create_file", "save_file", "patch", "apply_patch")):
        return "write_file"
    if _contains_any(text, ("read_file", "read file", "load_file")):
        return "read_file"
    if _contains_any(text, ("verify", "check", "pytest", "test")):
        return "verify"
    if _contains_any(text, ("run_python", "python", ".py")):
        return "run_python"
    if _contains_any(text, ("run_command", "command", "shell", "powershell", "cmd", "bash")):
        return "run_command"

    return "unknown"


def _classify_planner_action(payload: Mapping[str, Any]) -> str:
    text = _action_text(payload)
    if _contains_any(text, ("retry", "replan", "planner_retry")):
        return "planner_retry"
    if _contains_any(text, ("verify", "check", "test")):
        return "verify"
    if _contains_any(text, ("repair", "fix")):
        return "repair_attempt"
    return "plan"


def _classify_repair_action(payload: Mapping[str, Any]) -> str:
    text = _action_text(payload)
    if _contains_any(text, ("verify", "check", "test")):
        return "verify"
    if _contains_any(text, ("write", "patch", "apply", "edit")):
        return "write_file"
    return "repair_attempt"


def _classify_runtime_action(payload: Mapping[str, Any]) -> str:
    text = _action_text(payload)
    if _contains_any(text, ("run_python", "python")):
        return "run_python"
    if _contains_any(text, ("run_command", "command", "shell")):
        return "run_command"
    if _contains_any(text, ("verify", "check", "test")):
        return "verify"
    return "runtime_step"


def _action_text(payload: Mapping[str, Any]) -> str:
    parts: List[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text:
            parts.append(text)

    for key in (
        "event",
        "event_type",
        "action",
        "type",
        "tool",
        "command",
        "intent",
        "raw_action",
        "repair_action",
        "reason",
        "summary",
        "message",
    ):
        add(payload.get(key))

    step = payload.get("step")
    if isinstance(step, Mapping):
        for key in ("event", "event_type", "action", "type", "tool", "command", "description", "title", "name"):
            add(step.get(key))
    elif isinstance(step, str):
        add(step)

    result = payload.get("result")
    if isinstance(result, Mapping):
        for key in ("event", "event_type", "action", "type", "tool", "command", "status", "message", "error"):
            add(result.get(key))
    elif isinstance(result, str):
        add(result)

    return " ".join(parts).lower()


def _event_status(payload: Mapping[str, Any], source: str) -> str:
    status = _first_nonempty(payload.get("status"))
    if status:
        return status

    result = payload.get("result")
    if isinstance(result, Mapping):
        nested_status = _first_nonempty(result.get("status"))
        if nested_status:
            return nested_status
        if "ok" in result:
            return "ok" if bool(result.get("ok")) else "error"

    if "ok" in payload:
        return "ok" if bool(payload.get("ok")) else "error"
    if "is_valid" in payload:
        return "ok" if bool(payload.get("is_valid")) else "invalid"
    if "result_ok" in payload and payload.get("result_ok") is not None:
        return "ok" if bool(payload.get("result_ok")) else "error"
    if _first_nonempty(payload.get("error"), payload.get("result_error")):
        return "error"
    if source == "blocker":
        return "blocked"
    return "unknown"


def _event_timestamp(payload: Mapping[str, Any]) -> Any:
    return payload.get("timestamp", payload.get("ts", payload.get("time", payload.get("created_at", ""))))


def _event_summary(payload: Mapping[str, Any], source: str, event_type: str, action_type: str) -> str:
    if not isinstance(payload, Mapping):
        return "malformed event"
    if source == "blocker":
        reason = _first_nonempty(payload.get("reason"), payload.get("blocked_reason"), payload.get("message"), payload.get("error"))
        return f"blocker: {reason or event_type}"
    if source == "execution":
        action = _first_nonempty(payload.get("action"), payload.get("type"), payload.get("tool"), action_type if action_type != "unknown" else "", event_type)
        result = payload.get("result")
        result_text = ""
        if isinstance(result, Mapping):
            result_text = _first_nonempty(result.get("status"), result.get("action"), result.get("message"))
            error = _first_nonempty(result.get("error"))
        else:
            error = ""
        error = error or _first_nonempty(payload.get("result_error"), payload.get("error"), payload.get("reason"))
        if error:
            return f"execution action: {action}; error: {error}"
        if result_text:
            return f"execution action: {action}; result: {result_text}"
        return f"execution action: {action}"
    if source == "planner":
        intent = _first_nonempty(payload.get("intent"), payload.get("action"), payload.get("raw_action"))
        plan = _extract_plan_text(payload.get("plan"))
        step = _extract_step_text(payload.get("step"))
        detail = _first_nonempty(plan, step, intent, event_type)
        return f"planner: {detail}"
    if source == "repair":
        detail = _first_nonempty(payload.get("repair_action"), payload.get("action"), payload.get("reason"), payload.get("error"), event_type)
        return f"repair: {detail}"
    if source == "runtime":
        detail = _first_nonempty(_extract_step_text(payload.get("step")), payload.get("current_step"), payload.get("status"), event_type)
        return f"runtime: {detail}"
    return _first_nonempty(payload.get("summary"), payload.get("message"), payload.get("reason"), event_type)


def _extract_plan_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return _first_nonempty(value.get("title"), value.get("goal"), value.get("intent"), value.get("action"), value.get("summary"))
    if isinstance(value, list) and value:
        return _extract_step_text(value[0])
    return ""


def _extract_step_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        nested = _extract_step_text(value.get("step"))
        if nested:
            return nested
        return _first_nonempty(value.get("title"), value.get("name"), value.get("description"), value.get("action"), value.get("type"))
    return ""


def _deep_find_string(data: Any, key: str, depth: int = 0) -> str:
    if depth > 6:
        return ""

    if isinstance(data, Mapping):
        value = data.get(key)
        if value not in (None, "", [], {}):
            if isinstance(value, (str, int, float, bool)):
                return str(value)
        for nested in data.values():
            found = _deep_find_string(nested, key, depth + 1)
            if found:
                return found

    if isinstance(data, list):
        for item in data:
            found = _deep_find_string(item, key, depth + 1)
            if found:
                return found

    return ""


def _contains_any(text: str, needles: Any) -> bool:
    return any(str(needle).lower() in text for needle in needles)


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
