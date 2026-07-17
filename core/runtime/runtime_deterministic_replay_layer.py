from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


DETERMINISTIC_REPLAY_VERIFIED = "verified"
DETERMINISTIC_REPLAY_DIVERGED = "diverged"
DETERMINISTIC_REPLAY_BLOCKED = "blocked"

DIVERGENCE_NONE = "none"
DIVERGENCE_HASH_MISMATCH = "hash_mismatch"
DIVERGENCE_SEQUENCE_MISMATCH = "sequence_mismatch"
DIVERGENCE_EVENT_COUNT_MISMATCH = "event_count_mismatch"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonical_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": str(event.get("event_type") or ""),
        "runtime_zone": str(event.get("runtime_zone") or ""),
        "payload": copy.deepcopy(event.get("payload") if isinstance(event.get("payload"), dict) else {}),
        "sequence": int(event.get("sequence") or 0),
    }


@dataclass(frozen=True)
class RuntimeDeterministicReplayTrace:
    trace_id: str
    event_count: int
    canonical_hash: str
    final_state_hash: str
    final_state: dict[str, Any]
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "event_count": self.event_count,
            "canonical_hash": self.canonical_hash,
            "final_state_hash": self.final_state_hash,
            "final_state": copy.deepcopy(self.final_state),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RuntimeDeterministicReplayDecision:
    replay_status: str
    deterministic: bool
    divergence_type: str
    reason: str
    baseline_trace: dict[str, Any]
    replay_trace: dict[str, Any]
    created_at: str = field(default_factory=utc_timestamp)
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            object.__setattr__(
                self,
                "fingerprint",
                _stable_fingerprint(self.to_dict(include_fingerprint=False)),
            )

    def to_dict(self, include_fingerprint: bool = True) -> dict[str, Any]:
        payload = {
            "artifact_type": "runtime_deterministic_replay_decision",
            "replay_status": self.replay_status,
            "deterministic": self.deterministic,
            "divergence_type": self.divergence_type,
            "reason": self.reason,
            "baseline_trace": copy.deepcopy(self.baseline_trace),
            "replay_trace": copy.deepcopy(self.replay_trace),
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


class RuntimeDeterministicReplayLayer:
    """
    Deterministic runtime replay verifier.

    Given the same canonical event stream, replay should produce the same
    canonical trace hash and final reconstructed state hash.
    """

    def build_trace(
        self,
        *,
        events: list[dict[str, Any]],
    ) -> RuntimeDeterministicReplayTrace:
        canonical_events = [
            _canonical_event(event)
            for event in events
            if isinstance(event, dict)
        ]

        canonical_events.sort(key=lambda item: item["sequence"])

        final_state: dict[str, Any] = {
            "zones": {},
            "event_count": len(canonical_events),
            "last_event_type": "",
        }

        for event in canonical_events:
            zone = event["runtime_zone"]
            zone_state = final_state["zones"].setdefault(
                zone,
                {
                    "last_sequence": 0,
                    "events": [],
                },
            )
            zone_state["last_sequence"] = event["sequence"]
            zone_state["events"].append(
                {
                    "event_type": event["event_type"],
                    "payload": copy.deepcopy(event["payload"]),
                    "sequence": event["sequence"],
                }
            )
            final_state["last_event_type"] = event["event_type"]

        canonical_hash = _stable_fingerprint(canonical_events)
        final_state_hash = _stable_fingerprint(final_state)

        return RuntimeDeterministicReplayTrace(
            trace_id="deterministic-trace-" + canonical_hash[:16],
            event_count=len(canonical_events),
            canonical_hash=canonical_hash,
            final_state_hash=final_state_hash,
            final_state=final_state,
        )

    def verify_replay(
        self,
        *,
        baseline_events: list[dict[str, Any]],
        replay_events: list[dict[str, Any]],
    ) -> RuntimeDeterministicReplayDecision:
        if not baseline_events or not replay_events:
            empty_trace = RuntimeDeterministicReplayTrace(
                trace_id="deterministic-trace-empty",
                event_count=0,
                canonical_hash="",
                final_state_hash="",
                final_state={},
            ).to_dict()
            return RuntimeDeterministicReplayDecision(
                replay_status=DETERMINISTIC_REPLAY_BLOCKED,
                deterministic=False,
                divergence_type=DIVERGENCE_EVENT_COUNT_MISMATCH,
                reason="event_stream_missing",
                baseline_trace=empty_trace,
                replay_trace=empty_trace,
            )

        baseline_trace = self.build_trace(events=baseline_events)
        replay_trace = self.build_trace(events=replay_events)

        if baseline_trace.event_count != replay_trace.event_count:
            return self._decision(
                deterministic=False,
                divergence_type=DIVERGENCE_EVENT_COUNT_MISMATCH,
                reason="event_count_mismatch",
                baseline_trace=baseline_trace,
                replay_trace=replay_trace,
            )

        baseline_sequences = [
            _canonical_event(event)["sequence"]
            for event in baseline_events
            if isinstance(event, dict)
        ]
        replay_sequences = [
            _canonical_event(event)["sequence"]
            for event in replay_events
            if isinstance(event, dict)
        ]

        if sorted(baseline_sequences) != sorted(replay_sequences):
            return self._decision(
                deterministic=False,
                divergence_type=DIVERGENCE_SEQUENCE_MISMATCH,
                reason="sequence_mismatch",
                baseline_trace=baseline_trace,
                replay_trace=replay_trace,
            )

        if baseline_trace.canonical_hash != replay_trace.canonical_hash:
            return self._decision(
                deterministic=False,
                divergence_type=DIVERGENCE_HASH_MISMATCH,
                reason="canonical_event_hash_mismatch",
                baseline_trace=baseline_trace,
                replay_trace=replay_trace,
            )

        if baseline_trace.final_state_hash != replay_trace.final_state_hash:
            return self._decision(
                deterministic=False,
                divergence_type=DIVERGENCE_HASH_MISMATCH,
                reason="final_state_hash_mismatch",
                baseline_trace=baseline_trace,
                replay_trace=replay_trace,
            )

        return self._decision(
            deterministic=True,
            divergence_type=DIVERGENCE_NONE,
            reason="deterministic_replay_verified",
            baseline_trace=baseline_trace,
            replay_trace=replay_trace,
        )

    def _decision(
        self,
        *,
        deterministic: bool,
        divergence_type: str,
        reason: str,
        baseline_trace: RuntimeDeterministicReplayTrace,
        replay_trace: RuntimeDeterministicReplayTrace,
    ) -> RuntimeDeterministicReplayDecision:
        return RuntimeDeterministicReplayDecision(
            replay_status=(
                DETERMINISTIC_REPLAY_VERIFIED
                if deterministic
                else DETERMINISTIC_REPLAY_DIVERGED
            ),
            deterministic=deterministic,
            divergence_type=divergence_type,
            reason=reason,
            baseline_trace=baseline_trace.to_dict(),
            replay_trace=replay_trace.to_dict(),
        )


def verify_deterministic_runtime_replay(
    *,
    baseline_events: list[dict[str, Any]],
    replay_events: list[dict[str, Any]],
) -> RuntimeDeterministicReplayDecision:
    runtime = RuntimeDeterministicReplayLayer()
    return runtime.verify_replay(
        baseline_events=baseline_events,
        replay_events=replay_events,
    )


__all__ = [
    "RuntimeDeterministicReplayLayer",
    "RuntimeDeterministicReplayTrace",
    "RuntimeDeterministicReplayDecision",
    "DETERMINISTIC_REPLAY_VERIFIED",
    "DETERMINISTIC_REPLAY_DIVERGED",
    "DETERMINISTIC_REPLAY_BLOCKED",
    "DIVERGENCE_NONE",
    "DIVERGENCE_HASH_MISMATCH",
    "DIVERGENCE_SEQUENCE_MISMATCH",
    "DIVERGENCE_EVENT_COUNT_MISMATCH",
    "verify_deterministic_runtime_replay",
]
