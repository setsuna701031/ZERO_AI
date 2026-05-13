from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeIntentClassifierContractTest(unittest.TestCase):
    def _assert_intent(
        self,
        operation: str,
        target: str,
        action: str,
        category: str,
        risk_level: str,
        governance_target: str,
    ) -> None:
        from core.runtime.runtime_intent_classifier import RuntimeIntentClassifier

        intent = RuntimeIntentClassifier().classify(operation)

        self.assertEqual(intent.operation, operation)
        self.assertEqual(intent.target, target)
        self.assertEqual(intent.action, action)
        self.assertEqual(intent.category, category)
        self.assertEqual(intent.risk_level, risk_level)
        self.assertEqual(intent.governance_target, governance_target)

    def test_default_lifecycle_queue_classification(self) -> None:
        self._assert_intent(
            "lifecycle.queue",
            "lifecycle",
            "queue",
            "lifecycle",
            "low",
            "lifecycle",
        )

    def test_default_lifecycle_dispatch_classification(self) -> None:
        self._assert_intent(
            "lifecycle.dispatch",
            "lifecycle",
            "dispatch",
            "lifecycle",
            "low",
            "lifecycle",
        )

    def test_default_lifecycle_start_execution_classification(self) -> None:
        self._assert_intent(
            "lifecycle.start_execution",
            "lifecycle",
            "start_execution",
            "execution",
            "medium",
            "lifecycle",
        )

    def test_default_replay_session_classification(self) -> None:
        self._assert_intent(
            "replay.session",
            "replay",
            "session",
            "replay",
            "medium",
            "replay",
        )

    def test_default_recovery_create_classification(self) -> None:
        self._assert_intent(
            "recovery.create",
            "recovery",
            "create",
            "recovery",
            "high",
            "recovery",
        )

    def test_default_recovery_run_classification(self) -> None:
        self._assert_intent(
            "recovery.run",
            "recovery",
            "run",
            "recovery",
            "high",
            "recovery",
        )

    def test_default_recovery_verify_classification(self) -> None:
        self._assert_intent(
            "recovery.verify",
            "recovery",
            "verify",
            "recovery",
            "medium",
            "recovery",
        )

    def test_default_mutation_write_classification(self) -> None:
        self._assert_intent(
            "mutation.write",
            "mutation",
            "write",
            "mutation",
            "high",
            "mutation",
        )

    def test_default_self_edit_apply_classification(self) -> None:
        self._assert_intent(
            "self_edit.apply",
            "self_edit",
            "apply",
            "self_edit",
            "critical",
            "self_edit",
        )

    def test_unknown_operation_rejected(self) -> None:
        from core.runtime.runtime_intent_classifier import (
            RuntimeIntentClassifier,
            RuntimeIntentRejected,
        )

        with self.assertRaises(RuntimeIntentRejected):
            RuntimeIntentClassifier().classify("unknown.operation")

    def test_empty_operation_rejected(self) -> None:
        from core.runtime.runtime_intent_classifier import (
            RuntimeIntentClassifier,
            RuntimeIntentRejected,
        )

        with self.assertRaises(RuntimeIntentRejected):
            RuntimeIntentClassifier().classify("")

    def test_register_custom_mapping(self) -> None:
        from core.runtime.runtime_intent_classifier import RuntimeIntentClassifier

        classifier = RuntimeIntentClassifier()
        classifier.register_mapping(
            "custom.audit",
            "custom",
            "audit",
            "observability",
            "low",
            "audit",
        )

        intent = classifier.classify("custom.audit")

        self.assertEqual(intent.target, "custom")
        self.assertEqual(intent.action, "audit")
        self.assertEqual(intent.category, "observability")
        self.assertEqual(intent.risk_level, "low")
        self.assertEqual(intent.governance_target, "audit")

    def test_register_mapping_overrides_existing_operation(self) -> None:
        from core.runtime.runtime_intent_classifier import RuntimeIntentClassifier

        classifier = RuntimeIntentClassifier()
        classifier.register_mapping(
            "lifecycle.queue",
            "override",
            "queue_override",
            "override_category",
            "high",
            "override_governance",
        )

        intent = classifier.classify("lifecycle.queue")

        self.assertEqual(intent.target, "override")
        self.assertEqual(intent.action, "queue_override")
        self.assertEqual(intent.category, "override_category")
        self.assertEqual(intent.risk_level, "high")
        self.assertEqual(intent.governance_target, "override_governance")

    def test_invalid_risk_level_rejected(self) -> None:
        from core.runtime.runtime_intent_classifier import (
            RuntimeIntentClassifier,
            RuntimeIntentRejected,
        )

        with self.assertRaises(RuntimeIntentRejected):
            RuntimeIntentClassifier().register_mapping(
                "custom.audit",
                "custom",
                "audit",
                "observability",
                "severe",
            )

    def test_empty_target_action_category_rejected(self) -> None:
        from core.runtime.runtime_intent_classifier import (
            RuntimeIntentClassifier,
            RuntimeIntentRejected,
        )

        classifier = RuntimeIntentClassifier()
        with self.assertRaises(RuntimeIntentRejected):
            classifier.register_mapping("custom.target", "", "audit", "category", "low")
        with self.assertRaises(RuntimeIntentRejected):
            classifier.register_mapping("custom.action", "custom", "", "category", "low")
        with self.assertRaises(RuntimeIntentRejected):
            classifier.register_mapping("custom.category", "custom", "audit", "", "low")

    def test_governance_target_defaults_to_target(self) -> None:
        from core.runtime.runtime_intent_classifier import RuntimeIntentClassifier

        classifier = RuntimeIntentClassifier()
        classifier.register_mapping(
            "custom.audit",
            "custom",
            "audit",
            "observability",
            "low",
        )

        self.assertEqual(classifier.classify("custom.audit").governance_target, "custom")

    def test_sequence_increments_globally(self) -> None:
        from core.runtime.runtime_intent_classifier import RuntimeIntentClassifier

        classifier = RuntimeIntentClassifier()
        first = classifier.classify("lifecycle.queue")
        second = classifier.classify("replay.session")

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_intent_id_is_stable(self) -> None:
        from core.runtime.runtime_intent_classifier import RuntimeIntentClassifier

        intent = RuntimeIntentClassifier().classify("lifecycle.queue")

        self.assertEqual(intent.intent_id, "intent:1:lifecycle.queue")

    def test_payload_preserved(self) -> None:
        from core.runtime.runtime_intent_classifier import RuntimeIntentClassifier

        payload = {"session_id": "session-1"}

        intent = RuntimeIntentClassifier().classify("lifecycle.queue", payload=payload)

        self.assertIs(intent.payload, payload)

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_intent_classifier import RuntimeIntentClassifier

        metadata = {"source": "contract", "attempt": 1}

        intent = RuntimeIntentClassifier().classify(
            "lifecycle.queue",
            metadata=metadata,
        )

        self.assertIs(intent.metadata, metadata)

    def test_payload_not_mutated(self) -> None:
        from core.runtime.runtime_intent_classifier import RuntimeIntentClassifier

        payload = {"items": [{"session_id": "session-1"}]}
        before = copy.deepcopy(payload)

        RuntimeIntentClassifier().classify("lifecycle.queue", payload=payload)

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        from core.runtime.runtime_intent_classifier import RuntimeIntentClassifier

        metadata = {"tags": ["contract"], "attempt": 1}
        before = copy.deepcopy(metadata)

        RuntimeIntentClassifier().classify("lifecycle.queue", metadata=metadata)

        self.assertEqual(metadata, before)

    def test_get_mappings_returns_copy(self) -> None:
        from core.runtime.runtime_intent_classifier import RuntimeIntentClassifier

        classifier = RuntimeIntentClassifier()
        mappings = classifier.get_mappings()
        mappings["lifecycle.queue"]["target"] = "polluted"
        mappings.clear()

        self.assertEqual(
            classifier.get_mappings()["lifecycle.queue"]["target"],
            "lifecycle",
        )

    def test_get_intents_returns_copy(self) -> None:
        from core.runtime.runtime_intent_classifier import RuntimeIntentClassifier

        classifier = RuntimeIntentClassifier()
        classifier.classify("lifecycle.queue")
        intents = classifier.get_intents()
        intents.clear()

        self.assertEqual(len(classifier.get_intents()), 1)

    def test_clear_intents_resets_intents_and_sequence_but_keeps_mappings(self) -> None:
        from core.runtime.runtime_intent_classifier import RuntimeIntentClassifier

        classifier = RuntimeIntentClassifier()
        classifier.register_mapping("custom.audit", "custom", "audit", "custom", "low")
        classifier.classify("lifecycle.queue")
        classifier.clear_intents()
        intent = classifier.classify("custom.audit")

        self.assertEqual(len(classifier.get_intents()), 1)
        self.assertEqual(intent.sequence, 1)
        self.assertIn("custom.audit", classifier.get_mappings())


if __name__ == "__main__":
    unittest.main()
