from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeOperationRegistryContractTest(unittest.TestCase):
    def test_default_operations_exist(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        registry = RuntimeOperationRegistry()
        expected = {
            "lifecycle.queue",
            "lifecycle.dispatch",
            "lifecycle.start_execution",
            "lifecycle.complete_execution",
            "lifecycle.fail_execution",
            "replay.session",
            "recovery.create",
            "recovery.run",
            "recovery.verify",
            "mutation.write",
            "self_edit.apply",
        }

        self.assertTrue(all(registry.has(operation) for operation in expected))

    def test_default_lifecycle_queue_matches_intent_mapping(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        operation = RuntimeOperationRegistry().get("lifecycle.queue")

        self.assertEqual(operation.target, "lifecycle")
        self.assertEqual(operation.action, "queue")
        self.assertEqual(operation.category, "lifecycle")
        self.assertEqual(operation.risk_level, "low")
        self.assertEqual(operation.governance_target, "lifecycle")

    def test_default_recovery_run_matches_intent_mapping(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        operation = RuntimeOperationRegistry().get("recovery.run")

        self.assertEqual(operation.target, "recovery")
        self.assertEqual(operation.action, "run")
        self.assertEqual(operation.category, "recovery")
        self.assertEqual(operation.risk_level, "high")
        self.assertEqual(operation.governance_target, "recovery")

    def test_default_self_edit_apply_is_critical(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        operation = RuntimeOperationRegistry().get("self_edit.apply")

        self.assertEqual(operation.risk_level, "critical")

    def test_register_custom_operation(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        operation = RuntimeOperationRegistry().register(
            "custom.audit",
            "custom",
            "audit",
            "observability",
            "low",
            governance_target="audit",
            description="Audit custom runtime operation",
        )

        self.assertEqual(operation.operation, "custom.audit")
        self.assertEqual(operation.target, "custom")
        self.assertEqual(operation.action, "audit")
        self.assertEqual(operation.category, "observability")
        self.assertEqual(operation.governance_target, "audit")
        self.assertEqual(operation.description, "Audit custom runtime operation")

    def test_register_overrides_existing_operation(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        registry = RuntimeOperationRegistry()
        registry.register(
            "lifecycle.queue",
            "override",
            "queue_override",
            "override_category",
            "high",
            governance_target="override_governance",
        )

        operation = registry.get("lifecycle.queue")

        self.assertEqual(operation.target, "override")
        self.assertEqual(operation.action, "queue_override")
        self.assertEqual(operation.category, "override_category")
        self.assertEqual(operation.risk_level, "high")
        self.assertEqual(operation.governance_target, "override_governance")

    def test_sequence_increments_on_register(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        registry = RuntimeOperationRegistry()
        first = registry.register("custom.one", "custom", "one", "custom", "low")
        second = registry.register("custom.two", "custom", "two", "custom", "medium")

        self.assertEqual(second.sequence, first.sequence + 1)

    def test_empty_operation_rejected(self) -> None:
        from core.runtime.runtime_operation_registry import (
            RuntimeOperationRegistry,
            RuntimeOperationRejected,
        )

        with self.assertRaises(RuntimeOperationRejected):
            RuntimeOperationRegistry().register("", "custom", "audit", "custom", "low")

    def test_empty_target_action_category_rejected(self) -> None:
        from core.runtime.runtime_operation_registry import (
            RuntimeOperationRegistry,
            RuntimeOperationRejected,
        )

        registry = RuntimeOperationRegistry()
        with self.assertRaises(RuntimeOperationRejected):
            registry.register("custom.target", "", "audit", "custom", "low")
        with self.assertRaises(RuntimeOperationRejected):
            registry.register("custom.action", "custom", "", "custom", "low")
        with self.assertRaises(RuntimeOperationRejected):
            registry.register("custom.category", "custom", "audit", "", "low")

    def test_invalid_risk_level_rejected(self) -> None:
        from core.runtime.runtime_operation_registry import (
            RuntimeOperationRegistry,
            RuntimeOperationRejected,
        )

        with self.assertRaises(RuntimeOperationRejected):
            RuntimeOperationRegistry().register(
                "custom.audit",
                "custom",
                "audit",
                "custom",
                "severe",
            )

    def test_governance_target_defaults_to_target(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        operation = RuntimeOperationRegistry().register(
            "custom.audit",
            "custom",
            "audit",
            "custom",
            "low",
        )

        self.assertEqual(operation.governance_target, "custom")

    def test_get_unknown_rejected(self) -> None:
        from core.runtime.runtime_operation_registry import (
            RuntimeOperationRegistry,
            RuntimeOperationRejected,
        )

        with self.assertRaises(RuntimeOperationRejected):
            RuntimeOperationRegistry().get("unknown.operation")

    def test_has_returns_true_false(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        registry = RuntimeOperationRegistry()

        self.assertTrue(registry.has("lifecycle.queue"))
        self.assertFalse(registry.has("unknown.operation"))

    def test_unregister_custom_operation(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        registry = RuntimeOperationRegistry()
        registry.register("custom.audit", "custom", "audit", "custom", "low")
        registry.unregister("custom.audit")

        self.assertFalse(registry.has("custom.audit"))

    def test_unregister_unknown_rejected(self) -> None:
        from core.runtime.runtime_operation_registry import (
            RuntimeOperationRegistry,
            RuntimeOperationRejected,
        )

        with self.assertRaises(RuntimeOperationRejected):
            RuntimeOperationRegistry().unregister("unknown.operation")

    def test_unregister_default_operation_rejected(self) -> None:
        from core.runtime.runtime_operation_registry import (
            RuntimeOperationRegistry,
            RuntimeOperationRejected,
        )

        with self.assertRaises(RuntimeOperationRejected):
            RuntimeOperationRegistry().unregister("lifecycle.queue")

    def test_clear_custom_keeps_defaults(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        registry = RuntimeOperationRegistry()
        registry.register("custom.audit", "custom", "audit", "custom", "low")
        registry.clear_custom()

        self.assertFalse(registry.has("custom.audit"))
        self.assertTrue(registry.has("lifecycle.queue"))
        self.assertTrue(registry.has("self_edit.apply"))

    def test_list_operations_returns_all_operations(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        operations = RuntimeOperationRegistry().list_operations()

        self.assertEqual(len(operations), 11)

    def test_list_operations_filters_category(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        operations = RuntimeOperationRegistry().list_operations(category="recovery")

        self.assertEqual(
            [operation.operation for operation in operations],
            ["recovery.create", "recovery.run", "recovery.verify"],
        )

    def test_list_operations_filters_governance_target(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        operations = RuntimeOperationRegistry().list_operations(
            governance_target="lifecycle"
        )

        self.assertEqual(
            [operation.operation for operation in operations],
            [
                "lifecycle.queue",
                "lifecycle.dispatch",
                "lifecycle.start_execution",
                "lifecycle.complete_execution",
                "lifecycle.fail_execution",
            ],
        )

    def test_list_operations_filters_risk_level(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        operations = RuntimeOperationRegistry().list_operations(risk_level="critical")

        self.assertEqual(
            [operation.operation for operation in operations],
            ["self_edit.apply"],
        )

    def test_list_operations_returns_copy(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        registry = RuntimeOperationRegistry()
        operations = registry.list_operations()
        operations.clear()

        self.assertEqual(len(registry.list_operations()), 11)

    def test_get_returns_copy(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        registry = RuntimeOperationRegistry()
        operation = registry.get("lifecycle.queue")
        object.__setattr__(operation, "target", "polluted")

        self.assertEqual(registry.get("lifecycle.queue").target, "lifecycle")

    def test_get_all_mappings_returns_copy(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        registry = RuntimeOperationRegistry()
        mappings = registry.get_all_mappings()
        mappings["lifecycle.queue"]["target"] = "polluted"
        mappings.clear()

        self.assertEqual(
            registry.get_all_mappings()["lifecycle.queue"]["target"],
            "lifecycle",
        )

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        metadata = {"source": "contract", "tags": ["runtime"]}

        operation = RuntimeOperationRegistry().register(
            "custom.audit",
            "custom",
            "audit",
            "custom",
            "low",
            metadata=metadata,
        )

        self.assertIs(operation.metadata, metadata)

    def test_metadata_not_mutated(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        metadata = {"source": "contract", "tags": ["runtime"]}
        before = copy.deepcopy(metadata)

        RuntimeOperationRegistry().register(
            "custom.audit",
            "custom",
            "audit",
            "custom",
            "low",
            metadata=metadata,
        )

        self.assertEqual(metadata, before)

    def test_description_defaults_to_empty_string(self) -> None:
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        operation = RuntimeOperationRegistry().register(
            "custom.audit",
            "custom",
            "audit",
            "custom",
            "low",
        )

        self.assertEqual(operation.description, "")


if __name__ == "__main__":
    unittest.main()
