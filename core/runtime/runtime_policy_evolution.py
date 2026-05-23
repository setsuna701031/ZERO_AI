from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


POLICY_MODE_NORMAL = "normal"
POLICY_MODE_REVIEW_REQUIRED = "review_required"
POLICY_MODE_SAFE = "safe"
POLICY_MODE_RESTRICTED = "restricted"

ACTION_NONE = "none"
ACTION_REQUIRE_REVIEW = "require_review"
ACTION_DISABLE_MUTATION = "disable_mutation"
ACTION_BLOCK_TOOL = "block_tool"
ACTION_LOWER_AUTONOMY = "lower_autonomy"


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimePolicyRule:
    rule_id: str
    component: str
    trigger: str
    action: str
    severity: str
    created_at: str = field(default_factory=utc_timestamp)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "component": self.component,
            "trigger": self.trigger,
            "action": self.action,
            "severity": self.severity,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class RuntimePolicyEvolutionDecision:
    policy_mode: str
    autonomy_level: int
    applied_actions: list[str]
    generated_rules: list[dict[str, Any]]
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
            "artifact_type": "runtime_policy_evolution_decision",
            "policy_mode": self.policy_mode,
            "autonomy_level": self.autonomy_level,
            "applied_actions": list(self.applied_actions),
            "generated_rules": copy.deepcopy(self.generated_rules),
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


class RuntimePolicyEvolution:
    """
    Adaptive governance layer.

    Converts runtime instability history into runtime policy changes.
    """

    def evolve(
        self,
        *,
        stability_patterns: list[dict[str, Any]],
    ) -> RuntimePolicyEvolutionDecision:
        applied_actions: list[str] = []
        generated_rules: list[dict[str, Any]] = []

        autonomy_level = 100
        policy_mode = POLICY_MODE_NORMAL

        for pattern in stability_patterns:
            component = str(pattern.get("affected_component") or "runtime")
            trigger = str(pattern.get("pattern_key") or "unknown_pattern")
            recommended = str(pattern.get("recommended_action") or ACTION_NONE)
            count = int(pattern.get("count") or 0)

            if recommended == ACTION_REQUIRE_REVIEW:
                applied_actions.append(ACTION_REQUIRE_REVIEW)
                autonomy_level -= 15
                policy_mode = POLICY_MODE_REVIEW_REQUIRED

                generated_rules.append(
                    RuntimePolicyRule(
                        rule_id="rule-" + _stable_fingerprint(pattern)[:12],
                        component=component,
                        trigger=trigger,
                        action=ACTION_REQUIRE_REVIEW,
                        severity="medium",
                    ).to_dict()
                )

            elif recommended == ACTION_DISABLE_MUTATION:
                applied_actions.append(ACTION_DISABLE_MUTATION)
                autonomy_level -= 35
                policy_mode = POLICY_MODE_SAFE

                generated_rules.append(
                    RuntimePolicyRule(
                        rule_id="rule-" + _stable_fingerprint(pattern)[:12],
                        component=component,
                        trigger=trigger,
                        action=ACTION_DISABLE_MUTATION,
                        severity="high",
                    ).to_dict()
                )

            elif recommended == ACTION_BLOCK_TOOL:
                applied_actions.append(ACTION_BLOCK_TOOL)
                applied_actions.append(ACTION_LOWER_AUTONOMY)
                autonomy_level -= 60
                policy_mode = POLICY_MODE_RESTRICTED

                generated_rules.append(
                    RuntimePolicyRule(
                        rule_id="rule-" + _stable_fingerprint(pattern)[:12],
                        component=component,
                        trigger=trigger,
                        action=ACTION_BLOCK_TOOL,
                        severity="critical",
                    ).to_dict()
                )

            if count >= 5 and ACTION_LOWER_AUTONOMY not in applied_actions:
                applied_actions.append(ACTION_LOWER_AUTONOMY)
                autonomy_level -= 10

        autonomy_level = max(0, min(100, autonomy_level))

        return RuntimePolicyEvolutionDecision(
            policy_mode=policy_mode,
            autonomy_level=autonomy_level,
            applied_actions=sorted(set(applied_actions)),
            generated_rules=generated_rules,
        )


__all__ = [
    "RuntimePolicyEvolution",
    "RuntimePolicyEvolutionDecision",
    "RuntimePolicyRule",
    "POLICY_MODE_NORMAL",
    "POLICY_MODE_REVIEW_REQUIRED",
    "POLICY_MODE_SAFE",
    "POLICY_MODE_RESTRICTED",
    "ACTION_NONE",
    "ACTION_REQUIRE_REVIEW",
    "ACTION_DISABLE_MUTATION",
    "ACTION_BLOCK_TOOL",
    "ACTION_LOWER_AUTONOMY",
]
