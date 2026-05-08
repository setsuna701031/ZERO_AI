from __future__ import annotations

import copy
from typing import Any, Dict


def should_rollback_after_failed_verify(
    *,
    step: Any,
    step_result: Any,
    state: Any,
) -> bool:
    """
    Decide whether a failed verify step should trigger repair rollback.

    This helper is intentionally pure:
    - It does not mutate runtime state.
    - It does not restore files.
    - It does not decide terminal status.
    - It only answers whether rollback should be attempted.
    """

    if not isinstance(step, dict) or not isinstance(step_result, dict) or not isinstance(state, dict):
        return False

    if bool(step_result.get("ok", False)):
        return False

    step_type = str(step.get("type") or "").strip().lower()
    if step_type not in {"verify", "verify_file", "code_chain_verify"}:
        return False

    repair_context = state.get("repair_context")
    if not isinstance(repair_context, dict):
        return False

    rollback_result = repair_context.get("rollback_result")
    if isinstance(rollback_result, dict) and rollback_result.get("ok") is True:
        return False

    rollback = repair_context.get("rollback")
    return isinstance(rollback, dict) and bool(rollback.get("restore_available"))


def restore_repair_backup(
    *,
    runtime: Any,
    task: Dict[str, Any],
    current_tick: int = 0,
    verify_error: Any = "",
) -> Dict[str, Any]:
    """
    Restore the last repair backup through TaskRuntime.

    TaskRunner remains the orchestrator. This helper only normalizes the
    rollback invocation/result boundary so the restore operation no longer
    lives directly inside TaskRunner.

    Expected runtime contract:
        runtime.rollback_last_apply(task=..., current_tick=..., verify_error=...)

    Returned payload is always a dict and always contains a rollback_result
    payload, even when the runtime method is missing or returns malformed data.
    """

    if not isinstance(task, dict):
        task = {}

    rollback_fn = getattr(runtime, "rollback_last_apply", None)
    if not callable(rollback_fn):
        return {
            "ok": False,
            "status": "failed",
            "runtime_state": {},
            "rollback_result": {
                "ok": False,
                "reason": "runtime rollback_last_apply is not available",
                "restore_source": "",
                "restored_files": [],
                "failed_files": [],
            },
        }

    try:
        result = rollback_fn(
            task=task,
            current_tick=current_tick,
            verify_error=verify_error,
        )
    except Exception as exc:
        return {
            "ok": False,
            "status": "failed",
            "runtime_state": {},
            "rollback_result": {
                "ok": False,
                "reason": f"rollback exception: {exc}",
                "restore_source": "",
                "restored_files": [],
                "failed_files": [],
            },
        }

    if not isinstance(result, dict):
        return {
            "ok": False,
            "status": "failed",
            "runtime_state": {},
            "rollback_result": {
                "ok": False,
                "reason": "runtime rollback returned invalid result",
                "restore_source": "",
                "restored_files": [],
                "failed_files": [],
                "raw_result": str(result),
            },
        }

    normalized = copy.deepcopy(result)
    rollback_result = normalized.get("rollback_result")
    if not isinstance(rollback_result, dict):
        rollback_result = {
            "ok": bool(normalized.get("ok", False)),
            "reason": str(normalized.get("reason") or normalized.get("error") or ""),
            "restore_source": "",
            "restored_files": [],
            "failed_files": [],
        }
        normalized["rollback_result"] = rollback_result

    return normalized


def compact_rollback_result(value: Any) -> Dict[str, Any]:
    """
    Build a compact rollback payload for trace/audit tests.

    This is intentionally lossy and should not be used as persistence source.
    """

    if not isinstance(value, dict):
        return {}

    payload = value.get("rollback_result") if isinstance(value.get("rollback_result"), dict) else value

    return {
        "ok": bool(payload.get("ok", False)),
        "reason": str(payload.get("reason") or payload.get("error") or ""),
        "restore_source": str(payload.get("restore_source") or ""),
        "restored_files": list(payload.get("restored_files") or []) if isinstance(payload.get("restored_files"), list) else [],
        "failed_files": list(payload.get("failed_files") or []) if isinstance(payload.get("failed_files"), list) else [],
    }
