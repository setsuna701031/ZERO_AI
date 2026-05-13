from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeLifecyclePipelineContractTest(unittest.TestCase):
    def _started_pipeline(self):
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline

        pipeline = RuntimeLifecyclePipeline()
        pipeline.queue("life-1")
        pipeline.dispatch("life-1")
        pipeline.start_execution("life-1")
        return pipeline

    def test_queued_starts_lifecycle(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline

        record = RuntimeLifecyclePipeline().queue("life-1")

        self.assertEqual(record.lifecycle_id, "life-1")
        self.assertEqual(record.phase, "queued")
        self.assertEqual(record.sequence, 1)

    def test_dispatch_requires_queued(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import (
            RuntimeLifecyclePipeline,
            RuntimeLifecycleRejected,
        )

        with self.assertRaises(RuntimeLifecycleRejected):
            RuntimeLifecyclePipeline().dispatch("life-1")

    def test_execution_requires_dispatch(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import (
            RuntimeLifecyclePipeline,
            RuntimeLifecycleRejected,
        )

        pipeline = RuntimeLifecyclePipeline()
        pipeline.queue("life-1")

        with self.assertRaises(RuntimeLifecycleRejected):
            pipeline.start_execution("life-1")

    def test_completed_requires_executing(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import (
            RuntimeLifecyclePipeline,
            RuntimeLifecycleRejected,
        )

        pipeline = RuntimeLifecyclePipeline()
        pipeline.queue("life-1")
        pipeline.dispatch("life-1")

        with self.assertRaises(RuntimeLifecycleRejected):
            pipeline.complete_execution("life-1")

    def test_failed_requires_executing(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import (
            RuntimeLifecyclePipeline,
            RuntimeLifecycleRejected,
        )

        pipeline = RuntimeLifecyclePipeline()
        pipeline.queue("life-1")
        pipeline.dispatch("life-1")

        with self.assertRaises(RuntimeLifecycleRejected):
            pipeline.fail_execution("life-1")

    def test_incident_requires_failed(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecycleRejected

        pipeline = self._started_pipeline()
        pipeline.complete_execution("life-1")

        with self.assertRaises(RuntimeLifecycleRejected):
            pipeline.incident("life-1")

    def test_repair_requires_incident(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecycleRejected

        pipeline = self._started_pipeline()
        pipeline.fail_execution("life-1")

        with self.assertRaises(RuntimeLifecycleRejected):
            pipeline.repair("life-1")

    def test_replay_requires_completed_or_repaired(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecycleRejected

        completed = self._started_pipeline()
        completed.complete_execution("life-1")
        completed_replay = completed.replay("life-1")

        repaired = self._started_pipeline()
        repaired.fail_execution("life-1")
        repaired.incident("life-1")
        repaired.repair("life-1")
        repaired_replay = repaired.replay("life-1")

        blocked = self._started_pipeline()
        with self.assertRaises(RuntimeLifecycleRejected):
            blocked.replay("life-1")

        self.assertEqual(completed_replay.phase, "replayed")
        self.assertEqual(repaired_replay.phase, "replayed")

    def test_completed_lifecycle_cannot_fail(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecycleRejected

        pipeline = self._started_pipeline()
        pipeline.complete_execution("life-1")

        with self.assertRaises(RuntimeLifecycleRejected):
            pipeline.fail_execution("life-1")

    def test_failed_lifecycle_cannot_replay_before_repair(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecycleRejected

        pipeline = self._started_pipeline()
        pipeline.fail_execution("life-1")

        with self.assertRaises(RuntimeLifecycleRejected):
            pipeline.replay("life-1")

    def test_empty_lifecycle_id_rejected(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import (
            RuntimeLifecyclePipeline,
            RuntimeLifecycleRejected,
        )

        with self.assertRaises(RuntimeLifecycleRejected):
            RuntimeLifecyclePipeline().queue("")

    def test_sequence_increments_globally(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline

        pipeline = RuntimeLifecyclePipeline()
        first = pipeline.queue("life-1")
        second = pipeline.queue("life-2")
        third = pipeline.dispatch("life-1")

        self.assertEqual([first.sequence, second.sequence, third.sequence], [1, 2, 3])

    def test_get_records_returns_all_records(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline

        pipeline = RuntimeLifecyclePipeline()
        first = pipeline.queue("life-1")
        second = pipeline.queue("life-2")

        self.assertEqual(pipeline.get_records(), [first, second])

    def test_get_records_filters_lifecycle_id(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline

        pipeline = RuntimeLifecyclePipeline()
        first = pipeline.queue("life-1")
        pipeline.queue("life-2")

        self.assertEqual(pipeline.get_records("life-1"), [first])

    def test_get_records_returns_copy(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline

        pipeline = RuntimeLifecyclePipeline()
        pipeline.queue("life-1")
        records = pipeline.get_records()
        records.clear()

        self.assertEqual(len(pipeline.get_records()), 1)

    def test_replay_records_returns_records_in_sequence_order(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline

        pipeline = RuntimeLifecyclePipeline()
        pipeline.queue("life-1")
        pipeline.queue("life-2")
        pipeline.dispatch("life-1")

        self.assertEqual(
            [record.sequence for record in pipeline.replay_records()],
            [1, 2, 3],
        )

    def test_replay_records_handler_receives_records_in_sequence_order(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline

        received = []
        pipeline = RuntimeLifecyclePipeline()
        pipeline.queue("life-1")
        pipeline.queue("life-2")
        pipeline.dispatch("life-1")

        pipeline.replay_records(handler=lambda record: received.append(record.sequence))

        self.assertEqual(received, [1, 2, 3])

    def test_replay_handler_exception_raises_runtime_lifecycle_rejected(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import (
            RuntimeLifecyclePipeline,
            RuntimeLifecycleRejected,
        )

        original = ValueError("boom")

        def fail(_record) -> None:
            raise original

        pipeline = RuntimeLifecyclePipeline()
        pipeline.queue("life-1")

        with self.assertRaises(RuntimeLifecycleRejected) as context:
            pipeline.replay_records(handler=fail)

        self.assertIs(context.exception.original_exception, original)

    def test_payload_preserved(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline

        payload = {"task_id": "task-1", "state": "queued"}

        record = RuntimeLifecyclePipeline().queue("life-1", payload=payload)

        self.assertIs(record.payload, payload)

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline

        metadata = {"source": "contract", "attempt": 1}

        record = RuntimeLifecyclePipeline().queue("life-1", metadata=metadata)

        self.assertIs(record.metadata, metadata)

    def test_payload_not_mutated(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline

        payload = {"items": [{"task_id": "task-1", "state": "queued"}]}
        before = copy.deepcopy(payload)

        RuntimeLifecyclePipeline().queue("life-1", payload=payload)

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline

        metadata = {"tags": ["contract"], "attempt": 1}
        before = copy.deepcopy(metadata)

        RuntimeLifecyclePipeline().queue("life-1", metadata=metadata)

        self.assertEqual(metadata, before)

    def test_clear_resets_records_and_sequence(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline

        pipeline = RuntimeLifecyclePipeline()
        pipeline.queue("life-1")
        pipeline.clear()
        record = pipeline.queue("life-2")

        self.assertEqual(pipeline.get_records(), [record])
        self.assertEqual(record.sequence, 1)

    def test_hook_exception_raises_runtime_lifecycle_rejected(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import (
            RuntimeLifecyclePipeline,
            RuntimeLifecycleRejected,
        )

        original = ValueError("boom")

        class FailingHookController:
            def after_queue_transition(self, payload=None, metadata=None):
                raise original

        with self.assertRaises(RuntimeLifecycleRejected) as context:
            RuntimeLifecyclePipeline(
                hook_controller=FailingHookController()
            ).queue("life-1")

        self.assertIs(context.exception.original_exception, original)

    def test_lifecycle_record_includes_adapter_result(self) -> None:
        from core.runtime.runtime_lifecycle_pipeline import RuntimeLifecyclePipeline

        record = RuntimeLifecyclePipeline().queue("life-1")

        self.assertIsNotNone(record.adapter_result)
        self.assertEqual(record.adapter_result.operation, "scheduler_queue_transition")


if __name__ == "__main__":
    unittest.main()
