from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


POLICY_ACTION_NONE = "none"
POLICY_ACTION_REQUIRE_REVIEW = "require_review"
POLICY_ACTION_DISABLE_MUTATION = "disable_mutation"
POLICY_ACTION_BLOCK_TOOL = "block_tool"
POLICY_ACTION_LIMIT_AUTONOMY = "limit_autonomy"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeStabilityPattern:
    pattern_key: str
    count: int
    last_seen_at: str
    affected_component: str
    recommended_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_key": self.pattern_key,
            "count": self.count,
            "last_seen_at": self.last_seen_at,
            "affected_component": self.affected_component,
            "recommended_action": self.recommended_action,
        }


@dataclass(frozen=True)
class RuntimeStabilityDecision:
    status: str
    health_score: int
    policy_action: str
    detected_patterns: list[dict[str, Any]] = field(default_factory=list)
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
            "artifact_type": "runtime_stability_decision",
            "status": self.status,
            "health_score": self.health_score,
            "policy_action": self.policy_action,
            "detected_patterns": copy.deepcopy(self.detected_patterns),
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


class RuntimeStabilityMemory:
    """
    Runtime instability pattern memory.

    This layer records repeated instability patterns and recommends governance
    actions. It does not mutate runtime state directly.
    """

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def remember(
        self,
        *,
        component: str,
        failure_type: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            {
                "component": str(component or "runtime"),
                "failure_type": str(failure_type or "unknown_failure"),
                "details": copy.deepcopy(details or {}),
                "created_at": utc_timestamp(),
            }
        )

    def evaluate(self) -> RuntimeStabilityDecision:
        grouped: dict[str, int] = {}

        for event in self.events:
            component = str(event.get("component") or "runtime")
            failure_type = str(event.get("failure_type") or "unknown_failure")
            key = f"{component}::{failure_type}"
            grouped[key] = grouped.get(key, 0) + 1

        patterns: list[dict[str, Any]] = []
        policy_action = POLICY_ACTION_NONE
        health_score = 100

        for key, count in sorted(grouped.items()):
            component, failure_type = key.split("::", 1)
            action = POLICY_ACTION_NONE

            if count >= 5:
                action = POLICY_ACTION_BLOCK_TOOL
                policy_action = POLICY_ACTION_BLOCK_TOOL
                health_score -= 50
            elif count >= 3:
                action = POLICY_ACTION_DISABLE_MUTATION
                if policy_action != POLICY_ACTION_BLOCK_TOOL:
                    policy_action = POLICY_ACTION_DISABLE_MUTATION
                health_score -= 30
            elif count >= 2:
                action = POLICY_ACTION_REQUIRE_REVIEW
                if policy_action == POLICY_ACTION_NONE:
                    policy_action = POLICY_ACTION_REQUIRE_REVIEW
                health_score -= 15

            patterns.append(
                RuntimeStabilityPattern(
                    pattern_key=failure_type,
                    count=count,
                    last_seen_at=utc_timestamp(),
                    affected_component=component,
                    recommended_action=action,
                ).to_dict()
            )

        health_score = max(0, min(100, health_score))

        status = "healthy"
        if policy_action != POLICY_ACTION_NONE or health_score < 80:
            status = "degraded"
        if policy_action == POLICY_ACTION_BLOCK_TOOL or health_score <= 50:
            status = "unstable"

        return RuntimeStabilityDecision(
            status=status,
            health_score=health_score,
            policy_action=policy_action,
            detected_patterns=patterns,
        )


__all__ = [
    "RuntimeStabilityMemory",
    "RuntimeStabilityDecision",
    "RuntimeStabilityPattern",
    "POLICY_ACTION_NONE",
    "POLICY_ACTION_REQUIRE_REVIEW",
    "POLICY_ACTION_DISABLE_MUTATION",
    "POLICY_ACTION_BLOCK_TOOL",
    "POLICY_ACTION_LIMIT_AUTONOMY",
]
