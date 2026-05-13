from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RecordingAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, object]] = []

    def _record(self, name, payload=None, metadata=None):
        self.calls.append((name, payload, metadata))
        return {"adapter_method": name, "payload": payload, "metadata": metadata}

    def mirror_scheduler_queue_transition(self, payload=None, metadata=None):
        return self._record(
            "mirror_scheduler_queue_transition",
            payload=payload,
            metadata=metadata,
        )

    def mirror_executor_result_write(self, payload=None, metadata=None):
        return self._record(
            "mirror_executor_result_write",
            payload=payload,
            metadata=metadata,
        )

    def mirror_orchestrator_dispatch(self, payload=None, metadata=None):
        return self._record(
            "mirror_orchestrator_dispatch",
            payload=payload,
            metadata=metadata,
        )

    def mirror_repair_incident(self, payload=None, metadata=None):
        return self._record(
            "mirror_repair_incident",
            payload=payload,
            metadata=metadata,
        )


class RuntimeHookControllerContractTest(unittest.TestCase):
    def _hook_cases(self):
        from core.runtime.runtime_hook_controller import RuntimeHookController

        return [
            (
                RuntimeHookController.before_queue_transition,
                "before_queue_transition",
                "scheduler",
                "before",
                "scheduler_queue_transition",
                "mirror_scheduler_queue_transition",
            ),
            (
                RuntimeHookController.after_queue_transition,
                "after_queue_transition",
                "scheduler",
                "after",
                "scheduler_queue_transition",
                "mirror_scheduler_queue_transition",
            ),
            (
                RuntimeHookController.before_execution_result_write,
                "before_execution_result_write",
                "step_executor",
                "before",
                "executor_result_write",
                "mirror_executor_result_write",
            ),
            (
                RuntimeHookController.after_execution_result_write,
                "after_execution_result_write",
                "step_executor",
                "after",
                "executor_result_write",
                "mirror_executor_result_write",
            ),
            (
                RuntimeHookController.before_orchestrator_dispatch,
                "before_orchestrator_dispatch",
                "orchestrator",
                "before",
                "orchestrator_dispatch",
                "mirror_orchestrator_dispatch",
            ),
            (
                RuntimeHookController.after_orchestrator_dispatch,
                "after_orchestrator_dispatch",
                "orchestrator",
                "after",
                "orchestrator_dispatch",
                "mirror_orchestrator_dispatch",
            ),
            (
                RuntimeHookController.before_repair_incident,
                "before_repair_incident",
                "repair_chain",
                "before",
                "repair_incident",
                "mirror_repair_incident",
            ),
            (
                RuntimeHookController.after_repair_incident,
                "after_repair_incident",
                "repair_chain",
                "after",
                "repair_incident",
                "mirror_repair_incident",
            ),
        ]

    def test_enabled_hook_calls_adapter(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        adapter = RecordingAdapter()
        result = RuntimeHookController(adapter=adapter).before_queue_transition()

        self.assertEqual(len(adapter.calls), 1)
        self.assertFalse(result.skipped)
        self.assertIsNotNone(result.adapter_result)

    def test_disabled_hook_skips_adapter(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        adapter = RecordingAdapter()
        result = RuntimeHookController(adapter=adapter, enabled=False).before_queue_transition()

        self.assertEqual(adapter.calls, [])
        self.assertTrue(result.skipped)
        self.assertIsNone(result.adapter_result)
        self.assertIn("hook disabled", result.reason or "")

    def test_set_enabled_false_disables_hooks(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        adapter = RecordingAdapter()
        controller = RuntimeHookController(adapter=adapter)
        controller.set_enabled(False)
        result = controller.before_queue_transition()

        self.assertFalse(controller.is_enabled())
        self.assertTrue(result.skipped)
        self.assertEqual(adapter.calls, [])

    def test_set_enabled_true_re_enables_hooks(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        adapter = RecordingAdapter()
        controller = RuntimeHookController(adapter=adapter, enabled=False)
        controller.set_enabled(True)
        result = controller.before_queue_transition()

        self.assertTrue(controller.is_enabled())
        self.assertFalse(result.skipped)
        self.assertEqual(len(adapter.calls), 1)

    def test_before_queue_transition_mirrors(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        result = RuntimeHookController().before_queue_transition()

        self.assertEqual(result.adapter_result.operation, "scheduler_queue_transition")

    def test_after_queue_transition_mirrors(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        result = RuntimeHookController().after_queue_transition()

        self.assertEqual(result.adapter_result.operation, "scheduler_queue_transition")

    def test_before_execution_result_write_mirrors(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        result = RuntimeHookController().before_execution_result_write()

        self.assertEqual(result.adapter_result.operation, "executor_result_write")

    def test_after_execution_result_write_mirrors(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        result = RuntimeHookController().after_execution_result_write()

        self.assertEqual(result.adapter_result.operation, "executor_result_write")

    def test_before_orchestrator_dispatch_mirrors(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        result = RuntimeHookController().before_orchestrator_dispatch()

        self.assertEqual(result.adapter_result.operation, "orchestrator_dispatch")

    def test_after_orchestrator_dispatch_mirrors(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        result = RuntimeHookController().after_orchestrator_dispatch()

        self.assertEqual(result.adapter_result.operation, "orchestrator_dispatch")

    def test_before_repair_incident_mirrors(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        result = RuntimeHookController().before_repair_incident()

        self.assertEqual(result.adapter_result.operation, "repair_incident")

    def test_after_repair_incident_mirrors(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        result = RuntimeHookController().after_repair_incident()

        self.assertEqual(result.adapter_result.operation, "repair_incident")

    def test_hook_result_contains_hook_name_source_phase(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        controller = RuntimeHookController()

        for method, hook_name, source, phase, _operation, _adapter_method in self._hook_cases():
            with self.subTest(hook_name=hook_name):
                result = method(controller)
                self.assertEqual(result.hook_name, hook_name)
                self.assertEqual(result.source, source)
                self.assertEqual(result.phase, phase)

    def test_hook_result_includes_adapter_result_when_enabled(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        result = RuntimeHookController().before_queue_transition()

        self.assertIsNotNone(result.adapter_result)
        self.assertFalse(result.skipped)

    def test_hook_result_skipped_true_when_disabled(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        result = RuntimeHookController(enabled=False).before_queue_transition()

        self.assertTrue(result.skipped)
        self.assertIsNone(result.adapter_result)

    def test_payload_preserved(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        payload = {"task_id": "task-1", "state": "queued"}

        result = RuntimeHookController().before_queue_transition(payload=payload)

        self.assertIs(result.payload, payload)
        self.assertIs(result.adapter_result.payload, payload)

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        metadata = {"source": "contract", "attempt": 1}

        result = RuntimeHookController().before_queue_transition(metadata=metadata)

        self.assertIs(result.metadata, metadata)
        self.assertIs(result.adapter_result.metadata, metadata)

    def test_payload_not_mutated(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        payload = {"items": [{"task_id": "task-1", "state": "queued"}]}
        before = copy.deepcopy(payload)

        RuntimeHookController().before_queue_transition(payload=payload)

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        metadata = {"tags": ["contract"], "attempt": 1}
        before = copy.deepcopy(metadata)

        RuntimeHookController().before_queue_transition(metadata=metadata)

        self.assertEqual(metadata, before)

    def test_adapter_exception_raises_runtime_hook_rejected(self) -> None:
        from core.runtime.runtime_hook_controller import (
            RuntimeHookController,
            RuntimeHookRejected,
        )

        original = ValueError("boom")

        class FailingAdapter(RecordingAdapter):
            def mirror_scheduler_queue_transition(self, payload=None, metadata=None):
                raise original

        with self.assertRaises(RuntimeHookRejected):
            RuntimeHookController(adapter=FailingAdapter()).before_queue_transition()

    def test_runtime_hook_rejected_keeps_original_exception(self) -> None:
        from core.runtime.runtime_hook_controller import (
            RuntimeHookController,
            RuntimeHookRejected,
        )

        original = ValueError("boom")

        class FailingAdapter(RecordingAdapter):
            def mirror_scheduler_queue_transition(self, payload=None, metadata=None):
                raise original

        with self.assertRaises(RuntimeHookRejected) as context:
            RuntimeHookController(adapter=FailingAdapter()).before_queue_transition()

        self.assertIs(context.exception.original_exception, original)

    def test_all_hooks_call_expected_adapter_method(self) -> None:
        from core.runtime.runtime_hook_controller import RuntimeHookController

        for method, hook_name, _source, _phase, _operation, adapter_method in self._hook_cases():
            with self.subTest(hook_name=hook_name):
                adapter = RecordingAdapter()
                method(RuntimeHookController(adapter=adapter))
                self.assertEqual(adapter.calls[0][0], adapter_method)


if __name__ == "__main__":
    unittest.main()
