from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


SUPERVISOR_STATUS_HEALTHY = "healthy"
SUPERVISOR_STATUS_DEGRADED = "degraded"
SUPERVISOR_STATUS_ESCALATE = "escalate"
SUPERVISOR_STATUS_BLOCKED = "blocked"

SUPERVISOR_ACTION_CONTINUE = "continue_runtime"
SUPERVISOR_ACTION_THROTTLE = "throttle_recovery"
SUPERVISOR_ACTION_ESCALATE = "escalate_to_review"
SUPERVISOR_ACTION_BLOCK = "block_runtime"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


@dataclass(frozen=True)
class RuntimeSupervisorObservation:
    observation_id: str
    source: str
    status: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "source": self.source,
            "status": self.status,
            "event_type": self.event_type,
            "payload": copy.deepcopy(self.payload),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RuntimeSupervisorDecision:
    decision_id: str
    status: str
    action: str
    health_score: int
    failure_count: int
    recovery_count: int
    repeated_failure_count: int
    reasons: list[str] = field(default_factory=list)
    observations: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_timestamp)
    fingerprint: str = ""

    def __post_init__(self) -> None:
        reasons = [str(item) for item in self.reasons if str(item or "").strip()]
        object.__setattr__(self, "reasons", reasons)
        observations = [copy.deepcopy(item) for item in self.observations if isinstance(item, dict)]
        object.__setattr__(self, "observations", observations)
        if not self.fingerprint:
            object.__setattr__(
                self,
                "fingerprint",
                _stable_fingerprint(self.to_dict(include_fingerprint=False)),
            )

    def to_dict(self, include_fingerprint: bool = True) -> dict[str, Any]:
        payload = {
            "artifact_type": "runtime_supervisor_decision",
            "decision_id": self.decision_id,
            "status": self.status,
            "action": self.action,
            "health_score": self.health_score,
            "failure_count": self.failure_count,
            "recovery_count": self.recovery_count,
            "repeated_failure_count": self.repeated_failure_count,
            "reasons": list(self.reasons),
            "observations": copy.deepcopy(self.observations),
            "created_at": self.created_at,
        }
        if include_fingerprint:
            payload["fingerprint"] = self.fingerprint
            payload["verified"] = self.verify()
        return payload

    def verify(self) -> bool:
        return self.fingerprint == _stable_fingerprint(self.to_dict(include_fingerprint=False))


def build_supervisor_observation_id(source: str, event_type: str, payload: dict[str, Any]) -> str:
    seed = {
        "source": str(source or ""),
        "event_type": str(event_type or ""),
        "payload": payload,
    }
    return "runtime-supervisor-observation-" + _stable_fingerprint(seed)[:16]


def build_supervisor_decision_id(observations: list[dict[str, Any]]) -> str:
    return "runtime-supervisor-decision-" + _stable_fingerprint(observations)[:16]


class RuntimeSupervisorLoop:
    """
    Runtime health supervisor.

    The supervisor does not execute recovery and does not mutate runtime state.
    It observes recovery/failure/replay/continuation outcomes and returns a
    governed decision for the owning runtime loop to apply.
    """

    def __init__(
        self,
        *,
        max_failures_before_degraded: int = 2,
        max_repeated_failures_before_escalate: int = 2,
        max_failures_before_block: int = 5,
    ) -> None:
        self.max_failures_before_degraded = int(max_failures_before_degraded)
        self.max_repeated_failures_before_escalate = int(max_repeated_failures_before_escalate)
        self.max_failures_before_block = int(max_failures_before_block)
        self._observations: list[RuntimeSupervisorObservation] = []

    @property
    def observations(self) -> tuple[RuntimeSupervisorObservation, ...]:
        return tuple(self._observations)

    def observe(
        self,
        *,
        source: str,
        status: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> RuntimeSupervisorObservation:
        payload_copy = copy.deepcopy(payload if isinstance(payload, dict) else {})
        observation = RuntimeSupervisorObservation(
            observation_id=build_supervisor_observation_id(source, event_type, payload_copy),
            source=str(source or "runtime"),
            status=str(status or "unknown"),
            event_type=str(event_type or "runtime_event"),
            payload=payload_copy,
        )
        self._observations.append(observation)
        return observation

    def evaluate(self) -> RuntimeSupervisorDecision:
        observation_payloads = [item.to_dict() for item in self._observations]

        failure_events = [
            item for item in self._observations
            if self._is_failure(item)
        ]
        recovery_events = [
            item for item in self._observations
            if self._is_recovery(item)
        ]

        repeated_failure_count = self._count_repeated_failures(failure_events)
        failure_count = len(failure_events)
        recovery_count = len(recovery_events)

        health_score = self._score_health(
            failure_count=failure_count,
            recovery_count=recovery_count,
            repeated_failure_count=repeated_failure_count,
        )

        status, action, reasons = self._decide(
            failure_count=failure_count,
            recovery_count=recovery_count,
            repeated_failure_count=repeated_failure_count,
            health_score=health_score,
        )

        return RuntimeSupervisorDecision(
            decision_id=build_supervisor_decision_id(observation_payloads),
            status=status,
            action=action,
            health_score=health_score,
            failure_count=failure_count,
            recovery_count=recovery_count,
            repeated_failure_count=repeated_failure_count,
            reasons=reasons,
            observations=observation_payloads,
        )

    def evaluate_payloads(self, payloads: list[dict[str, Any]]) -> RuntimeSupervisorDecision:
        self._observations = []
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            self.observe(
                source=str(payload.get("source") or "runtime"),
                status=str(payload.get("status") or "unknown"),
                event_type=str(payload.get("event_type") or "runtime_event"),
                payload=dict(payload.get("payload") or {}),
            )
        return self.evaluate()

    def _is_failure(self, item: RuntimeSupervisorObservation) -> bool:
        status = item.status.lower()
        event_type = item.event_type.lower()
        return (
            "failed" in status
            or "failure" in event_type
            or "blocked" in status
            or bool(item.payload.get("failed"))
        )

    def _is_recovery(self, item: RuntimeSupervisorObservation) -> bool:
        status = item.status.lower()
        event_type = item.event_type.lower()
        return (
            "recovered" in status
            or "resumed" in status
            or "recovery" in event_type
            or bool(item.payload.get("recovered"))
        )

    def _count_repeated_failures(self, failures: list[RuntimeSupervisorObservation]) -> int:
        seen: dict[str, int] = {}
        for item in failures:
            key = str(
                item.payload.get("failure_type")
                or item.payload.get("error")
                or item.event_type
                or "failure"
            )
            seen[key] = seen.get(key, 0) + 1
        return max(seen.values()) if seen else 0

    def _score_health(
        self,
        *,
        failure_count: int,
        recovery_count: int,
        repeated_failure_count: int,
    ) -> int:
        score = 100
        score -= failure_count * 15
        score -= repeated_failure_count * 10
        score += min(recovery_count * 5, 20)
        if score < 0:
            return 0
        if score > 100:
            return 100
        return score

    def _decide(
        self,
        *,
        failure_count: int,
        recovery_count: int,
        repeated_failure_count: int,
        health_score: int,
    ) -> tuple[str, str, list[str]]:
        reasons: list[str] = []

        if failure_count >= self.max_failures_before_block:
            reasons.append("failure_limit_exceeded")
            return SUPERVISOR_STATUS_BLOCKED, SUPERVISOR_ACTION_BLOCK, reasons

        if repeated_failure_count >= self.max_repeated_failures_before_escalate:
            reasons.append("repeated_failure_escalation")
            return SUPERVISOR_STATUS_ESCALATE, SUPERVISOR_ACTION_ESCALATE, reasons

        if failure_count >= self.max_failures_before_degraded or health_score < 70:
            reasons.append("runtime_degraded")
            return SUPERVISOR_STATUS_DEGRADED, SUPERVISOR_ACTION_THROTTLE, reasons

        reasons.append("runtime_healthy")
        return SUPERVISOR_STATUS_HEALTHY, SUPERVISOR_ACTION_CONTINUE, reasons


def evaluate_runtime_supervisor_loop(
    payloads: list[dict[str, Any]],
    *,
    max_failures_before_degraded: int = 2,
    max_repeated_failures_before_escalate: int = 2,
    max_failures_before_block: int = 5,
) -> RuntimeSupervisorDecision:
    supervisor = RuntimeSupervisorLoop(
        max_failures_before_degraded=max_failures_before_degraded,
        max_repeated_failures_before_escalate=max_repeated_failures_before_escalate,
        max_failures_before_block=max_failures_before_block,
    )
    return supervisor.evaluate_payloads(payloads)


__all__ = [
    "SUPERVISOR_STATUS_HEALTHY",
    "SUPERVISOR_STATUS_DEGRADED",
    "SUPERVISOR_STATUS_ESCALATE",
    "SUPERVISOR_STATUS_BLOCKED",
    "SUPERVISOR_ACTION_CONTINUE",
    "SUPERVISOR_ACTION_THROTTLE",
    "SUPERVISOR_ACTION_ESCALATE",
    "SUPERVISOR_ACTION_BLOCK",
    "RuntimeSupervisorObservation",
    "RuntimeSupervisorDecision",
    "RuntimeSupervisorLoop",
    "evaluate_runtime_supervisor_loop",
]
