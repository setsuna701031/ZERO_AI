from __future__ import annotations

import copy
import hashlib
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Mapping

from core.runtime.runtime_surface_registry import (
    RuntimeSurfaceKind,
    classify_runtime_surface,
)


class RuntimeTransactionState(str, Enum):
    PROPOSED = "proposed"
    PREFLIGHT = "preflight"
    APPROVED = "approved"
    BLOCKED = "blocked"
    APPLIED = "applied"
    VERIFIED = "verified"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"
    AUDITED = "audited"


class RuntimeTransactionKind(str, Enum):
    FILE_MUTATION = "file_mutation"
    GIT_MUTATION = "git_mutation"
    RUNTIME_MUTATION = "runtime_mutation"
    UNKNOWN_MUTATION = "unknown_mutation"


class RuntimeTransactionRisk(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class RuntimeTransaction:
    transaction_id: str
    task_id: str
    step_id: str
    trace_id: str
    authority_source: str
    surface: str
    kind: RuntimeTransactionKind
    risk: RuntimeTransactionRisk
    state: RuntimeTransactionState
    affected_files: tuple[str, ...] = ()
    preflight_result: dict[str, Any] = field(default_factory=dict)
    approval_result: dict[str, Any] = field(default_factory=dict)
    apply_result: dict[str, Any] = field(default_factory=dict)
    verification_result: dict[str, Any] = field(default_factory=dict)
    commit_result: dict[str, Any] = field(default_factory=dict)
    rollback_result: dict[str, Any] = field(default_factory=dict)
    failure_result: dict[str, Any] = field(default_factory=dict)
    audit_refs: tuple[str, ...] = ()
    replay_refs: tuple[str, ...] = ()
    parent_transaction_id: str = ""
    replay_source: str = ""
    recovery_source: str = ""
    original_transaction_id: str = ""
    original_trace_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    state_history: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        payload["kind"] = self.kind.value
        payload["risk"] = self.risk.value
        payload["affected_files"] = list(self.affected_files)
        payload["audit_refs"] = list(self.audit_refs)
        payload["replay_refs"] = list(self.replay_refs)
        payload["state_history"] = list(self.state_history)
        return payload


_TRANSACTIONS: dict[str, RuntimeTransaction] = {}
_STATE_INDEX = {
    RuntimeTransactionState.PROPOSED: 0,
    RuntimeTransactionState.PREFLIGHT: 1,
    RuntimeTransactionState.APPROVED: 2,
    RuntimeTransactionState.BLOCKED: 2,
    RuntimeTransactionState.APPLIED: 3,
    RuntimeTransactionState.VERIFIED: 4,
    RuntimeTransactionState.COMMITTED: 5,
    RuntimeTransactionState.ROLLED_BACK: 5,
    RuntimeTransactionState.FAILED: 5,
    RuntimeTransactionState.AUDITED: 6,
}
_ALLOWED_TRANSITIONS = {
    RuntimeTransactionState.PROPOSED: {RuntimeTransactionState.PREFLIGHT},
    RuntimeTransactionState.PREFLIGHT: {
        RuntimeTransactionState.APPROVED,
        RuntimeTransactionState.BLOCKED,
    },
    RuntimeTransactionState.APPROVED: {RuntimeTransactionState.APPLIED},
    RuntimeTransactionState.APPLIED: {
        RuntimeTransactionState.VERIFIED,
        RuntimeTransactionState.ROLLED_BACK,
        RuntimeTransactionState.FAILED,
    },
    RuntimeTransactionState.VERIFIED: {
        RuntimeTransactionState.COMMITTED,
        RuntimeTransactionState.ROLLED_BACK,
        RuntimeTransactionState.FAILED,
    },
    RuntimeTransactionState.BLOCKED: {RuntimeTransactionState.AUDITED},
    RuntimeTransactionState.COMMITTED: {RuntimeTransactionState.AUDITED},
    RuntimeTransactionState.ROLLED_BACK: {RuntimeTransactionState.AUDITED},
    RuntimeTransactionState.FAILED: {RuntimeTransactionState.AUDITED},
}


def create_transaction(
    *,
    task_id: str,
    step_id: str,
    trace_id: str,
    authority_source: str,
    surface: str,
    affected_files: Any = None,
    audit_refs: Any = None,
    replay_refs: Any = None,
    parent_transaction_id: str = "",
    replay_source: str = "",
    recovery_source: str = "",
    original_transaction_id: str = "",
    original_trace_id: str = "",
) -> RuntimeTransaction:
    classified = classify_runtime_surface(surface)
    if classified.anonymous or not classified.requires_transaction:
        raise ValueError("transaction surface must be a registered mutation surface")
    required = {
        "task_id": task_id,
        "step_id": step_id,
        "trace_id": trace_id,
        "authority_source": authority_source,
        "surface": classified.name,
    }
    missing = [key for key, value in required.items() if not str(value or "").strip()]
    if missing:
        raise ValueError("anonymous transaction rejected: " + ", ".join(missing))
    if classified.name == "rollback_restore" and not (parent_transaction_id or affected_files):
        raise ValueError("rollback_restore requires parent transaction or rollback evidence")
    if replay_source and original_transaction_id and original_transaction_id in _TRANSACTIONS:
        pass

    now = _now()
    tx = RuntimeTransaction(
        transaction_id=_transaction_id(required, len(_TRANSACTIONS) + 1),
        task_id=str(task_id),
        step_id=str(step_id),
        trace_id=str(trace_id),
        authority_source=str(authority_source),
        surface=classified.name,
        kind=_kind_for_surface(classified.kind),
        risk=RuntimeTransactionRisk(classified.risk.value),
        state=RuntimeTransactionState.PROPOSED,
        affected_files=_normalize_text_tuple(affected_files),
        audit_refs=_normalize_text_tuple(audit_refs),
        replay_refs=_normalize_text_tuple(replay_refs),
        parent_transaction_id=str(parent_transaction_id or ""),
        replay_source=str(replay_source or ""),
        recovery_source=str(recovery_source or ""),
        original_transaction_id=str(original_transaction_id or ""),
        original_trace_id=str(original_trace_id or ""),
        created_at=now,
        updated_at=now,
        state_history=(RuntimeTransactionState.PROPOSED.value,),
    )
    _TRANSACTIONS[tx.transaction_id] = tx
    return tx


def record_preflight(transaction: RuntimeTransaction | str, result: Mapping[str, Any]) -> RuntimeTransaction:
    return _transition(transaction, RuntimeTransactionState.PREFLIGHT, preflight_result=dict(result or {}))


def record_approval(transaction: RuntimeTransaction | str, result: Mapping[str, Any]) -> RuntimeTransaction:
    allowed = _result_ok(result)
    return _transition(
        transaction,
        RuntimeTransactionState.APPROVED if allowed else RuntimeTransactionState.BLOCKED,
        approval_result=dict(result or {}),
    )


def record_apply(
    transaction: RuntimeTransaction | str,
    result: Mapping[str, Any],
    *,
    affected_files: Any = None,
) -> RuntimeTransaction:
    updates: dict[str, Any] = {"apply_result": dict(result or {})}
    normalized_files = _normalize_text_tuple(affected_files)
    if normalized_files:
        tx = get_transaction(transaction)
        updates["affected_files"] = tuple(dict.fromkeys((*tx.affected_files, *normalized_files)))
    return _transition(transaction, RuntimeTransactionState.APPLIED, **updates)


def record_verification(transaction: RuntimeTransaction | str, result: Mapping[str, Any]) -> RuntimeTransaction:
    tx = get_transaction(transaction)
    if not _result_ok(result):
        return _transition(
            tx,
            RuntimeTransactionState.FAILED,
            verification_result=dict(result or {}),
            failure_result={"reason": str((result or {}).get("reason") or (result or {}).get("message") or "verification_failed")},
        )
    return _transition(tx, RuntimeTransactionState.VERIFIED, verification_result=dict(result or {}))


def record_commit(transaction: RuntimeTransaction | str, result: Mapping[str, Any]) -> RuntimeTransaction:
    tx = get_transaction(transaction)
    if tx.state is not RuntimeTransactionState.VERIFIED or not _result_ok(tx.verification_result):
        raise ValueError("committed transaction requires verified success")
    return _transition(tx, RuntimeTransactionState.COMMITTED, commit_result=dict(result or {}))


def record_rollback(transaction: RuntimeTransaction | str, result: Mapping[str, Any]) -> RuntimeTransaction:
    tx = get_transaction(transaction)
    has_evidence = bool(result) or bool(tx.rollback_result) or bool(tx.apply_result) or bool(tx.parent_transaction_id)
    if not has_evidence:
        raise ValueError("rollback requires evidence")
    if tx.state not in {
        RuntimeTransactionState.APPLIED,
        RuntimeTransactionState.VERIFIED,
        RuntimeTransactionState.FAILED,
    }:
        raise ValueError("rolled_back requires applied state or rollback evidence")
    if tx.state is RuntimeTransactionState.FAILED:
        return _replace_tx(tx, rollback_result=dict(result or {}))
    return _transition(tx, RuntimeTransactionState.ROLLED_BACK, rollback_result=dict(result or {}))


def record_failure(transaction: RuntimeTransaction | str, reason: str, result: Mapping[str, Any] | None = None) -> RuntimeTransaction:
    if not str(reason or "").strip():
        raise ValueError("failed state requires reason")
    return _transition(
        transaction,
        RuntimeTransactionState.FAILED,
        failure_result={"reason": str(reason), **dict(result or {})},
    )


def record_audit(transaction: RuntimeTransaction | str, refs: Any = None) -> RuntimeTransaction:
    tx = get_transaction(transaction)
    if tx.state not in {
        RuntimeTransactionState.BLOCKED,
        RuntimeTransactionState.COMMITTED,
        RuntimeTransactionState.ROLLED_BACK,
        RuntimeTransactionState.FAILED,
    }:
        raise ValueError("audit requires terminal transaction state")
    audit_refs = tuple(dict.fromkeys((*tx.audit_refs, *_normalize_text_tuple(refs))))
    return _transition(tx, RuntimeTransactionState.AUDITED, audit_refs=audit_refs)


def get_transaction(transaction: RuntimeTransaction | str) -> RuntimeTransaction:
    if isinstance(transaction, RuntimeTransaction):
        return transaction
    tx = _TRANSACTIONS.get(str(transaction or ""))
    if tx is None:
        raise KeyError(f"transaction not found: {transaction}")
    return tx


def list_transactions(
    *,
    task_id: str | None = None,
    step_id: str | None = None,
    trace_id: str | None = None,
    original_transaction_id: str | None = None,
) -> tuple[RuntimeTransaction, ...]:
    values = tuple(_TRANSACTIONS.values())
    if task_id is not None:
        values = tuple(tx for tx in values if tx.task_id == task_id)
    if step_id is not None:
        values = tuple(tx for tx in values if tx.step_id == step_id)
    if trace_id is not None:
        values = tuple(tx for tx in values if tx.trace_id == trace_id)
    if original_transaction_id is not None:
        values = tuple(tx for tx in values if tx.original_transaction_id == original_transaction_id)
    return tuple(replace(tx) for tx in values)


def assert_transaction_lifecycle_valid(transaction: RuntimeTransaction | str) -> bool:
    tx = get_transaction(transaction)
    states = [RuntimeTransactionState(item) for item in tx.state_history]
    for previous, current in zip(states, states[1:]):
        if current not in _ALLOWED_TRANSITIONS.get(previous, set()):
            raise AssertionError(f"invalid transaction transition: {previous.value}->{current.value}")
        if _STATE_INDEX[current] < _STATE_INDEX[previous]:
            raise AssertionError("transaction lifecycle moved backwards")
    if tx.state in {RuntimeTransactionState.COMMITTED, RuntimeTransactionState.AUDITED}:
        if RuntimeTransactionState.COMMITTED.value in tx.state_history:
            if RuntimeTransactionState.VERIFIED.value not in tx.state_history or not _result_ok(tx.verification_result):
                raise AssertionError("committed transaction requires verified success")
    if tx.state is RuntimeTransactionState.ROLLED_BACK and not tx.rollback_result:
        raise AssertionError("rolled_back transaction requires rollback evidence")
    if tx.state is RuntimeTransactionState.FAILED and not tx.failure_result:
        raise AssertionError("failed transaction requires reason")
    classified = classify_runtime_surface(tx.surface)
    if classified.anonymous or not classified.requires_transaction:
        raise AssertionError("transaction surface must exist in runtime_surface_registry")
    if classified.kind is RuntimeSurfaceKind.FILE_MUTATION and not tx.affected_files:
        raise AssertionError("file mutation transaction requires affected_files")
    if tx.replay_source and tx.original_transaction_id and tx.transaction_id == tx.original_transaction_id:
        raise AssertionError("replay-created transaction must differ from source transaction")
    if tx.recovery_source and tx.original_transaction_id and tx.transaction_id == tx.original_transaction_id:
        raise AssertionError("recovery-created transaction must differ from source transaction")
    return True


def _transition(
    transaction: RuntimeTransaction | str,
    state: RuntimeTransactionState,
    **updates: Any,
) -> RuntimeTransaction:
    tx = get_transaction(transaction)
    if state not in _ALLOWED_TRANSITIONS.get(tx.state, set()):
        raise ValueError(f"invalid transaction transition: {tx.state.value}->{state.value}")
    return _replace_tx(tx, state=state, **updates)


def _replace_tx(tx: RuntimeTransaction, **updates: Any) -> RuntimeTransaction:
    state = updates.get("state", tx.state)
    history = tx.state_history
    if state is not tx.state:
        history = (*history, state.value)
    updated = replace(tx, **updates, updated_at=_now(), state_history=history)
    _TRANSACTIONS[updated.transaction_id] = updated
    return updated


def _transaction_id(required: Mapping[str, Any], ordinal: int) -> str:
    digest = hashlib.sha256(repr((required, ordinal)).encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"runtime_tx:{digest}"


def _kind_for_surface(kind: RuntimeSurfaceKind) -> RuntimeTransactionKind:
    if kind is RuntimeSurfaceKind.FILE_MUTATION:
        return RuntimeTransactionKind.FILE_MUTATION
    if kind is RuntimeSurfaceKind.GIT_MUTATION:
        return RuntimeTransactionKind.GIT_MUTATION
    if kind is RuntimeSurfaceKind.RUNTIME_MUTATION:
        return RuntimeTransactionKind.RUNTIME_MUTATION
    return RuntimeTransactionKind.UNKNOWN_MUTATION


def _normalize_text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Mapping):
        values = list(value.values())
    else:
        try:
            values = list(value)
        except TypeError:
            values = [value]
    return tuple(str(item) for item in values if str(item or "").strip())


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


def _now() -> str:
    return datetime.now(UTC).isoformat()


def transaction_to_dict(transaction: RuntimeTransaction | str) -> dict[str, Any]:
    payload = copy.deepcopy(get_transaction(transaction).to_dict())
    # Keep the public transaction serialization ABI stable for existing
    # lifecycle-contract tests.  Recovery lineage remains available on
    # RuntimeTransaction.to_dict(), but the legacy transaction_to_dict()
    # helper must not add new top-level keys.
    payload.pop("recovery_source", None)
    return payload
