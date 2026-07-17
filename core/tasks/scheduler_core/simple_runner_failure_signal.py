from __future__ import annotations

from typing import Any, Dict


def _extract_simple_step_failure_signal(payload: Any, *, max_depth: int = 5) -> Dict[str, Any]:
    """Return a compact failure/block signal from a step result payload.

    Scheduler simple-runner must not treat a blocked or failed executor result as
    success.  StepExecutor/gateway payloads can be nested, so this helper checks
    both top-level and common nested result/error containers without copying large
    evidence payloads.
    """
    if max_depth <= 0:
        return {"failed": False, "blocked": False, "message": "", "error_type": ""}

    if not isinstance(payload, dict):
        return {"failed": False, "blocked": False, "message": "", "error_type": ""}

    error_payload = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    error_type = str(
        payload.get("error_type")
        or payload.get("failure_type")
        or error_payload.get("type")
        or ""
    ).strip()
    message = str(
        payload.get("message")
        or payload.get("final_answer")
        or payload.get("last_error")
        or payload.get("failure_message")
        or error_payload.get("message")
        or payload.get("error")
        or ""
    ).strip()

    status = str(payload.get("status") or "").strip().lower()
    action = str(payload.get("action") or "").strip().lower()

    blocked = bool(payload.get("blocked")) or status in {
        "blocked",
        "review_required",
        "waiting",
        "waiting_review",
        "waiting_blocker",
    }
    failed = (
        payload.get("ok") is False
        or bool(payload.get("failed"))
        or status in {"failed", "error", "cancelled", "canceled"}
        or action in {"step_failed", "simple_step_failed", "execution_failed"}
    )

    if error_type in {
        "execution_authority_denied",
        "authority_denied",
        "permission_denied",
        "unsafe_action_blocked",
        "repo_scope_confirmation_required",
    }:
        blocked = True
        failed = True

    if blocked or failed:
        return {
            "failed": bool(failed),
            "blocked": bool(blocked),
            "message": message or error_type or status or action or "step execution blocked",
            "error_type": error_type,
        }

    for key in ("runtime_execution_result", "result", "adapter_payload", "raw"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            signal = _extract_simple_step_failure_signal(nested, max_depth=max_depth - 1)
            if signal.get("failed") or signal.get("blocked"):
                return signal

    return {"failed": False, "blocked": False, "message": "", "error_type": ""}


