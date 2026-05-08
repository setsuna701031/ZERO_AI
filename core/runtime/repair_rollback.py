from __future__ import annotations

import copy
from typing import Any, Dict

try:
    from core.runtime.runtime_mode import READONLY_RUNTIME_MODES, RuntimeMode
    from core.runtime.runtime_transition_policy import RuntimeTransitionPolicy
except Exception:  # pragma: no cover - compatibility fallback
    class RuntimeMode(str):
        EXECUTE = "execute"
        REPLAY = "replay"
        AUDIT = "audit"
        REPAIR_REPLAY = "repair_replay"

    READONLY_RUNTIME_MODES = {"replay", "audit", "repair_replay"}


def should_rollback_after_failed_verify(
    *,
    step: Any,
    step_result: Any,
    state: Any,
) -> bool:
    if not isinstance(step, dict):
        return False

    if not isinstance(step_result, dict):
        return False

    if not isinstance(state, dict):
        return False

    runtime_mode = _runtime_mode_from_payload(step, step_result, state)

    if _is_readonly_runtime_mode(runtime_mode):
        return False

    if bool(step_result.get("ok", False)):
        return False

    step_type = str(step.get("type") or "").strip().lower()

    if step_type not in {
        "verify",
        "verify_file",
        "code_chain_verify",
    }:
        return False

    repair_context = state.get("repair_context")

    if not isinstance(repair_context, dict):
        return False

    rollback_result = repair_context.get("rollback_result")

    if isinstance(rollback_result, dict):
        if rollback_result.get("ok") is True:
            return False

    rollback = repair_context.get("rollback")

    return (
        isinstance(rollback, dict)
        and bool(rollback.get("restore_available"))
    )


def restore_repair_backup(
    *,
    runtime: Any,
    task: Dict[str, Any],
    current_tick: int = 0,
    verify_error: Any = "",
) -> Dict[str, Any]:
    if not isinstance(task, dict):
        task = {}

    runtime_mode = _runtime_mode_from_payload(task)

    if _is_readonly_runtime_mode(runtime_mode):
        return {
            "ok": False,
            "status": "blocked",
            "runtime_state": {},
            "runtime_mode": runtime_mode,
            "rollback_result": {
                "ok": False,
                "reason": f"{runtime_mode} runtime cannot restore repair backup",
                "restore_source": "",
                "restored_files": [],
                "failed_files": [],
                "guard_mode": "readonly_runtime_rollback_blocked",
            },
        }

    try:
        preview_state: Dict[str, Any] = {}
        has_preview_state = False

        load_fn = getattr(runtime, "load_runtime_state", None)

        if callable(load_fn):
            loaded = load_fn(task)

            if isinstance(loaded, dict):
                preview_state = loaded
                has_preview_state = True

        if has_preview_state:
            recovery_decision = RuntimeTransitionPolicy().check_recovery_transition(
                current_state=preview_state,
                updates={"recovery_action": "rollback_restore"},
                owner="task_runtime",
                action="rollback_restore",
            )

            if not recovery_decision.ok:
                return {
                    "ok": False,
                    "status": "blocked",
                    "runtime_state": preview_state,
                    "runtime_mode": runtime_mode,
                    "rollback_result": {
                        "ok": False,
                        "reason": recovery_decision.reason,
                        "restore_source": "",
                        "restored_files": [],
                        "failed_files": [],
                        "guard_mode": "rollback_recovery_policy_blocked",
                        "policy_decision": recovery_decision.to_dict(),
                    },
                }

    except Exception:
        pass

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
            "reason": str(
                normalized.get("reason")
                or normalized.get("error")
                or ""
            ),
            "restore_source": "",
            "restored_files": [],
            "failed_files": [],
        }

        normalized["rollback_result"] = rollback_result

    return normalized


def compact_rollback_result(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    payload = (
        value.get("rollback_result")
        if isinstance(value.get("rollback_result"), dict)
        else value
    )

    return {
        "ok": bool(payload.get("ok", False)),
        "reason": str(payload.get("reason") or payload.get("error") or ""),
        "restore_source": str(payload.get("restore_source") or ""),
        "restored_files": (
            list(payload.get("restored_files") or [])
            if isinstance(payload.get("restored_files"), list)
            else []
        ),
        "failed_files": (
            list(payload.get("failed_files") or [])
            if isinstance(payload.get("failed_files"), list)
            else []
        ),
    }


def _runtime_mode_from_payload(*payloads: Any) -> str:
    for payload in payloads:
        if not isinstance(payload, dict):
            continue

        value = str(payload.get("runtime_mode") or "").strip().lower()

        if value:
            return value

        runtime_context = payload.get("runtime_context")

        if isinstance(runtime_context, dict):
            value = str(runtime_context.get("runtime_mode") or "").strip().lower()

            if value:
                return value

        repair_context = payload.get("repair_context")

        if isinstance(repair_context, dict):
            value = str(repair_context.get("runtime_mode") or "").strip().lower()

            if value:
                return value

    return str(
        getattr(RuntimeMode, "EXECUTE", "execute")
    ).strip().lower()


def _is_readonly_runtime_mode(mode: Any) -> bool:
    text = str(mode or "").strip().lower()

    readonly_values = {
        str(item.value if hasattr(item, "value") else item)
        .strip()
        .lower()
        for item in READONLY_RUNTIME_MODES
    }

    return text in readonly_values