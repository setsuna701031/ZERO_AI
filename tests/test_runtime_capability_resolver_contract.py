from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeCapabilityResolverContractTest(unittest.TestCase):
    def test_resolve_default_lifecycle_queue(self) -> None:
        from core.runtime.runtime_capability_resolver import RuntimeCapabilityResolver

        capability = RuntimeCapabilityResolver().resolve("lifecycle.queue")

        self.assertEqual(capability.operation, "lifecycle.queue")
        self.assertEqual(capability.target, "lifecycle")
        self.assertEqual(capability.action, "queue")
        self.assertEqual(capability.category, "lifecycle")
        self.assertEqual(capability.risk_level, "low")
        self.assertEqual(capability.governance_target, "lifecycle")

    def test_resolve_default_recovery_run(self) -> None:
        from core.runtime.runtime_capability_resolver import RuntimeCapabilityResolver

        capability = RuntimeCapabilityResolver().resolve("recovery.run")

        self.assertEqual(capability.operation, "recovery.run")
        self.assertEqual(capability.target, "recovery")
        self.assertEqual(capability.action, "run")
        self.assertEqual(capability.category, "recovery")
        self.assertEqual(capability.risk_level, "high")
        self.assertEqual(capability.governance_target, "recovery")

    def test_resolve_self_edit_apply_critical(self) -> None:
        from core.runtime.runtime_capability_resolver import RuntimeCapabilityResolver

        capability = RuntimeCapabilityResolver().resolve("self_edit.apply")

        self.assertEqual(capability.risk_level, "critical")

    def test_empty_operation_rejected(self) -> None:
        from core.runtime.runtime_capability_resolver import (
            RuntimeCapabilityRejected,
            RuntimeCapabilityResolver,
        )

        with self.assertRaises(RuntimeCapabilityRejected):
            RuntimeCapabilityResolver().resolve("")

    def test_unknown_operation_rejected(self) -> None:
        from core.runtime.runtime_capability_resolver import (
            RuntimeCapabilityRejected,
            RuntimeCapabilityResolver,
        )

        with self.assertRaises(RuntimeCapabilityRejected) as context:
            RuntimeCapabilityResolver().resolve("unknown.operation")

        self.assertIsNotNone(context.exception.original_exception)

    def test_capability_id_stable(self) -> None:
        from core.runtime.runtime_capability_resolver import RuntimeCapabilityResolver

        capability = RuntimeCapabilityResolver().resolve("lifecycle.queue")

        self.assertEqual(capability.capability_id, "capability:1:lifecycle.queue")

    def test_dispatch_target_defaults_to_operation_target(self) -> None:
        from core.runtime.runtime_capability_resolver import RuntimeCapabilityResolver

        capability = RuntimeCapabilityResolver().resolve("recovery.run")

        self.assertEqual(capability.dispatch_target, capability.target)

    def test_dispatch_action_defaults_to_operation_action(self) -> None:
        from core.runtime.runtime_capability_resolver import RuntimeCapabilityResolver

        capability = RuntimeCapabilityResolver().resolve("recovery.run")

        self.assertEqual(capability.dispatch_action, capability.action)

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_capability_resolver import RuntimeCapabilityResolver
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        metadata = {"source": "contract", "tags": ["runtime"]}
        registry = RuntimeOperationRegistry()
        registry.register(
            "custom.audit",
            "custom",
            "audit",
            "custom",
            "low",
            metadata=metadata,
        )

        capability = RuntimeCapabilityResolver(registry=registry).resolve(
            "custom.audit"
        )

        self.assertEqual(capability.metadata, metadata)
        self.assertIsNot(capability.metadata, metadata)

    def test_metadata_copy_protected(self) -> None:
        from core.runtime.runtime_capability_resolver import RuntimeCapabilityResolver
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        registry = RuntimeOperationRegistry()
        registry.register(
            "custom.audit",
            "custom",
            "audit",
            "custom",
            "low",
            metadata={"tags": ["runtime"]},
        )
        resolver = RuntimeCapabilityResolver(registry=registry)
        capability = resolver.resolve("custom.audit")
        capability.metadata["tags"].append("polluted")

        self.assertEqual(
            resolver.get_resolved()[0].metadata,
            {"tags": ["runtime"]},
        )

    def test_sequence_increments_globally(self) -> None:
        from core.runtime.runtime_capability_resolver import RuntimeCapabilityResolver

        resolver = RuntimeCapabilityResolver()
        first = resolver.resolve("lifecycle.queue")
        second = resolver.resolve("recovery.run")

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_resolve_many_preserves_input_order(self) -> None:
        from core.runtime.runtime_capability_resolver import RuntimeCapabilityResolver

        capabilities = RuntimeCapabilityResolver().resolve_many(
            ["recovery.run", "lifecycle.queue", "self_edit.apply"]
        )

        self.assertEqual(
            [capability.operation for capability in capabilities],
            ["recovery.run", "lifecycle.queue", "self_edit.apply"],
        )

    def test_resolve_many_rejects_if_any_operation_invalid(self) -> None:
        from core.runtime.runtime_capability_resolver import (
            RuntimeCapabilityRejected,
            RuntimeCapabilityResolver,
        )

        with self.assertRaises(RuntimeCapabilityRejected) as context:
            RuntimeCapabilityResolver().resolve_many(
                ["lifecycle.queue", "unknown.operation"]
            )

        self.assertIsNotNone(context.exception.original_exception)

    def test_get_resolved_returns_copy(self) -> None:
        from core.runtime.runtime_capability_resolver import RuntimeCapabilityResolver

        resolver = RuntimeCapabilityResolver()
        resolver.resolve("lifecycle.queue")
        resolved = resolver.get_resolved()
        object.__setattr__(resolved[0], "target", "polluted")
        resolved.clear()

        current = resolver.get_resolved()
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].target, "lifecycle")

    def test_clear_resets_resolved_and_sequence_but_keeps_registry(self) -> None:
        from core.runtime.runtime_capability_resolver import RuntimeCapabilityResolver
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        registry = RuntimeOperationRegistry()
        registry.register("custom.audit", "custom", "audit", "custom", "low")
        resolver = RuntimeCapabilityResolver(registry=registry)
        resolver.resolve("lifecycle.queue")
        resolver.clear()
        capability = resolver.resolve("custom.audit")

        self.assertEqual(len(resolver.get_resolved()), 1)
        self.assertEqual(capability.sequence, 1)
        self.assertEqual(capability.operation, "custom.audit")

    def test_injected_registry_is_used(self) -> None:
        from core.runtime.runtime_capability_resolver import RuntimeCapabilityResolver
        from core.runtime.runtime_operation_registry import RuntimeOperationRegistry

        registry = RuntimeOperationRegistry()
        registry.register(
            "custom.audit",
            "custom",
            "audit",
            "custom",
            "low",
        )

        capability = RuntimeCapabilityResolver(registry=registry).resolve(
            "custom.audit"
        )

        self.assertEqual(capability.operation, "custom.audit")

    def test_registry_exception_wraps_runtime_capability_rejected(self) -> None:
        from core.runtime.runtime_capability_resolver import (
            RuntimeCapabilityRejected,
            RuntimeCapabilityResolver,
        )

        original = ValueError("boom")

        class FailingRegistry:
            def get(self, _operation):
                raise original

        with self.assertRaises(RuntimeCapabilityRejected) as context:
            RuntimeCapabilityResolver(registry=FailingRegistry()).resolve(
                "lifecycle.queue"
            )

        self.assertIs(context.exception.original_exception, original)


if __name__ == "__main__":
    unittest.main()
