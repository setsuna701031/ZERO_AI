from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


REPLAY_RECOVERY_STATUS_RECONSTRUCTED = "reconstructed"
REPLAY_RECOVERY_STATUS_VERIFIED = "verified"
REPLAY_RECOVERY_STATUS_CONTINUABLE = "continuable"
REPLAY_RECOVERY_STATUS_BLOCKED = "blocked"
REPLAY_RECOVERY_STATUS_FAILED = "failed"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return copy.deepcopy(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        converted = to_dict()
        if isinstance(converted, dict):
            return copy.deepcopy(converted)
    return {}


def _text(*values: Any, default: str = "") -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return default


@dataclass(frozen=True)
class RuntimeReplayRecoveryResult:
    replay_recovery_id: str
    recovery_id: str
    source_session_id: str
    status: str
    replay_reference: dict[str, Any]
    reconstructed_incident: dict[str, Any]
    verification: dict[str, Any]
    continuation_decision: dict[str, Any]
    replay_events: list[dict[str, Any]] = field(default_factory=list)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_timestamp)
    fingerprint: str = ""

    def __post_init__(self) -> None:
        replay_events = [
            copy.deepcopy(item)
            for item in self.replay_events
            if isinstance(item, dict)
        ]
        audit_events = [
            copy.deepcopy(item)
            for item in self.audit_events
            if isinstance(item, dict)
        ]
        object.__setattr__(self, "replay_events", replay_events)
        object.__setattr__(self, "audit_events", audit_events)

        if not self.fingerprint:
            object.__setattr__(
                self,
                "fingerprint",
                _stable_fingerprint(self.to_dict(include_fingerprint=False)),
            )

    def to_dict(self, include_fingerprint: bool = True) -> dict[str, Any]:
        payload = {
            "artifact_type": "runtime_replay_recovery_result",
            "replay_recovery_id": self.replay_recovery_id,
            "recovery_id": self.recovery_id,
            "source_session_id": self.source_session_id,
            "status": self.status,
            "replay_reference": copy.deepcopy(self.replay_reference),
            "reconstructed_incident": copy.deepcopy(self.reconstructed_incident),
            "verification": copy.deepcopy(self.verification),
            "continuation_decision": copy.deepcopy(self.continuation_decision),
            "replay_events": copy.deepcopy(self.replay_events),
            "audit_events": copy.deepcopy(self.audit_events),
            "created_at": self.created_at,
        }

        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
            payload["verified"] = self.verify()

        return payload

    def verify(self) -> bool:
        return self.fingerprint == _stable_fingerprint(
            self.to_dict(include_fingerprint=False)
        )


def build_replay_recovery_id(
    recovery_id: str,
    source_session_id: str = "",
) -> str:
    seed = {
        "kind": "runtime_replay_recovery",
        "recovery_id": str(recovery_id or ""),
        "source_session_id": str(source_session_id or ""),
    }
    return "runtime-replay-recovery-" + _stable_fingerprint(seed)[:16]


class RuntimeReplayRecovery:
    """
    Replay-driven runtime recovery integration.

    This layer reconstructs incidents from replay evidence before
    continuation decisions are finalized.
    """

    def __init__(
        self,
        *,
        replay_engine: Any | None = None,
        incident_layer: Any | None = None,
    ) -> None:
        self.replay_engine = replay_engine
        self.incident_layer = incident_layer

    def reconstruct_runtime_failure(
        self,
        *,
        recovery_id: str,
        source_session_id: str,
        failure: dict[str, Any],
        replay_reference: dict[str, Any] | None = None,
        replay_events: list[dict[str, Any]] | None = None,
    ) -> RuntimeReplayRecoveryResult:
        replay_ref = copy.deepcopy(
            replay_reference if isinstance(replay_reference, dict) else {}
        )
        events = [
            copy.deepcopy(item)
            for item in (replay_events or [])
            if isinstance(item, dict)
        ]

        reconstructed = self._reconstruct_incident(
            source_session_id=source_session_id,
            failure=failure,
            replay_reference=replay_ref,
            replay_events=events,
        )

        verification = self._verify_replay_consistency(
            failure=failure,
            reconstructed=reconstructed,
            replay_reference=replay_ref,
            replay_events=events,
        )

        continuation = self._build_continuation_decision(
            failure=failure,
            verification=verification,
        )

        status = continuation["status"]

        audit_events = [
            {
                "event_type": "runtime_replay_recovery_started",
                "recovery_id": recovery_id,
                "source_session_id": source_session_id,
            },
            {
                "event_type": "runtime_replay_recovery_verified",
                "verification_status": verification["status"],
            },
            {
                "event_type": "runtime_replay_recovery_completed",
                "continuation_status": continuation["status"],
            },
        ]

        return RuntimeReplayRecoveryResult(
            replay_recovery_id=build_replay_recovery_id(
                recovery_id,
                source_session_id,
            ),
            recovery_id=recovery_id,
            source_session_id=source_session_id,
            status=status,
            replay_reference=replay_ref,
            reconstructed_incident=reconstructed,
            verification=verification,
            continuation_decision=continuation,
            replay_events=events,
            audit_events=audit_events,
        )

    def _reconstruct_incident(
        self,
        *,
        source_session_id: str,
        failure: dict[str, Any],
        replay_reference: dict[str, Any],
        replay_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        failure_type = _text(
            failure.get("failure_type"),
            default="runtime_failure",
        )

        reconstructed = {
            "incident_id": "incident-" + _stable_fingerprint(
                {
                    "session": source_session_id,
                    "failure": failure,
                }
            )[:12],
            "source_session_id": source_session_id,
            "failure_type": failure_type,
            "failure_message": _text(
                failure.get("failure_message"),
                failure.get("error"),
            ),
            "replay_reference": copy.deepcopy(replay_reference),
            "event_count": len(replay_events),
            "timeline": copy.deepcopy(replay_events),
        }

        if self.incident_layer is not None:
            attach = getattr(self.incident_layer, "attach_event", None)
            build = getattr(self.incident_layer, "build_incidents", None)

            if callable(attach):
                for event in replay_events:
                    attach(event)

            if callable(build):
                try:
                    incidents = build()
                    if incidents:
                        reconstructed["incident_summary"] = incidents[-1]
                except Exception:
                    pass

        return reconstructed

    def _verify_replay_consistency(
        self,
        *,
        failure: dict[str, Any],
        reconstructed: dict[str, Any],
        replay_reference: dict[str, Any],
        replay_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        failure_type = _text(
            failure.get("failure_type"),
            default="runtime_failure",
        )

        replay_ok = bool(replay_reference) or bool(replay_events)

        consistent = (
            replay_ok
            and reconstructed.get("failure_type") == failure_type
        )

        return {
            "status": (
                REPLAY_RECOVERY_STATUS_VERIFIED
                if consistent
                else REPLAY_RECOVERY_STATUS_FAILED
            ),
            "consistent": consistent,
            "replay_reference_present": bool(replay_reference),
            "replay_events_present": bool(replay_events),
            "failure_type_match": (
                reconstructed.get("failure_type") == failure_type
            ),
        }

    def _build_continuation_decision(
        self,
        *,
        failure: dict[str, Any],
        verification: dict[str, Any],
    ) -> dict[str, Any]:
        rollback_required = bool(failure.get("rollback_required"))

        if rollback_required:
            return {
                "status": REPLAY_RECOVERY_STATUS_BLOCKED,
                "next_action": "wait_for_recovery_approval",
            }

        if verification.get("consistent"):
            return {
                "status": REPLAY_RECOVERY_STATUS_CONTINUABLE,
                "next_action": "resume_runtime",
            }

        return {
            "status": REPLAY_RECOVERY_STATUS_FAILED,
            "next_action": "inspect_replay_reconstruction",
        }


def reconstruct_runtime_failure_from_replay(
    *,
    recovery_id: str,
    source_session_id: str,
    failure: dict[str, Any],
    replay_reference: dict[str, Any] | None = None,
    replay_events: list[dict[str, Any]] | None = None,
    replay_engine: Any | None = None,
    incident_layer: Any | None = None,
) -> RuntimeReplayRecoveryResult:
    runtime = RuntimeReplayRecovery(
        replay_engine=replay_engine,
        incident_layer=incident_layer,
    )

    return runtime.reconstruct_runtime_failure(
        recovery_id=recovery_id,
        source_session_id=source_session_id,
        failure=failure,
        replay_reference=replay_reference,
        replay_events=replay_events,
    )


__all__ = [
    "REPLAY_RECOVERY_STATUS_RECONSTRUCTED",
    "REPLAY_RECOVERY_STATUS_VERIFIED",
    "REPLAY_RECOVERY_STATUS_CONTINUABLE",
    "REPLAY_RECOVERY_STATUS_BLOCKED",
    "REPLAY_RECOVERY_STATUS_FAILED",
    "RuntimeReplayRecovery",
    "RuntimeReplayRecoveryResult",
    "build_replay_recovery_id",
    "reconstruct_runtime_failure_from_replay",
]
