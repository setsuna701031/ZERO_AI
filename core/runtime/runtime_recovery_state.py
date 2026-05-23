from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


RECOVERY_EXECUTION_STATUS_PLANNED = "planned"
RECOVERY_EXECUTION_STATUS_COMPLETED = "completed"
RECOVERY_EXECUTION_STATUS_BLOCKED = "blocked"
RECOVERY_EXECUTION_STATUS_FAILED = "failed"
RECOVERY_EXECUTION_STATUS_SKIPPED = "skipped"

RECOVERY_CONTINUATION_BLOCKED = "blocked"
RECOVERY_CONTINUATION_READY = "ready_for_continuation"
RECOVERY_CONTINUATION_REQUIRES_ROLLBACK = "requires_rollback"
RECOVERY_CONTINUATION_UNRECOVERABLE = "unrecoverable"
RECOVERY_CONTINUATION_REQUIRES_REVIEW = "requires_review"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_recovery_execution_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _copy_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


def _copy_list(value: Any) -> list[Any]:
    return copy.deepcopy(value) if isinstance(value, list) else []


@dataclass(frozen=True)
class RuntimeRecoveryExecutionAction:
    action_id: str
    action_type: str
    status: str = RECOVERY_EXECUTION_STATUS_PLANNED
    reason: str = ""
    required: bool = True
    payload: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "status": self.status,
            "reason": self.reason,
            "required": self.required,
            "payload": copy.deepcopy(self.payload),
            "result": copy.deepcopy(self.result),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class RuntimeRecoveryExecutionResult:
    execution_id: str
    recovery_id: str
    source_session_id: str
    status: str
    continuation_decision: str
    action_results: list[dict[str, Any]] = field(default_factory=list)
    verification_snapshot: dict[str, Any] = field(default_factory=dict)
    recovery_chain_status: str = ""
    source_state_before: dict[str, Any] = field(default_factory=dict)
    source_state_after: dict[str, Any] = field(default_factory=dict)
    source_state_mutated: bool = False
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)
    updated_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "recovery_id": self.recovery_id,
            "source_session_id": self.source_session_id,
            "status": self.status,
            "continuation_decision": self.continuation_decision,
            "action_results": [copy.deepcopy(item) for item in self.action_results],
            "verification_snapshot": copy.deepcopy(self.verification_snapshot),
            "recovery_chain_status": self.recovery_chain_status,
            "source_state_before": copy.deepcopy(self.source_state_before),
            "source_state_after": copy.deepcopy(self.source_state_after),
            "source_state_mutated": self.source_state_mutated,
            "audit_events": [copy.deepcopy(item) for item in self.audit_events],
            "metadata": copy.deepcopy(self.metadata),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class RuntimeRecoveryExecutionStore:
    def __init__(self) -> None:
        self._results: dict[str, RuntimeRecoveryExecutionResult] = {}

    def put(self, result: RuntimeRecoveryExecutionResult) -> RuntimeRecoveryExecutionResult:
        self._results[result.execution_id] = copy.deepcopy(result)
        return result

    def get(self, execution_id: str) -> RuntimeRecoveryExecutionResult | None:
        item = self._results.get(str(execution_id or ""))
        return copy.deepcopy(item) if item is not None else None

    def list_results(self) -> list[RuntimeRecoveryExecutionResult]:
        return [copy.deepcopy(item) for item in self._results.values()]


def normalize_recovery_chain_payload(chain: Any) -> dict[str, Any]:
    if hasattr(chain, "to_dict") and callable(chain.to_dict):
        payload = chain.to_dict()
        return copy.deepcopy(payload if isinstance(payload, dict) else {})
    return _copy_dict(chain)


def build_recovery_execution_id(recovery_id: str, payload: dict[str, Any] | None = None) -> str:
    seed = {
        "recovery_id": str(recovery_id or ""),
        "payload": _copy_dict(payload),
        "created_at": utc_timestamp(),
    }
    return "runtime-recovery-exec-" + stable_recovery_execution_fingerprint(seed)[:16]


__all__ = [
    "RECOVERY_CONTINUATION_BLOCKED",
    "RECOVERY_CONTINUATION_READY",
    "RECOVERY_CONTINUATION_REQUIRES_REVIEW",
    "RECOVERY_CONTINUATION_REQUIRES_ROLLBACK",
    "RECOVERY_CONTINUATION_UNRECOVERABLE",
    "RECOVERY_EXECUTION_STATUS_BLOCKED",
    "RECOVERY_EXECUTION_STATUS_COMPLETED",
    "RECOVERY_EXECUTION_STATUS_FAILED",
    "RECOVERY_EXECUTION_STATUS_PLANNED",
    "RECOVERY_EXECUTION_STATUS_SKIPPED",
    "RuntimeRecoveryExecutionAction",
    "RuntimeRecoveryExecutionResult",
    "RuntimeRecoveryExecutionStore",
    "build_recovery_execution_id",
    "normalize_recovery_chain_payload",
    "stable_recovery_execution_fingerprint",
    "utc_timestamp",
]
