from __future__ import annotations

import copy
from enum import StrEnum
from typing import Any


class RuntimeStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    EXECUTED = "executed"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    BLOCKED = "blocked"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    RECOVERING = "recovering"
    RECOVERED = "recovered"
    REPLAYING = "replaying"
    REPLAYED = "replayed"
    COMMITTED = "committed"
    SEALED = "sealed"
    UNKNOWN = "unknown"


PENDING = RuntimeStatus.PENDING.value
QUEUED = RuntimeStatus.QUEUED.value
RUNNING = RuntimeStatus.RUNNING.value
EXECUTED = RuntimeStatus.EXECUTED.value
VERIFYING = RuntimeStatus.VERIFYING.value
VERIFIED = RuntimeStatus.VERIFIED.value
BLOCKED = RuntimeStatus.BLOCKED.value
FAILED = RuntimeStatus.FAILED.value
ROLLING_BACK = RuntimeStatus.ROLLING_BACK.value
ROLLED_BACK = RuntimeStatus.ROLLED_BACK.value
RECOVERING = RuntimeStatus.RECOVERING.value
RECOVERED = RuntimeStatus.RECOVERED.value
REPLAYING = RuntimeStatus.REPLAYING.value
REPLAYED = RuntimeStatus.REPLAYED.value
COMMITTED = RuntimeStatus.COMMITTED.value
SEALED = RuntimeStatus.SEALED.value
UNKNOWN = RuntimeStatus.UNKNOWN.value


_STATUS_ALIASES = {
    "": UNKNOWN,
    "none": UNKNOWN,
    "unknown": UNKNOWN,
    "pending": PENDING,
    "created": PENDING,
    "new": PENDING,
    "queued": QUEUED,
    "scheduled": QUEUED,
    "active": RUNNING,
    "running": RUNNING,
    "started": RUNNING,
    "scanning": RUNNING,
    "planning": RUNNING,
    "applying": RUNNING,
    "ok": EXECUTED,
    "success": EXECUTED,
    "succeeded": EXECUTED,
    "done": EXECUTED,
    "completed": EXECUTED,
    "complete": EXECUTED,
    "finished": EXECUTED,
    "executed": EXECUTED,
    "finalized": EXECUTED,
    "verifying": VERIFYING,
    "verified": VERIFIED,
    "error": FAILED,
    "exception": FAILED,
    "failure": FAILED,
    "failed": FAILED,
    "denied": BLOCKED,
    "rejected": BLOCKED,
    "policy_blocked": BLOCKED,
    "blocked": BLOCKED,
    "rollback": ROLLING_BACK,
    "rollback_required": ROLLING_BACK,
    "rolling_back": ROLLING_BACK,
    "rolled_back": ROLLED_BACK,
    "rollback_skipped": ROLLED_BACK,
    "recovering": RECOVERING,
    "recovery": RECOVERING,
    "recovered": RECOVERED,
    "consistent": RECOVERED,
    "replaying": REPLAYING,
    "replay": REPLAYING,
    "replayed": REPLAYED,
    "committing": COMMITTED,
    "committed": COMMITTED,
    "sealed": SEALED,
}

_TERMINAL_STATUSES = {
    EXECUTED,
    VERIFIED,
    BLOCKED,
    FAILED,
    ROLLED_BACK,
    RECOVERED,
    REPLAYED,
    COMMITTED,
    SEALED,
}
_FAILURE_STATUSES = {FAILED}
_SUCCESS_STATUSES = {EXECUTED, VERIFIED, RECOVERED, REPLAYED, COMMITTED, SEALED}
_BLOCKED_STATUSES = {BLOCKED}


def normalize_runtime_status(value: Any, *, default: str = UNKNOWN) -> str:
    text = str(value or "").strip().lower()
    if not text:
        text = str(default or UNKNOWN).strip().lower()
    normalized = text.replace("-", "_").replace(" ", "_")
    return _STATUS_ALIASES.get(normalized, _STATUS_ALIASES.get(str(default).lower(), UNKNOWN))


def is_terminal_runtime_status(status: Any) -> bool:
    return normalize_runtime_status(status) in _TERMINAL_STATUSES


def is_failure_runtime_status(status: Any) -> bool:
    return normalize_runtime_status(status) in _FAILURE_STATUSES


def is_success_runtime_status(status: Any) -> bool:
    return normalize_runtime_status(status) in _SUCCESS_STATUSES


def is_blocked_runtime_status(status: Any) -> bool:
    return normalize_runtime_status(status) in _BLOCKED_STATUSES


def status_from_execution_result(payload: Any) -> str:
    data = payload if isinstance(payload, dict) else {}
    if data.get("blocked") is True:
        return BLOCKED
    if data.get("failed") is True:
        return FAILED
    if data.get("verification_passed") is True and (
        data.get("ok") is True or data.get("executed") is True
    ):
        return VERIFIED
    if data.get("ok") is True or data.get("executed") is True or data.get("success") is True:
        return EXECUTED
    if data.get("ok") is False or data.get("success") is False:
        return FAILED
    if data.get("status") is not None:
        return normalize_runtime_status(data.get("status"))
    if data.get("result") is not None:
        return normalize_runtime_status(data.get("result"))
    return UNKNOWN


def status_from_lifecycle_phase(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == "created":
        return PENDING
    if text == "active":
        return RUNNING
    return normalize_runtime_status(text)


def status_from_transaction_state(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == "created":
        return PENDING
    if text == "active":
        return RUNNING
    return normalize_runtime_status(text)


def status_from_recovery_state(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"consistent", "reconstructed"}:
        return RECOVERED
    if text in {"inconsistent", "diverged"}:
        return FAILED
    return normalize_runtime_status(text)


def status_from_replay_state(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"verified", "done", "completed", "complete", "finished"}:
        return REPLAYED
    return normalize_runtime_status(text)


def canonical_runtime_status_payload(
    payload: Any,
    *,
    status: Any = None,
) -> dict[str, Any]:
    data = copy.deepcopy(payload) if isinstance(payload, dict) else {}

    if status is not None:
        canonical_status = normalize_runtime_status(status)
    elif isinstance(data.get("runtime_execution_result"), dict):
        canonical_status = status_from_execution_result(data.get("runtime_execution_result"))
    elif isinstance(data.get("execution_result"), dict):
        canonical_status = status_from_execution_result(data.get("execution_result"))
    elif any(key in data for key in ("ok", "executed", "success", "blocked", "failed", "verification_passed")):
        canonical_status = status_from_execution_result(data)
    elif data.get("phase") is not None:
        canonical_status = status_from_lifecycle_phase(data.get("phase"))
    elif data.get("state") is not None:
        canonical_status = normalize_runtime_status(data.get("state"))
    elif data.get("status") is not None:
        canonical_status = normalize_runtime_status(data.get("status"))
    elif data.get("result") is not None:
        canonical_status = normalize_runtime_status(data.get("result"))
    else:
        canonical_status = UNKNOWN

    data["canonical_status"] = canonical_status
    return data
