from __future__ import annotations

import copy
from typing import Any

from core.runtime.runtime_status import (
    BLOCKED,
    COMMITTED,
    EXECUTED,
    FAILED,
    PENDING,
    QUEUED,
    RECOVERED,
    RECOVERING,
    REPLAYED,
    REPLAYING,
    ROLLED_BACK,
    ROLLING_BACK,
    RUNNING,
    SEALED,
    UNKNOWN,
    VERIFIED,
    VERIFYING,
    is_terminal_runtime_status,
    normalize_runtime_status,
)
from core.runtime.runtime_transition_evidence import build_transition_evidence


ALLOWED_RUNTIME_STATUS_TRANSITIONS: dict[str, set[str]] = {
    UNKNOWN: {PENDING, QUEUED, RUNNING, BLOCKED, FAILED, RECOVERED},
    PENDING: {QUEUED, RUNNING, BLOCKED, FAILED},
    QUEUED: {RUNNING, BLOCKED, FAILED},
    RUNNING: {EXECUTED, VERIFYING, BLOCKED, FAILED, COMMITTED},
    EXECUTED: {VERIFYING, VERIFIED, COMMITTED, SEALED, FAILED},
    VERIFYING: {VERIFIED, ROLLING_BACK, BLOCKED, FAILED},
    VERIFIED: {COMMITTED, SEALED, FAILED},
    COMMITTED: {REPLAYING, SEALED, FAILED},
    REPLAYING: {REPLAYED, FAILED},
    REPLAYED: {SEALED, FAILED},
    ROLLING_BACK: {ROLLED_BACK, FAILED},
    ROLLED_BACK: {RECOVERING, SEALED, FAILED},
    RECOVERING: {RUNNING, VERIFYING, RECOVERED, FAILED},
    RECOVERED: {REPLAYING, SEALED, FAILED},
    BLOCKED: {RECOVERING, FAILED, SEALED},
    FAILED: {RECOVERING, SEALED},
    SEALED: {SEALED},
}


def normalize_transition_status(value: Any) -> str:
    return normalize_runtime_status(value)


def can_transition_runtime_status(from_status: Any, to_status: Any) -> bool:
    source = normalize_transition_status(from_status)
    target = normalize_transition_status(to_status)
    return target in ALLOWED_RUNTIME_STATUS_TRANSITIONS.get(source, set())


def is_runtime_status_terminal(status: Any) -> bool:
    return is_terminal_runtime_status(status)


def is_runtime_status_regression(from_status: Any, to_status: Any) -> bool:
    source = normalize_transition_status(from_status)
    target = normalize_transition_status(to_status)
    if source == target:
        return False
    if source == SEALED:
        return target != SEALED
    return not can_transition_runtime_status(source, target)


def validate_runtime_status_transition(from_status: Any, to_status: Any) -> dict[str, Any]:
    source = normalize_transition_status(from_status)
    target = normalize_transition_status(to_status)
    allowed = can_transition_runtime_status(source, target)
    return {
        "from_status": source,
        "to_status": target,
        "allowed": bool(allowed),
        "regression": bool(is_runtime_status_regression(source, target)),
        "terminal_from": bool(is_runtime_status_terminal(source)),
    }


def runtime_status_transition_payload(
    from_status: Any,
    to_status: Any,
    *,
    source: str = "",
    metadata: dict[str, Any] | None = None,
    mode: Any = None,
) -> dict[str, Any]:
    validation = validate_runtime_status_transition(from_status, to_status)
    transition_evidence = build_transition_evidence(
        validation["from_status"],
        validation["to_status"],
        source=source,
        metadata=metadata,
    )
    payload = {
        **validation,
        "source": str(source or ""),
        "metadata": copy.deepcopy(metadata) if isinstance(metadata, dict) else {},
        "transition_reason": transition_evidence["reason"],
        "transition_trigger": transition_evidence["trigger"],
        "transition_source": transition_evidence["source"],
        "transition_evidence": transition_evidence,
    }
    from core.runtime.runtime_enforcement_readiness import apply_runtime_enforcement_decision

    return apply_runtime_enforcement_decision(
        payload,
        mode=mode,
        source=payload["transition_source"] or payload["source"],
        metadata=payload["metadata"],
    )


def transition_evidence_required(from_status: Any, to_status: Any) -> bool:
    source = normalize_transition_status(from_status)
    target = normalize_transition_status(to_status)
    return source != target


def canonical_transition_summary(
    from_status: Any,
    to_status: Any,
    *,
    source: str = "",
    metadata: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    runtime_execution_result: Any = None,
    mode: Any = None,
) -> dict[str, Any]:
    validation = validate_runtime_status_transition(from_status, to_status)
    transition_evidence = build_transition_evidence(
        validation["from_status"],
        validation["to_status"],
        source=source,
        runtime_execution_result=runtime_execution_result,
        metadata=metadata,
        evidence=evidence,
    )
    payload = {
        **validation,
        "canonical_transition": f"{validation['from_status']}->{validation['to_status']}",
        "transition_evidence": transition_evidence,
        "transition_reason": transition_evidence["reason"],
        "transition_trigger": transition_evidence["trigger"],
        "transition_source": transition_evidence["source"],
        "evidence_required": transition_evidence_required(
            validation["from_status"],
            validation["to_status"],
        ),
    }
    from core.runtime.runtime_enforcement_readiness import apply_runtime_enforcement_decision

    return apply_runtime_enforcement_decision(
        payload,
        mode=mode,
        source=transition_evidence["source"],
        metadata=metadata,
    )
