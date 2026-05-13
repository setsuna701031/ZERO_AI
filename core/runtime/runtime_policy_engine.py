from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


_ALLOWED_EFFECTS = {"allow", "deny", "require_confirmation"}
_ALLOWED_RISK_LEVELS = {"low", "medium", "high", "critical"}
_RISK_ORDER = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}


@dataclass(frozen=True)
class RuntimePolicyRule:
    rule_id: str
    target: str
    action: str
    effect: str
    risk_level: str
    reason: str
    metadata: Any = None


@dataclass(frozen=True)
class RuntimePolicyViolation:
    rule_id: str
    target: str
    action: str
    risk_level: str
    reason: str
    metadata: Any


@dataclass(frozen=True)
class RuntimePolicyDecision:
    allowed: bool
    target: str
    action: str
    risk_level: str
    matched_rules: list[RuntimePolicyRule]
    violations: list[RuntimePolicyViolation]
    reason: str
    payload: Any
    metadata: Any
    sequence: int


class RuntimePolicyRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        decision: RuntimePolicyDecision | None = None,
    ) -> None:
        self.decision = decision
        super().__init__(message)


class RuntimePolicyEngine:
    def __init__(self) -> None:
        self._rules: dict[str, RuntimePolicyRule] = {}
        self._decisions: list[RuntimePolicyDecision] = []
        self._sequence = 0

    def add_rule(self, rule: RuntimePolicyRule) -> RuntimePolicyRule:
        self._validate_rule(rule)

        if rule.rule_id in self._rules:
            raise RuntimePolicyRejected(
                f"runtime policy rule already exists: {rule.rule_id!r}"
            )

        self._rules[rule.rule_id] = rule
        return self._copy_rule(rule)

    def evaluate(
        self,
        target: str,
        action: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimePolicyDecision:
        target = self._validate_text("target", target)
        action = self._validate_text("action", action)

        matched_rules = [
            rule
            for rule in self._rules.values()
            if rule.target == target and rule.action == action
        ]
        effective_rules = self._effective_rules(matched_rules)
        violations = [
            RuntimePolicyViolation(
                rule_id=rule.rule_id,
                target=rule.target,
                action=rule.action,
                risk_level=rule.risk_level,
                reason=rule.reason,
                metadata=rule.metadata,
            )
            for rule in matched_rules
            if rule.effect in {"deny", "require_confirmation"}
        ]

        allowed = not violations
        risk_level = self._decision_risk_level(effective_rules)
        reason = self._decision_reason(effective_rules, allowed)

        self._sequence += 1
        decision = RuntimePolicyDecision(
            allowed=allowed,
            target=target,
            action=action,
            risk_level=risk_level,
            matched_rules=[self._copy_rule(rule) for rule in matched_rules],
            violations=violations,
            reason=reason,
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
        )
        self._decisions.append(decision)
        return self._copy_decision(decision)

    def assert_allowed(
        self,
        target: str,
        action: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimePolicyDecision:
        decision = self.evaluate(
            target,
            action,
            payload=payload,
            metadata=metadata,
        )
        if not decision.allowed:
            raise RuntimePolicyRejected(
                "runtime policy rejected action",
                decision=decision,
            )

        return decision

    def get_rules(
        self,
        target: str | None = None,
        action: str | None = None,
    ) -> list[RuntimePolicyRule]:
        rules = list(self._rules.values())
        if target is not None:
            rules = [rule for rule in rules if rule.target == target]
        if action is not None:
            rules = [rule for rule in rules if rule.action == action]

        return [self._copy_rule(rule) for rule in rules]

    def get_decisions(self) -> list[RuntimePolicyDecision]:
        return [self._copy_decision(decision) for decision in self._decisions]

    def clear(self) -> None:
        self._rules.clear()
        self._decisions.clear()
        self._sequence = 0

    def _effective_rules(
        self,
        matched_rules: list[RuntimePolicyRule],
    ) -> list[RuntimePolicyRule]:
        for effect in ("deny", "require_confirmation", "allow"):
            rules = [rule for rule in matched_rules if rule.effect == effect]
            if rules:
                return rules

        return []

    def _decision_risk_level(self, rules: list[RuntimePolicyRule]) -> str:
        if not rules:
            return "low"

        return max(rules, key=lambda rule: _RISK_ORDER[rule.risk_level]).risk_level

    def _decision_reason(
        self,
        rules: list[RuntimePolicyRule],
        allowed: bool,
    ) -> str:
        if not rules:
            return "runtime policy default allow"

        prefix = "runtime policy allowed" if allowed else "runtime policy blocked"
        reasons = "; ".join(rule.reason for rule in rules if rule.reason)
        return f"{prefix}: {reasons}" if reasons else prefix

    def _validate_rule(self, rule: RuntimePolicyRule) -> None:
        self._validate_text("rule_id", rule.rule_id)
        self._validate_text("target", rule.target)
        self._validate_text("action", rule.action)

        if rule.effect not in _ALLOWED_EFFECTS:
            raise RuntimePolicyRejected(
                f"runtime policy invalid effect: {rule.effect!r}"
            )

        if rule.risk_level not in _ALLOWED_RISK_LEVELS:
            raise RuntimePolicyRejected(
                f"runtime policy invalid risk_level: {rule.risk_level!r}"
            )

    def _validate_text(self, field_name: str, value: str) -> str:
        if not str(value or "").strip():
            raise RuntimePolicyRejected(
                f"runtime policy {field_name} is required"
            )

        return value

    def _copy_rule(self, rule: RuntimePolicyRule) -> RuntimePolicyRule:
        return replace(rule)

    def _copy_decision(
        self,
        decision: RuntimePolicyDecision,
    ) -> RuntimePolicyDecision:
        return replace(
            decision,
            matched_rules=[
                self._copy_rule(rule)
                for rule in decision.matched_rules
            ],
            violations=list(decision.violations),
        )
