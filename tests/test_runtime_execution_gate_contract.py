from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeExecutionGateContractTest(unittest.TestCase):
    def _deny_gate(self):
        from core.runtime.runtime_execution_gate import RuntimeExecutionGate
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine, RuntimePolicyRule

        policy_engine = RuntimePolicyEngine()
        policy_engine.add_rule(
            RuntimePolicyRule(
                rule_id="deny-1",
                target="runtime.execution",
                action="start",
                effect="deny",
                risk_level="high",
                reason="blocked by contract",
            )
        )
        return RuntimeExecutionGate(policy_engine=policy_engine)

    def _confirmation_gate(self):
        from core.runtime.runtime_execution_gate import RuntimeExecutionGate
        from core.runtime.runtime_policy_engine import RuntimePolicyEngine, RuntimePolicyRule

        policy_engine = RuntimePolicyEngine()
        policy_engine.add_rule(
            RuntimePolicyRule(
                rule_id="confirm-1",
                target="runtime.recovery",
                action="run",
                effect="require_confirmation",
                risk_level="medium",
                reason="confirmation required",
            )
        )
        return RuntimeExecutionGate(policy_engine=policy_engine)

    def test_check_default_allow(self) -> None:
        from core.runtime.runtime_execution_gate import RuntimeExecutionGate

        result = RuntimeExecutionGate().check("runtime.execution", "start")

        self.assertTrue(result.allowed)
        self.assertTrue(result.decision.allowed)

    def test_check_deny_returns_allowed_false_without_raising(self) -> None:
        result = self._deny_gate().check("runtime.execution", "start")

        self.assertFalse(result.allowed)
        self.assertFalse(result.decision.allowed)

    def test_check_require_confirmation_returns_allowed_false_without_raising(self) -> None:
        result = self._confirmation_gate().check("runtime.recovery", "run")

        self.assertFalse(result.allowed)
        self.assertFalse(result.decision.allowed)

    def test_assert_open_default_allow_returns_result(self) -> None:
        from core.runtime.runtime_execution_gate import RuntimeExecutionGate

        result = RuntimeExecutionGate().assert_open("runtime.execution", "start")

        self.assertTrue(result.allowed)

    def test_assert_open_deny_raises_runtime_gate_rejected(self) -> None:
        from core.runtime.runtime_execution_gate import RuntimeGateRejected

        with self.assertRaises(RuntimeGateRejected):
            self._deny_gate().assert_open("runtime.execution", "start")

    def test_runtime_gate_rejected_keeps_decision(self) -> None:
        from core.runtime.runtime_execution_gate import RuntimeGateRejected

        with self.assertRaises(RuntimeGateRejected) as context:
            self._deny_gate().assert_open("runtime.execution", "start")

        self.assertIsNotNone(context.exception.decision)
        self.assertFalse(context.exception.decision.allowed)

    def test_runtime_gate_rejected_keeps_gate_result(self) -> None:
        from core.runtime.runtime_execution_gate import RuntimeGateRejected

        with self.assertRaises(RuntimeGateRejected) as context:
            self._deny_gate().assert_open("runtime.execution", "start")

        self.assertIsNotNone(context.exception.gate_result)
        self.assertFalse(context.exception.gate_result.allowed)

    def test_empty_target_rejected(self) -> None:
        from core.runtime.runtime_execution_gate import RuntimeExecutionGate, RuntimeGateRejected

        with self.assertRaises(RuntimeGateRejected):
            RuntimeExecutionGate().check("", "start")

    def test_empty_action_rejected(self) -> None:
        from core.runtime.runtime_execution_gate import RuntimeExecutionGate, RuntimeGateRejected

        with self.assertRaises(RuntimeGateRejected):
            RuntimeExecutionGate().check("runtime.execution", "")

    def test_sequence_increments_globally(self) -> None:
        from core.runtime.runtime_execution_gate import RuntimeExecutionGate

        gate = RuntimeExecutionGate()
        first = gate.check("runtime.execution", "start")
        second = gate.check("runtime.replay", "run")

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_get_results_returns_copy(self) -> None:
        from core.runtime.runtime_execution_gate import RuntimeExecutionGate

        gate = RuntimeExecutionGate()
        gate.check("runtime.execution", "start")
        results = gate.get_results()
        results.clear()

        self.assertEqual(len(gate.get_results()), 1)

    def test_payload_preserved(self) -> None:
        from core.runtime.runtime_execution_gate import RuntimeExecutionGate

        payload = {"session_id": "session-1"}

        result = RuntimeExecutionGate().check(
            "runtime.execution",
            "start",
            payload=payload,
        )

        self.assertIs(result.payload, payload)
        self.assertIs(result.decision.payload, payload)

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_execution_gate import RuntimeExecutionGate

        metadata = {"source": "contract", "attempt": 1}

        result = RuntimeExecutionGate().check(
            "runtime.execution",
            "start",
            metadata=metadata,
        )

        self.assertIs(result.metadata, metadata)
        self.assertIs(result.decision.metadata, metadata)

    def test_payload_not_mutated(self) -> None:
        from core.runtime.runtime_execution_gate import RuntimeExecutionGate

        payload = {"items": [{"session_id": "session-1"}]}
        before = copy.deepcopy(payload)

        RuntimeExecutionGate().check("runtime.execution", "start", payload=payload)

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        from core.runtime.runtime_execution_gate import RuntimeExecutionGate

        metadata = {"tags": ["contract"], "attempt": 1}
        before = copy.deepcopy(metadata)

        RuntimeExecutionGate().check(
            "runtime.execution",
            "start",
            metadata=metadata,
        )

        self.assertEqual(metadata, before)

    def test_clear_resets_gate_and_sequence(self) -> None:
        from core.runtime.runtime_execution_gate import RuntimeExecutionGate

        gate = RuntimeExecutionGate()
        gate.check("runtime.execution", "start")
        gate.clear()
        result = gate.check("runtime.replay", "run")

        self.assertEqual(result.sequence, 1)
        self.assertEqual(len(gate.get_results()), 1)

    def test_policy_exception_wraps_runtime_gate_rejected(self) -> None:
        from core.runtime.runtime_execution_gate import RuntimeExecutionGate, RuntimeGateRejected

        original = ValueError("boom")

        class FailingPolicyEngine:
            def evaluate(self, *_args, **_kwargs):
                raise original

        with self.assertRaises(RuntimeGateRejected) as context:
            RuntimeExecutionGate(policy_engine=FailingPolicyEngine()).check(
                "runtime.execution",
                "start",
            )

        self.assertIs(context.exception.original_exception, original)


if __name__ == "__main__":
    unittest.main()
