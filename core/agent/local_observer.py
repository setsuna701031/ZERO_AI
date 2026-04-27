from __future__ import annotations

from typing import Any, Dict, Optional


TERMINAL_STATUSES = {"finished", "failed", "blocked", "cancelled", "done", "completed", "success"}
RUNNING_STATUSES = {"running", "processing", "queued", "created", "pending", "retrying"}
FAILURE_ACTIONS = {"step_failed", "exception_failed", "guard_blocked", "command_failed"}
BLOCKED_ACTIONS = {"guard_blocked", "blocked", "policy_blocked"}
REPLAN_ERROR_TYPES = {
    "verify_target_not_found",
    "missing_output",
    "tool_result_invalid",
    "json_parse_error",
    "stderr_with_empty_output",
    "recoverable_tool_error",
}
FAIL_ERROR_TYPES = {
    "guard_blocked",
    "policy_blocked",
    "fatal",
    "internal_error",
    "max_cycles_reached",
}


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    try:
        return str(value)
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = _safe_str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "ok", "pass", "passed"}:
        return True
    if text in {"0", "false", "no", "n", "fail", "failed"}:
        return False
    return default


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        try:
            return int(value)
        except Exception:
            return default
    text = _safe_str(value).strip()
    if not text:
        return default
    try:
        return int(text)
    except Exception:
        return default


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_nonempty_str(*values: Any) -> str:
    for value in values:
        text = _safe_str(value).strip()
        if text:
            return text
    return ""


def _lower(value: Any) -> str:
    return _safe_str(value).strip().lower()


def _extract_nested_result(raw_result: Dict[str, Any]) -> Dict[str, Any]:
    candidates = [
        raw_result.get("result"),
        raw_result.get("last_result"),
        raw_result.get("last_step_result"),
        raw_result.get("step_result"),
    ]

    runtime_state = _as_dict(raw_result.get("runtime_state"))
    candidates.extend(
        [
            runtime_state.get("last_step_result"),
            runtime_state.get("last_result"),
            runtime_state.get("result"),
        ]
    )

    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate

    return {}


def _extract_returncode(raw_result: Dict[str, Any], nested_result: Dict[str, Any]) -> Optional[int]:
    for source in (raw_result, nested_result, _as_dict(nested_result.get("result"))):
        if not isinstance(source, dict):
            continue
        for key in ("returncode", "return_code", "exit_code", "code"):
            value = _safe_int(source.get(key), None)
            if value is not None:
                return value
    return None


def _extract_stdout(raw_result: Dict[str, Any], nested_result: Dict[str, Any]) -> str:
    for source in (raw_result, nested_result, _as_dict(nested_result.get("result"))):
        if not isinstance(source, dict):
            continue
        text = _first_nonempty_str(
            source.get("stdout"),
            source.get("output_text"),
            source.get("output"),
            source.get("text"),
        )
        if text:
            return text
    return ""


def _extract_stderr(raw_result: Dict[str, Any], nested_result: Dict[str, Any]) -> str:
    for source in (raw_result, nested_result, _as_dict(nested_result.get("result"))):
        if not isinstance(source, dict):
            continue
        text = _first_nonempty_str(
            source.get("stderr"),
            source.get("error_output"),
            source.get("err"),
        )
        if text:
            return text
    return ""


def _extract_error(raw_result: Dict[str, Any], nested_result: Dict[str, Any]) -> str:
    runtime_state = _as_dict(raw_result.get("runtime_state"))
    return _first_nonempty_str(
        raw_result.get("error"),
        raw_result.get("last_error"),
        nested_result.get("error"),
        runtime_state.get("last_error"),
        runtime_state.get("error"),
    )


def _extract_error_type(raw_result: Dict[str, Any], nested_result: Dict[str, Any], *, action: str, status: str, error: str, returncode: Optional[int]) -> str:
    runtime_state = _as_dict(raw_result.get("runtime_state"))

    explicit = _first_nonempty_str(
        raw_result.get("error_type"),
        nested_result.get("error_type"),
        runtime_state.get("error_type"),
    )
    if explicit:
        return explicit

    if action in BLOCKED_ACTIONS or status == "blocked":
        return "guard_blocked"

    lowered_error = error.lower()

    if "verify target not found" in lowered_error:
        return "verify_target_not_found"

    if "not json serializable" in lowered_error or "json" in lowered_error and "error" in lowered_error:
        return "json_parse_error"

    if returncode is not None and returncode != 0:
        return "command_failed"

    if status == "failed" or action in FAILURE_ACTIONS:
        return "recoverable_tool_error"

    return ""


def observe_result(raw_result: Any) -> Dict[str, Any]:
    """
    Convert runner/tool/step output into a small local observation.

    This module does not call planners, tools, schedulers, or AgentLoop.
    It only normalizes local execution evidence so upper layers can decide
    whether to continue, replan, fail, or stop.
    """
    if not isinstance(raw_result, dict):
        return {
            "ok": False,
            "status": "failed",
            "action": "invalid_result",
            "error": "result is not a dict",
            "error_type": "tool_result_invalid",
            "returncode": None,
            "stdout_present": False,
            "stderr_present": False,
            "terminal": True,
            "should_retry_candidate": False,
            "should_replan_candidate": True,
            "should_fail_candidate": False,
            "raw_type": type(raw_result).__name__,
        }

    nested_result = _extract_nested_result(raw_result)

    status = _lower(
        raw_result.get("status")
        or _as_dict(raw_result.get("runtime_state")).get("status")
        or nested_result.get("status")
        or ""
    )
    action = _lower(raw_result.get("action") or nested_result.get("action") or "")

    raw_ok = raw_result.get("ok")
    nested_ok = nested_result.get("ok")
    if raw_ok is None and nested_ok is not None:
        ok = _safe_bool(nested_ok, False)
    else:
        ok = _safe_bool(raw_ok, True)

    returncode = _extract_returncode(raw_result, nested_result)
    stdout = _extract_stdout(raw_result, nested_result)
    stderr = _extract_stderr(raw_result, nested_result)
    error = _extract_error(raw_result, nested_result)

    if returncode is not None and returncode != 0:
        ok = False

    if status in {"failed", "blocked"}:
        ok = False

    error_type = _extract_error_type(
        raw_result,
        nested_result,
        action=action,
        status=status,
        error=error,
        returncode=returncode,
    )

    stdout_present = bool(stdout.strip())
    stderr_present = bool(stderr.strip())

    terminal = status in TERMINAL_STATUSES or action in {"already_finished", "finished", "complete", "completed"}

    should_fail_candidate = (
        status == "blocked"
        or action in BLOCKED_ACTIONS
        or error_type in FAIL_ERROR_TYPES
    )

    should_replan_candidate = (
        not should_fail_candidate
        and (
            error_type in REPLAN_ERROR_TYPES
            or (status == "failed" and bool(error))
            or (returncode is not None and returncode != 0)
        )
    )

    should_retry_candidate = (
        not should_fail_candidate
        and not should_replan_candidate
        and status in {"retrying"}
    )

    if not status:
        if ok:
            status = "finished" if terminal else "running"
        else:
            status = "failed"

    return {
        "ok": ok,
        "status": status,
        "action": action,
        "error": error or None,
        "error_type": error_type or None,
        "returncode": returncode,
        "stdout_present": stdout_present,
        "stderr_present": stderr_present,
        "terminal": terminal,
        "should_retry_candidate": should_retry_candidate,
        "should_replan_candidate": should_replan_candidate,
        "should_fail_candidate": should_fail_candidate,
    }


def observe_step_result(step_result: Any) -> Dict[str, Any]:
    return observe_result(step_result)


def observe_tool_result(tool_result: Any) -> Dict[str, Any]:
    return observe_result(tool_result)


def observe_runner_result(runner_result: Any) -> Dict[str, Any]:
    return observe_result(runner_result)


def main() -> int:
    samples = {
        "success": {"ok": True, "status": "finished", "action": "already_finished"},
        "running": {"ok": True, "status": "running", "action": "step_completed"},
        "verify_missing": {
            "ok": False,
            "status": "failed",
            "action": "step_failed",
            "error": "verify target not found: workspace/shared/output.txt",
        },
        "blocked": {"ok": False, "status": "blocked", "action": "guard_blocked", "error": "blocked by guard"},
    }

    for name, payload in samples.items():
        obs = observe_result(payload)
        print(f"[local-observer] {name}: status={obs['status']} error_type={obs['error_type']} replan={obs['should_replan_candidate']} fail={obs['should_fail_candidate']}")

    print("[local-observer] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
