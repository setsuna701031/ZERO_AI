from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimePolicyEngineContractTest(unittest.TestCase):
    def _rule(
        self,
        rule_id="rule-1",
        target="runtime.execution",
        action="start",
        effect="allow",
        risk_level="low",
        reason="contract rule",
        metadata=None,
    ):
        from core.runtime.runtime_policy_engine import RuntimePolicyRule

        return RuntimePolicyRule(
            rule_id=rule_id,
            target=target,
            action=action,
            effect=effect,
            risk_level=risk_level,
            reason=reason,
            metadata=metadata,
        )

    def test_add_allow_rule(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        rule = RuntimePolicyEngine().add_rule(self._rule(effect="allow"))

        self.assertEqual(rule.effect, "allow")

    def test_add_deny_rule(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        rule = RuntimePolicyEngine().add_rule(
            self._rule(effect="deny", risk_level="high")
        )

        self.assertEqual(rule.effect, "deny")

    def test_duplicate_rule_id_rejected(self) -> None:
        from core.runtime.runtime_policy_engine import (
            RuntimePolicyEngine,
            RuntimePolicyRejected,
        )

        engine = RuntimePolicyEngine()
        engine.add_rule(self._rule(rule_id="rule-1"))

        with self.assertRaises(RuntimePolicyRejected):
            engine.add_rule(self._rule(rule_id="rule-1", action="stop"))

    def test_empty_rule_id_rejected(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine, RuntimePolicyRejected

        with self.assertRaises(RuntimePolicyRejected):
            RuntimePolicyEngine().add_rule(self._rule(rule_id=""))

    def test_empty_target_rejected(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine, RuntimePolicyRejected

        with self.assertRaises(RuntimePolicyRejected):
            RuntimePolicyEngine().add_rule(self._rule(target=""))

    def test_empty_action_rejected(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine, RuntimePolicyRejected

        with self.assertRaises(RuntimePolicyRejected):
            RuntimePolicyEngine().add_rule(self._rule(action=""))

    def test_invalid_effect_rejected(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine, RuntimePolicyRejected

        with self.assertRaises(RuntimePolicyRejected):
            RuntimePolicyEngine().add_rule(self._rule(effect="audit"))

    def test_invalid_risk_level_rejected(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine, RuntimePolicyRejected

        with self.assertRaises(RuntimePolicyRejected):
            RuntimePolicyEngine().add_rule(self._rule(risk_level="severe"))

    def test_evaluate_default_allow_when_no_rule(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        decision = RuntimePolicyEngine().evaluate("runtime.execution", "start")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.risk_level, "low")
        self.assertEqual(decision.matched_rules, [])

    def test_deny_rule_blocks_action(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        engine = RuntimePolicyEngine()
        engine.add_rule(self._rule(effect="deny", risk_level="high"))

        decision = engine.evaluate("runtime.execution", "start")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.risk_level, "high")

    def test_require_confirmation_blocks_action(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        engine = RuntimePolicyEngine()
        engine.add_rule(
            self._rule(effect="require_confirmation", risk_level="medium")
        )

        decision = engine.evaluate("runtime.execution", "start")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.risk_level, "medium")

    def test_allow_rule_allows_action(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        engine = RuntimePolicyEngine()
        engine.add_rule(self._rule(effect="allow"))

        decision = engine.evaluate("runtime.execution", "start")

        self.assertTrue(decision.allowed)
        self.assertEqual(len(decision.matched_rules), 1)

    def test_deny_overrides_allow(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        engine = RuntimePolicyEngine()
        engine.add_rule(self._rule(rule_id="allow-1", effect="allow"))
        engine.add_rule(
            self._rule(rule_id="deny-1", effect="deny", risk_level="critical")
        )

        decision = engine.evaluate("runtime.execution", "start")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.risk_level, "critical")

    def test_require_confirmation_overrides_allow(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        engine = RuntimePolicyEngine()
        engine.add_rule(self._rule(rule_id="allow-1", effect="allow"))
        engine.add_rule(
            self._rule(
                rule_id="confirm-1",
                effect="require_confirmation",
                risk_level="medium",
            )
        )

        decision = engine.evaluate("runtime.execution", "start")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.risk_level, "medium")

    def test_violations_created_for_deny(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        engine = RuntimePolicyEngine()
        engine.add_rule(self._rule(effect="deny", risk_level="high"))

        decision = engine.evaluate("runtime.execution", "start")

        self.assertEqual(len(decision.violations), 1)
        self.assertEqual(decision.violations[0].rule_id, "rule-1")

    def test_violations_created_for_require_confirmation(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        engine = RuntimePolicyEngine()
        engine.add_rule(self._rule(effect="require_confirmation"))

        decision = engine.evaluate("runtime.execution", "start")

        self.assertEqual(len(decision.violations), 1)
        self.assertEqual(decision.violations[0].rule_id, "rule-1")

    def test_assert_allowed_returns_decision_when_allowed(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        decision = RuntimePolicyEngine().assert_allowed(
            "runtime.execution",
            "start",
        )

        self.assertTrue(decision.allowed)

    def test_assert_allowed_raises_when_denied(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine, RuntimePolicyRejected

        engine = RuntimePolicyEngine()
        engine.add_rule(self._rule(effect="deny"))

        with self.assertRaises(RuntimePolicyRejected):
            engine.assert_allowed("runtime.execution", "start")

    def test_runtime_policy_rejected_keeps_decision(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine, RuntimePolicyRejected

        engine = RuntimePolicyEngine()
        engine.add_rule(self._rule(effect="deny"))

        with self.assertRaises(RuntimePolicyRejected) as context:
            engine.assert_allowed("runtime.execution", "start")

        self.assertIsNotNone(context.exception.decision)
        self.assertFalse(context.exception.decision.allowed)

    def test_sequence_increments_globally(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        engine = RuntimePolicyEngine()
        first = engine.evaluate("runtime.execution", "start")
        second = engine.evaluate("runtime.replay", "run")

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_get_rules_returns_all_rules(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        engine = RuntimePolicyEngine()
        engine.add_rule(self._rule(rule_id="rule-1"))
        engine.add_rule(self._rule(rule_id="rule-2", action="stop"))

        self.assertEqual([rule.rule_id for rule in engine.get_rules()], ["rule-1", "rule-2"])

    def test_get_rules_filters_target(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        engine = RuntimePolicyEngine()
        engine.add_rule(self._rule(rule_id="rule-1", target="runtime.execution"))
        engine.add_rule(self._rule(rule_id="rule-2", target="runtime.replay"))

        self.assertEqual(
            [rule.rule_id for rule in engine.get_rules(target="runtime.replay")],
            ["rule-2"],
        )

    def test_get_rules_filters_action(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        engine = RuntimePolicyEngine()
        engine.add_rule(self._rule(rule_id="rule-1", action="start"))
        engine.add_rule(self._rule(rule_id="rule-2", action="stop"))

        self.assertEqual(
            [rule.rule_id for rule in engine.get_rules(action="stop")],
            ["rule-2"],
        )

    def test_get_rules_returns_copy(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        engine = RuntimePolicyEngine()
        engine.add_rule(self._rule(rule_id="rule-1"))
        rules = engine.get_rules()
        rules.clear()

        self.assertEqual(len(engine.get_rules()), 1)

    def test_get_decisions_returns_copy(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        engine = RuntimePolicyEngine()
        engine.evaluate("runtime.execution", "start")
        decisions = engine.get_decisions()
        decisions[0].matched_rules.clear()
        decisions.clear()

        self.assertEqual(len(engine.get_decisions()), 1)

    def test_payload_preserved(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        payload = {"session_id": "session-1"}

        decision = RuntimePolicyEngine().evaluate(
            "runtime.execution",
            "start",
            payload=payload,
        )

        self.assertIs(decision.payload, payload)

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        metadata = {"source": "contract", "attempt": 1}

        decision = RuntimePolicyEngine().evaluate(
            "runtime.execution",
            "start",
            metadata=metadata,
        )

        self.assertIs(decision.metadata, metadata)

    def test_payload_not_mutated(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        payload = {"items": [{"session_id": "session-1"}]}
        before = copy.deepcopy(payload)

        RuntimePolicyEngine().evaluate(
            "runtime.execution",
            "start",
            payload=payload,
        )

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        metadata = {"tags": ["contract"], "attempt": 1}
        before = copy.deepcopy(metadata)

        RuntimePolicyEngine().evaluate(
            "runtime.execution",
            "start",
            metadata=metadata,
        )

        self.assertEqual(metadata, before)

    def test_clear_resets_engine_and_sequence(self) -> None:
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine

        engine = RuntimePolicyEngine()
        engine.add_rule(self._rule(rule_id="rule-1"))
        engine.evaluate("runtime.execution", "start")
        engine.clear()
        decision = engine.evaluate("runtime.execution", "start")

        self.assertEqual(engine.get_rules(), [])
        self.assertEqual(len(engine.get_decisions()), 1)
        self.assertEqual(decision.sequence, 1)


if __name__ == "__main__":
    unittest.main()
