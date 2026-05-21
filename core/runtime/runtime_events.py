from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.runtime.runtime_safe_schema import to_runtime_safe_schema
from core.runtime.runtime_version import RUNTIME_ABI_VERSION, RUNTIME_KERNEL_VERSION


RUNTIME_EVENT_CHANNEL = "runtime.kernel"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_event_id(event_type: str, payload: Any, metadata: Any, sequence: int) -> str:
    seed = {
        "event_type": str(event_type or ""),
        "payload": to_runtime_safe_schema(payload),
        "metadata": to_runtime_safe_schema(metadata),
        "sequence": int(sequence or 0),
    }
    encoded = json.dumps(seed, sort_keys=True, default=str, separators=(",", ":"))
    return f"runtime-event-{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:16]}"


@dataclass(frozen=True)
class RuntimeEvent:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    sequence: int = 0
    timestamp: str = field(default_factory=utc_timestamp)
    event_id: str = ""
    runtime_version: str = RUNTIME_KERNEL_VERSION
    abi_version: str = RUNTIME_ABI_VERSION

    def __post_init__(self) -> None:
        event_type = str(self.event_type or "").strip()
        if not event_type:
            raise ValueError("runtime_event_type_required")

        safe_payload = to_runtime_safe_schema(copy.deepcopy(self.payload or {}))
        safe_metadata = to_runtime_safe_schema(copy.deepcopy(self.metadata or {}))

        if not isinstance(safe_payload, dict):
            safe_payload = {"value": safe_payload}

        if not isinstance(safe_metadata, dict):
            safe_metadata = {"value": safe_metadata}

        object.__setattr__(self, "event_type", event_type)
        object.__setattr__(self, "payload", safe_payload)
        object.__setattr__(self, "metadata", safe_metadata)

        if not self.event_id:
            object.__setattr__(
                self,
                "event_id",
                stable_event_id(event_type, safe_payload, safe_metadata, self.sequence),
            )

    def with_sequence(self, sequence: int) -> "RuntimeEvent":
        return RuntimeEvent(
            event_type=self.event_type,
            payload=self.payload,
            metadata=self.metadata,
            sequence=int(sequence),
            timestamp=self.timestamp,
            event_id=stable_event_id(
                self.event_type,
                self.payload,
                self.metadata,
                int(sequence),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "runtime_version": self.runtime_version,
            "abi_version": self.abi_version,
            "event_type": self.event_type,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "payload": to_runtime_safe_schema(copy.deepcopy(self.payload)),
            "metadata": to_runtime_safe_schema(copy.deepcopy(self.metadata)),
        }


class RuntimeStateTransitionEvent(RuntimeEvent):
    def __init__(
        self,
        *,
        old_state: str,
        new_state: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
        sequence: int = 0,
    ) -> None:
        super().__init__(
            event_type="RuntimeStateTransitionEvent",
            payload={
                "old_state": old_state,
                "new_state": new_state,
                "reason": reason,
            },
            metadata=metadata or {},
            sequence=sequence,
        )


class MutationAppliedEvent(RuntimeEvent):
    def __init__(
        self,
        *,
        mutation_id: str,
        applied_paths: list[str] | tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
        sequence: int = 0,
    ) -> None:
        super().__init__(
            event_type="MutationAppliedEvent",
            payload={
                "mutation_id": str(mutation_id or ""),
                "applied_paths": list(applied_paths),
            },
            metadata=metadata or {},
            sequence=sequence,
        )


class VerificationCompletedEvent(RuntimeEvent):
    def __init__(
        self,
        *,
        verification_id: str,
        passed: bool,
        metadata: dict[str, Any] | None = None,
        sequence: int = 0,
    ) -> None:
        super().__init__(
            event_type="VerificationCompletedEvent",
            payload={
                "verification_id": str(verification_id or ""),
                "passed": bool(passed),
            },
            metadata=metadata or {},
            sequence=sequence,
        )


class RollbackTriggeredEvent(RuntimeEvent):
    def __init__(
        self,
        *,
        reason: str,
        rollback_paths: list[str] | tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
        sequence: int = 0,
    ) -> None:
        super().__init__(
            event_type="RollbackTriggeredEvent",
            payload={
                "reason": str(reason or ""),
                "rollback_paths": list(rollback_paths),
            },
            metadata=metadata or {},
            sequence=sequence,
        )


class RecoveryStartedEvent(RuntimeEvent):
    def __init__(
        self,
        *,
        recovery_id: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
        sequence: int = 0,
    ) -> None:
        super().__init__(
            event_type="RecoveryStartedEvent",
            payload={
                "recovery_id": str(recovery_id or ""),
                "reason": str(reason or ""),
            },
            metadata=metadata or {},
            sequence=sequence,
        )


class RecoveryCompletedEvent(RuntimeEvent):
    def __init__(
        self,
        *,
        recovery_id: str,
        recovered: bool,
        metadata: dict[str, Any] | None = None,
        sequence: int = 0,
    ) -> None:
        super().__init__(
            event_type="RecoveryCompletedEvent",
            payload={
                "recovery_id": str(recovery_id or ""),
                "recovered": bool(recovered),
            },
            metadata=metadata or {},
            sequence=sequence,
        )


class ReplayStartedEvent(RuntimeEvent):
    def __init__(
        self,
        *,
        replay_id: str,
        checkpoint_id: str = "",
        metadata: dict[str, Any] | None = None,
        sequence: int = 0,
    ) -> None:
        super().__init__(
            event_type="ReplayStartedEvent",
            payload={
                "replay_id": str(replay_id or ""),
                "checkpoint_id": str(checkpoint_id or ""),
            },
            metadata=metadata or {},
            sequence=sequence,
        )


class EvidenceAttachedEvent(RuntimeEvent):
    def __init__(
        self,
        *,
        evidence_id: str,
        artifact_path: str = "",
        metadata: dict[str, Any] | None = None,
        sequence: int = 0,
    ) -> None:
        super().__init__(
            event_type="EvidenceAttachedEvent",
            payload={
                "evidence_id": str(evidence_id or ""),
                "artifact_path": str(artifact_path or ""),
            },
            metadata=metadata or {},
            sequence=sequence,
        )


class TransactionCommittedEvent(RuntimeEvent):
    def __init__(
        self,
        *,
        transaction_id: str,
        metadata: dict[str, Any] | None = None,
        sequence: int = 0,
    ) -> None:
        super().__init__(
            event_type="TransactionCommittedEvent",
            payload={"transaction_id": str(transaction_id or "")},
            metadata=metadata or {},
            sequence=sequence,
        )


class TransactionRolledBackEvent(RuntimeEvent):
    def __init__(
        self,
        *,
        transaction_id: str,
        metadata: dict[str, Any] | None = None,
        sequence: int = 0,
    ) -> None:
        super().__init__(
            event_type="TransactionRolledBackEvent",
            payload={"transaction_id": str(transaction_id or "")},
            metadata=metadata or {},
            sequence=sequence,
        )


__all__ = [
    "RUNTIME_EVENT_CHANNEL",
    "RuntimeEvent",
    "RuntimeStateTransitionEvent",
    "MutationAppliedEvent",
    "VerificationCompletedEvent",
    "RollbackTriggeredEvent",
    "RecoveryStartedEvent",
    "RecoveryCompletedEvent",
    "ReplayStartedEvent",
    "EvidenceAttachedEvent",
    "TransactionCommittedEvent",
    "TransactionRolledBackEvent",
]