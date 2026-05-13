from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from core.runtime.runtime_policy_engine import (
    RuntimePolicyDecision,
    RuntimePolicyEngine,
    RuntimePolicyRule,
    RuntimePolicyViolation,
    RuntimePolicyRejected,
)


@dataclass(frozen=True)
class RuntimeGateResult:
    target: str
    action: str
    allowed: bool
    decision: RuntimePolicyDecision
    payload: Any
    metadata: Any
    sequence: int
    reason: str


class RuntimeGateRejected(RuntimeError):
    def __init__(
        self,
        message: str,
        decision: RuntimePolicyDecision | None = None,
        gate_result: RuntimeGateResult | None = None,
        original_exception: BaseException | None = None,
    ) -> None:
        self.decision = decision
        self.gate_result = gate_result
        self.original_exception = original_exception
        super().__init__(message)


class RuntimeExecutionGate:
    def __init__(self, policy_engine: RuntimePolicyEngine | None = None) -> None:
        self.policy_engine = (
            policy_engine
            if policy_engine is not None
            else RuntimePolicyEngine()
        )
        self._results: list[RuntimeGateResult] = []
        self._sequence = 0

    def check(
        self,
        target: str,
        action: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeGateResult:
        try:
            decision = self.policy_engine.evaluate(
                target,
                action,
                payload=payload,
                metadata=metadata,
            )
        except Exception as exc:
            decision = getattr(exc, "decision", None)
            raise RuntimeGateRejected(
                "runtime execution gate policy check failed",
                decision=decision,
                original_exception=exc,
            ) from exc

        return self._record_result(decision, payload=payload, metadata=metadata)

    def assert_open(
        self,
        target: str,
        action: str,
        payload: Any = None,
        metadata: Any = None,
    ) -> RuntimeGateResult:
        try:
            decision = self.policy_engine.assert_allowed(
                target,
                action,
                payload=payload,
                metadata=metadata,
            )
        except RuntimePolicyRejected as exc:
            decision = exc.decision
            gate_result = (
                self._record_result(decision, payload=payload, metadata=metadata)
                if decision is not None
                else None
            )
            raise RuntimeGateRejected(
                "runtime execution gate rejected action",
                decision=decision,
                gate_result=gate_result,
                original_exception=exc,
            ) from exc
        except Exception as exc:
            decision = getattr(exc, "decision", None)
            raise RuntimeGateRejected(
                "runtime execution gate policy assertion failed",
                decision=decision,
                original_exception=exc,
            ) from exc

        return self._record_result(decision, payload=payload, metadata=metadata)

    def get_results(self) -> list[RuntimeGateResult]:
        return [self._copy_result(result) for result in self._results]

    def clear(self) -> None:
        self._results.clear()
        self._sequence = 0

    def _record_result(
        self,
        decision: RuntimePolicyDecision,
        payload: Any,
        metadata: Any,
    ) -> RuntimeGateResult:
        self._sequence += 1
        result = RuntimeGateResult(
            target=decision.target,
            action=decision.action,
            allowed=decision.allowed,
            decision=decision,
            payload=payload,
            metadata=metadata,
            sequence=self._sequence,
            reason=decision.reason,
        )
        self._results.append(result)
        return self._copy_result(result)

    def _copy_result(self, result: RuntimeGateResult) -> RuntimeGateResult:
        return replace(result, decision=self._copy_decision(result.decision))

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
            violations=[
                self._copy_violation(violation)
                for violation in decision.violations
            ],
        )

    def _copy_rule(self, rule: RuntimePolicyRule) -> RuntimePolicyRule:
        return replace(rule)

    def _copy_violation(
        self,
        violation: RuntimePolicyViolation,
    ) -> RuntimePolicyViolation:
        return replace(violation)
