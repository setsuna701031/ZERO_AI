from __future__ import annotations

from typing import Any, Mapping


def should_fallback_to_simple_runner(
    runner_result: Mapping[str, Any] | None,
    loop_error_text: str,
) -> bool:
    if not isinstance(runner_result, Mapping):
        return True

    if loop_error_text:
        return True

    action_text = str(runner_result.get("action") or "").strip().lower()
    status_text = str(runner_result.get("status") or "").strip().lower()

    if action_text in {"failed", "exception_failed"} and loop_error_text:
        return True

    if status_text in {"failed", "error"} and loop_error_text:
        return True

    return False


def is_simple_runner_eligible_fallback(loop_error_text: str) -> bool:
    lower_error = str(loop_error_text or "").lower()
    sandbox_path_error = (
        "task_id required for sandbox-relative path" in lower_error
        or "path resolve failed" in lower_error
    )
    if sandbox_path_error:
        return True

    fallback_like_errors = [
        "unsupported step type",
        "step_executor",
        "path resolve failed",
        "sandbox-relative path",
    ]
    return any(token in lower_error for token in fallback_like_errors)


__all__ = [
    "is_simple_runner_eligible_fallback",
    "should_fallback_to_simple_runner",
]
