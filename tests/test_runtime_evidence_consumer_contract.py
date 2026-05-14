from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEvidenceConsumerContractTest(unittest.TestCase):
    def _seal(self, seal_id: str = "consumer-contract"):
        from core.runtime.runtime_mainline_evidence_seal import build_runtime_mainline_evidence_seal

        return build_runtime_mainline_evidence_seal(
            workspace_root="workspace",
            seal_id=seal_id,
        )

    def _consumer(self):
        from core.runtime.runtime_evidence_consumer import RuntimeEvidenceConsumer

        return RuntimeEvidenceConsumer()

    def test_sealed_evidence_can_be_read(self) -> None:
        seal = self._seal()
        summary = self._consumer().read_seal(seal)

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["schema"], "zero.runtime_evidence.consumer_summary.v1")
        self.assertEqual(summary["record_count"], 5)
        self.assertEqual(summary["missing_records"], [])
        self.assertEqual(summary["aggregate_status"], "succeeded")
        self.assertEqual(
            summary["present_records"],
            ["snapshot", "replay", "audit", "rollback", "bundle"],
        )
        self.assertEqual(
            [item["type"] for item in summary["emission_order"]],
            ["snapshot", "replay", "audit", "rollback", "bundle"],
        )
        self.assertTrue(summary["can_replay"])
        self.assertTrue(summary["can_audit"])
        self.assertTrue(summary["can_rollback"])

    def test_missing_and_empty_evidence_is_safe(self) -> None:
        consumer = self._consumer()

        empty = consumer.read_records({})
        missing = consumer.read_seal(None)
        partial = consumer.read_records({"snapshot": self._seal().evidence_records["snapshot"]})

        self.assertFalse(empty["ok"])
        self.assertEqual(empty["record_count"], 0)
        self.assertEqual(
            empty["missing_records"],
            ["snapshot", "replay", "audit", "rollback", "bundle"],
        )
        self.assertFalse(missing["ok"])
        self.assertFalse(partial["ok"])
        self.assertEqual(partial["record_count"], 1)
        self.assertEqual(
            partial["missing_records"],
            ["replay", "audit", "rollback", "bundle"],
        )
        self.assertFalse(partial["can_replay"])
        self.assertFalse(partial["can_audit"])
        self.assertFalse(partial["can_rollback"])

    def test_consumer_output_is_deterministic(self) -> None:
        consumer = self._consumer()
        first = consumer.read_seal(self._seal("deterministic-consumer"))
        second = consumer.read_seal(self._seal("deterministic-consumer"))

        self.assertEqual(first, second)
        self.assertEqual(first["summary_fingerprint"], second["summary_fingerprint"])

    def test_consumer_does_not_mutate_source_records(self) -> None:
        seal = self._seal("mutation-isolation")
        consumer = self._consumer()
        before = consumer.read_seal(seal)
        records = seal.evidence_records

        records["bundle"]._metadata = {"polluted": True}
        records["snapshot"]._metadata = {"polluted": True}
        mutable_summary = consumer.read_seal(seal)
        mutable_summary["record_refs"]["bundle_id"] = "polluted"
        mutable_summary["events"]["step_executor"]["phases"].append("polluted")

        after = consumer.read_seal(seal)

        self.assertEqual(after, before)
        self.assertNotEqual(after["record_refs"]["bundle_id"], "polluted")
        self.assertNotIn("polluted", after["events"]["step_executor"]["phases"])

    def test_event_payloads_are_consumed_read_only(self) -> None:
        seal = self._seal("event-consumer")
        seal.scheduler_boundary.on_task_enqueued(
            scheduler_id="scheduler-1",
            task_id="task-1",
            queue_name="ready",
        )
        seal.task_boundary.on_task_started(
            task_id="task-1",
            runtime_status="running",
        )
        seal.step_hook.before_step(
            task_id="task-1",
            step_id="step-1",
            step_type="respond",
        )
        seal.step_hook.after_step(
            task_id="task-1",
            step_id="step-1",
            step_type="respond",
            status="succeeded",
            evidence_refs={"bundle_id": seal.evidence_refs["bundle_id"]},
        )

        summary = self._consumer().read_seal(seal)

        self.assertEqual(summary["event_count"], 4)
        self.assertEqual(summary["events"]["scheduler"]["phases"], ["task_enqueued"])
        self.assertEqual(summary["events"]["task_runtime"]["phases"], ["task_started"])
        self.assertEqual(summary["events"]["step_executor"]["phases"], ["before_step", "after_step"])
        self.assertEqual(summary["events"]["step_executor"]["statuses"], ["pending", "succeeded"])

    def test_safe_helpers_query_summary_only(self) -> None:
        consumer = self._consumer()
        summary = consumer.read_seal(self._seal("helper-consumer"))

        self.assertEqual(
            consumer.get_record_ref(summary, "bundle_id"),
            summary["record_refs"]["bundle_id"],
        )
        self.assertTrue(consumer.can_replay(summary))
        self.assertTrue(consumer.can_audit(summary))
        self.assertTrue(consumer.can_rollback(summary))


if __name__ == "__main__":
    unittest.main()
