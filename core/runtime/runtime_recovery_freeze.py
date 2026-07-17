from __future__ import annotations

import copy
import hashlib
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping

from core.runtime.runtime_transaction_registry import (
    RuntimeTransaction,
    RuntimeTransactionState,
    create_transaction,
    get_transaction,
    list_transactions,
    record_apply,
    record_approval,
    record_audit,
    record_commit,
    record_failure,
    record_preflight,
    record_rollback,
    record_verification,
)


class RuntimeRecoveryState(str, Enum):
    PROPOSED = "proposed"
    PREFLIGHT = "preflight"
    APPLIED = "applied"
    VERIFIED = "verified"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED_TERMINAL = "failed_terminal"
    BLOCKED = "blocked"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"


TERMINAL_RECOVERY_STATES = {
    RuntimeRecoveryState.COMMITTED,
    RuntimeRecoveryState.ROLLED_BACK,
    RuntimeRecoveryState.FAILED_TERMINAL,
    RuntimeRecoveryState.BLOCKED,
    RuntimeRecoveryState.REQUIRES_HUMAN_REVIEW,
}


@dataclass(frozen=True)
class RuntimeRecoveryAttempt:
    recovery_attempt_id: str
    original_transaction_id: str
    original_trace_id: str = ""
    replay_run_id: str = ""
    recovery_source: str = "runtime_recovery_freeze"
    state: RuntimeRecoveryState = RuntimeRecoveryState.PROPOSED
    retry_count: int = 0
    max_retries: int = 1
    recovery_transaction_id: str = ""
    rollback_transaction_id: str = ""
    preflight_result: dict[str, Any] = field(default_factory=dict)
    apply_result: dict[str, Any] = field(default_factory=dict)
    verification_result: dict[str, Any] = field(default_factory=dict)
    commit_result: dict[str, Any] = field(default_factory=dict)
    rollback_result: dict[str, Any] = field(default_factory=dict)
    failure_result: dict[str, Any] = field(default_factory=dict)
    audit_refs: tuple[str, ...] = ()
    replay_refs: tuple[str, ...] = ()
    prediction_refs: tuple[str, ...] = ()
    evidence_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    state_history: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        payload["audit_refs"] = list(self.audit_refs)
        payload["replay_refs"] = list(self.replay_refs)
        payload["prediction_refs"] = list(self.prediction_refs)
        payload["state_history"] = list(self.state_history)
        return payload


@dataclass(frozen=True)
class RuntimeRecoveryDecision:
    decision_id: str
    state: RuntimeRecoveryState
    recovery_attempt_id: str
    original_transaction_id: str
    recovery_transaction_id: str = ""
    rollback_transaction_id: str = ""
    reason: str = ""
    requires_human_review: bool = False
    retry_allowed: bool = False
    retry_count: int = 0
    max_retries: int = 1
    audit_refs: tuple[str, ...] = ()
    prediction_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        payload["audit_refs"] = list(self.audit_refs)
        payload["prediction_refs"] = list(self.prediction_refs)
        return payload


_ATTEMPTS: dict[str, RuntimeRecoveryAttempt] = {}


def create_recovery_attempt(
    *,
    original_transaction_id: str,
    original_trace_id: str = "",
    replay_run_id: str = "",
    recovery_source: str = "runtime_recovery_freeze",
    max_retries: int = 1,
    audit_refs: Any = None,
    replay_refs: Any = None,
    prediction_refs: Any = None,
) -> RuntimeRecoveryAttempt:
    if not str(original_transaction_id or "").strip():
        raise ValueError("recovery requires original_transaction_id")
    try:
        source_tx = get_transaction(original_transaction_id)
        if not original_trace_id:
            original_trace_id = source_tx.trace_id
    except Exception:
        source_tx = None
    now = _now()
    attempt = RuntimeRecoveryAttempt(
        recovery_attempt_id=_recovery_attempt_id(original_transaction_id, original_trace_id, len(_ATTEMPTS) + 1),
        original_transaction_id=str(original_transaction_id),
        original_trace_id=str(original_trace_id or ""),
        replay_run_id=str(replay_run_id or ""),
        recovery_source=str(recovery_source or "runtime_recovery_freeze"),
        max_retries=max(0, int(max_retries)),
        audit_refs=_normalize_text_tuple(audit_refs),
        replay_refs=_normalize_text_tuple(replay_refs or ([replay_run_id] if replay_run_id else [])),
        prediction_refs=_normalize_text_tuple(prediction_refs),
        created_at=now,
        updated_at=now,
        state_history=(RuntimeRecoveryState.PROPOSED.value,),
    )
    _ATTEMPTS[attempt.recovery_attempt_id] = attempt
    return attempt


def record_recovery_preflight(attempt: RuntimeRecoveryAttempt | str, result: Mapping[str, Any]) -> RuntimeRecoveryAttempt:
    current = get_recovery_attempt(attempt)
    ok = _result_ok(result)
    if not ok:
        return _replace_attempt(
            current,
            state=RuntimeRecoveryState.BLOCKED,
            preflight_result=dict(result or {}),
            failure_result={"reason": str((result or {}).get("reason") or "recovery_preflight_blocked")},
        )
    return _replace_attempt(current, state=RuntimeRecoveryState.PREFLIGHT, preflight_result=dict(result or {}))


def record_recovery_apply(
    attempt: RuntimeRecoveryAttempt | str,
    result: Mapping[str, Any],
    *,
    transaction: RuntimeTransaction | str | None = None,
) -> RuntimeRecoveryAttempt:
    current = get_recovery_attempt(attempt)
    tx_id = current.recovery_transaction_id
    if transaction is not None:
        tx_id = get_transaction(transaction).transaction_id
    if not _result_ok(result):
        return record_recovery_terminal_failure(current, str((result or {}).get("reason") or "recovery_apply_failed"), result=result)
    return _replace_attempt(
        current,
        state=RuntimeRecoveryState.APPLIED,
        apply_result=dict(result or {}),
        recovery_transaction_id=tx_id,
    )


def record_recovery_verify(attempt: RuntimeRecoveryAttempt | str, result: Mapping[str, Any]) -> RuntimeRecoveryAttempt:
    current = get_recovery_attempt(attempt)
    if not _result_ok(result):
        return _replace_attempt(
            current,
            state=RuntimeRecoveryState.FAILED_TERMINAL,
            verification_result=dict(result or {}),
            failure_result={"reason": str((result or {}).get("reason") or (result or {}).get("message") or "recovery_verification_failed")},
        )
    return _replace_attempt(current, state=RuntimeRecoveryState.VERIFIED, verification_result=dict(result or {}))


def record_recovery_commit(attempt: RuntimeRecoveryAttempt | str, result: Mapping[str, Any]) -> RuntimeRecoveryAttempt:
    current = get_recovery_attempt(attempt)
    if current.state is not RuntimeRecoveryState.VERIFIED or not _result_ok(current.verification_result):
        raise ValueError("committed recovery requires verified success")
    return _replace_attempt(current, state=RuntimeRecoveryState.COMMITTED, commit_result=dict(result or {}))


def record_recovery_rollback(
    attempt: RuntimeRecoveryAttempt | str,
    result: Mapping[str, Any],
    *,
    transaction: RuntimeTransaction | str | None = None,
) -> RuntimeRecoveryAttempt:
    current = get_recovery_attempt(attempt)
    if not result:
        raise ValueError("rolled_back recovery requires rollback evidence")
    rollback_tx_id = current.rollback_transaction_id
    if transaction is not None:
        rollback_tx_id = get_transaction(transaction).transaction_id
    return _replace_attempt(
        current,
        state=RuntimeRecoveryState.ROLLED_BACK,
        rollback_result=dict(result or {}),
        rollback_transaction_id=rollback_tx_id,
    )


def record_recovery_terminal_failure(
    attempt: RuntimeRecoveryAttempt | str,
    reason: str,
    *,
    result: Mapping[str, Any] | None = None,
) -> RuntimeRecoveryAttempt:
    if not str(reason or "").strip():
        raise ValueError("failed_terminal recovery requires reason")
    current = get_recovery_attempt(attempt)
    return _replace_attempt(
        current,
        state=RuntimeRecoveryState.FAILED_TERMINAL,
        failure_result={"reason": str(reason), **dict(result or {})},
    )


def handoff_terminal_failure_to_autonomous_repair(
    attempt: RuntimeRecoveryAttempt | str,
    *,
    authority: Mapping[str, Any] | None = None,
    max_attempts: int = 1,
) -> Any:
    current = get_recovery_attempt(attempt)
    if current.state is RuntimeRecoveryState.REQUIRES_HUMAN_REVIEW:
        return {
            "ok": False,
            "state": RuntimeRecoveryState.REQUIRES_HUMAN_REVIEW.value,
            "reason": "requires_human_review_stops_autonomous_repair",
            "recovery_attempt_id": current.recovery_attempt_id,
        }
    if current.state is RuntimeRecoveryState.BLOCKED:
        return {
            "ok": False,
            "state": RuntimeRecoveryState.BLOCKED.value,
            "reason": "blocked_recovery_stops_autonomous_repair",
            "recovery_attempt_id": current.recovery_attempt_id,
        }
    if current.state is not RuntimeRecoveryState.FAILED_TERMINAL:
        return {
            "ok": False,
            "state": current.state.value,
            "reason": "autonomous_repair_requires_terminal_failure",
            "recovery_attempt_id": current.recovery_attempt_id,
        }
    from core.runtime.autonomous_repair_loop import run_autonomous_repair_loop

    return run_autonomous_repair_loop(
        {
            "task_id": "task-recovery-repair",
            "step_id": "step-recovery-repair",
            "trace_id": current.original_trace_id,
            "failure_id": current.recovery_attempt_id,
            "reason": current.failure_result.get("reason") if current.failure_result else "recovery_failed_terminal",
            "transaction_id": current.original_transaction_id,
            "recovery_attempt_id": current.recovery_attempt_id,
        },
        authority=authority,
        max_attempts=max_attempts,
    )


def record_recovery_requires_human_review(
    attempt: RuntimeRecoveryAttempt | str,
    reason: str,
    *,
    result: Mapping[str, Any] | None = None,
) -> RuntimeRecoveryAttempt:
    current = get_recovery_attempt(attempt)
    return _replace_attempt(
        current,
        state=RuntimeRecoveryState.REQUIRES_HUMAN_REVIEW,
        failure_result={"reason": str(reason or "requires_human_review"), **dict(result or {})},
    )


def create_recovery_transaction(
    *,
    attempt: RuntimeRecoveryAttempt | str,
    task_id: str,
    step_id: str,
    trace_id: str,
    authority_source: str,
    surface: str = "recovery_apply",
    affected_files: Any = None,
    repair_loop_id: str = "",
    repair_source: str = "",
) -> RuntimeTransaction:
    current = get_recovery_attempt(attempt)
    tx = create_transaction(
        task_id=task_id,
        step_id=step_id,
        trace_id=trace_id,
        authority_source=authority_source,
        surface=surface,
        affected_files=affected_files,
        audit_refs=current.audit_refs,
        replay_refs=current.replay_refs,
        parent_transaction_id=current.original_transaction_id,
        recovery_source=current.recovery_source,
        original_transaction_id=current.original_transaction_id,
        original_trace_id=current.original_trace_id,
        repair_loop_id=repair_loop_id,
        repair_source=repair_source,
    )
    tx = record_preflight(tx, {"ok": True, "recovery_attempt_id": current.recovery_attempt_id})
    tx = record_approval(tx, {"ok": True, "approved": True, "recovery_attempt_id": current.recovery_attempt_id})
    updated = _replace_attempt(current, recovery_transaction_id=tx.transaction_id)
    return tx


def create_recovery_blocked_evidence(
    *,
    original_transaction_id: str = "",
    reason: str = "recovery_blocked",
    trace_id: str = "",
    surface: str = "recovery_apply",
) -> dict[str, Any]:
    seed = repr((original_transaction_id, reason, trace_id, surface)).encode("utf-8", errors="replace")
    return {
        "recovery_attempt_id": "blocked_recovery:" + hashlib.sha256(seed).hexdigest()[:16],
        "original_transaction_id": str(original_transaction_id or ""),
        "state": RuntimeRecoveryState.BLOCKED.value,
        "surface": surface,
        "blocked_reason": str(reason or "recovery_blocked"),
        "audit_refs": [trace_id] if trace_id else [],
    }


def get_recovery_attempt(attempt: RuntimeRecoveryAttempt | str) -> RuntimeRecoveryAttempt:
    if isinstance(attempt, RuntimeRecoveryAttempt):
        return attempt
    value = _ATTEMPTS.get(str(attempt or ""))
    if value is None:
        raise KeyError(f"recovery attempt not found: {attempt}")
    return value


def list_recovery_attempts(*, original_transaction_id: str | None = None) -> tuple[RuntimeRecoveryAttempt, ...]:
    values = tuple(_ATTEMPTS.values())
    if original_transaction_id is not None:
        values = tuple(item for item in values if item.original_transaction_id == original_transaction_id)
    return tuple(replace(item) for item in values)


def assert_recovery_terminal_state(attempt: RuntimeRecoveryAttempt | str) -> bool:
    current = get_recovery_attempt(attempt)
    if current.state not in TERMINAL_RECOVERY_STATES:
        raise AssertionError("recovery must end in terminal state")
    if current.state is RuntimeRecoveryState.COMMITTED:
        if RuntimeRecoveryState.VERIFIED.value not in current.state_history or not _result_ok(current.verification_result):
            raise AssertionError("committed recovery requires verified success")
    if current.state is RuntimeRecoveryState.ROLLED_BACK and not current.rollback_result:
        raise AssertionError("rolled_back recovery requires rollback evidence")
    if current.state is RuntimeRecoveryState.FAILED_TERMINAL and not current.failure_result:
        raise AssertionError("failed_terminal recovery requires reason")
    if current.retry_count > current.max_retries:
        _record_invariant_violation(
            "recovery.retry_loop_bounded",
            "recovery retry count exceeded bound",
            current.to_dict(),
        )
        raise AssertionError("recovery retry count exceeded bound")
    return True


def assert_recovery_does_not_overwrite_source_transaction(attempt: RuntimeRecoveryAttempt | str) -> bool:
    current = get_recovery_attempt(attempt)
    if current.recovery_transaction_id and current.recovery_transaction_id == current.original_transaction_id:
        raise AssertionError("recovery-created transaction must not overwrite source transaction")
    if current.rollback_transaction_id and current.rollback_transaction_id == current.original_transaction_id:
        raise AssertionError("rollback transaction must not overwrite source transaction")
    return True


def build_recovery_decision(attempt: RuntimeRecoveryAttempt | str) -> RuntimeRecoveryDecision:
    current = get_recovery_attempt(attempt)
    reason = ""
    if current.failure_result:
        reason = str(current.failure_result.get("reason") or "")
    decision_state = current.state
    retry_allowed = decision_state not in TERMINAL_RECOVERY_STATES and current.retry_count < current.max_retries
    payload = repr((current.recovery_attempt_id, current.state.value, reason)).encode("utf-8", errors="replace")
    prediction_refs = _prediction_refs_for_recovery(current)
    return RuntimeRecoveryDecision(
        decision_id="recovery_decision:" + hashlib.sha256(payload).hexdigest()[:16],
        state=decision_state,
        recovery_attempt_id=current.recovery_attempt_id,
        original_transaction_id=current.original_transaction_id,
        recovery_transaction_id=current.recovery_transaction_id,
        rollback_transaction_id=current.rollback_transaction_id,
        reason=reason,
        requires_human_review=decision_state is RuntimeRecoveryState.REQUIRES_HUMAN_REVIEW,
        retry_allowed=retry_allowed,
        retry_count=current.retry_count,
        max_retries=current.max_retries,
        audit_refs=current.audit_refs,
        prediction_refs=prediction_refs,
    )


def transaction_recovery_lineage(original_transaction_id: str) -> tuple[RuntimeTransaction, ...]:
    return list_transactions(original_transaction_id=original_transaction_id)


def _replace_attempt(attempt: RuntimeRecoveryAttempt, **updates: Any) -> RuntimeRecoveryAttempt:
    state = updates.get("state", attempt.state)
    history = attempt.state_history
    if state is not attempt.state:
        history = (*history, state.value)
    if state in TERMINAL_RECOVERY_STATES and not updates.get("evidence_id") and not attempt.evidence_id:
        try:
            from core.runtime.runtime_evidence_freeze import attach_recovery_evidence

            preview = replace(attempt, **updates, updated_at=_now(), state_history=history)
            updates["evidence_id"] = attach_recovery_evidence(preview).evidence_id
        except Exception:
            pass
    updated = replace(attempt, **updates, updated_at=_now(), state_history=history)
    _ATTEMPTS[updated.recovery_attempt_id] = updated
    if updated.state in TERMINAL_RECOVERY_STATES:
        try:
            from core.runtime.runtime_memory_engine import append_runtime_memory, memory_record_for_recovery

            append_runtime_memory(memory_record_for_recovery(updated))
        except Exception:
            pass
    return updated


def _result_ok(result: Mapping[str, Any] | None) -> bool:
    if not isinstance(result, Mapping):
        return False
    if result.get("ok") is False or result.get("allowed") is False:
        return False
    return bool(
        result.get("ok")
        or result.get("allowed")
        or result.get("approved")
        or result.get("verification_ok")
        or result.get("committed")
        or result.get("rollback_applied")
    )


def _normalize_text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Mapping):
        values = [value.get("id") or value.get("ref") or repr(value)]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]
    return tuple(str(item).strip() for item in values if str(item or "").strip())


def _recovery_attempt_id(original_transaction_id: str, original_trace_id: str, ordinal: int) -> str:
    digest = hashlib.sha256(repr((original_transaction_id, original_trace_id, ordinal)).encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"runtime_recovery:{digest}"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _record_invariant_violation(invariant: str, reason: str, context: Mapping[str, Any]) -> None:
    try:
        from core.runtime.runtime_constitution_freeze import record_runtime_invariant_violation

        record_runtime_invariant_violation(
            invariant,
            component="recovery",
            reason=reason,
            context=context,
        )
    except Exception:
        pass


def _prediction_refs_for_recovery(current: RuntimeRecoveryAttempt) -> tuple[str, ...]:
    if current.prediction_refs:
        return current.prediction_refs
    try:
        from core.runtime.runtime_prediction_engine import predict_rollback_risk

        prediction = predict_rollback_risk(
            {
                "trace_id": current.original_trace_id,
                "source_transaction_id": current.original_transaction_id,
                "source_replay_run_id": current.replay_run_id,
                "source_recovery_attempt_id": current.recovery_attempt_id,
            }
        )
        return (prediction.prediction_id,)
    except Exception:
        return ()
