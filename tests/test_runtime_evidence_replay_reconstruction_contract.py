from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEvidenceReplayReconstructionContractTest(unittest.TestCase):
    def _seal(self, seal_id: str = "replay-reconstruction"):
        from core.runtime.runtime_mainline_evidence_seal import build_runtime_mainline_evidence_seal

        return build_runtime_mainline_evidence_seal(
            workspace_root="workspace",
            seal_id=seal_id,
        )

    def _reconstructor(self):
        from core.runtime.runtime_evidence_replay_reconstruction import RuntimeEvidenceReplayReconstructor

        return RuntimeEvidenceReplayReconstructor()

    def test_deterministic_replay_reconstruction(self) -> None:
        reconstructor = self._reconstructor()

        first = reconstructor.reconstruct(self._seal("deterministic-replay"))
        second = reconstructor.reconstruct(self._seal("deterministic-replay"))

        self.assertEqual(first.export(), second.export())
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_execution_replay_ordering_correctness(self) -> None:
        replay = self._reconstructor().reconstruct(self._seal("execution-replay"))
        execution_replay = replay.execution_replay()

        self.assertEqual(
            [item["execution_id"] for item in execution_replay],
            ["scheduler.dispatch", "task_runtime.lifecycle", "step_executor.execute"],
        )
        self.assertEqual(
            [item["replay_order"] for item in execution_replay],
            [0, 1, 2],
        )

    def test_event_replay_ordering_correctness(self) -> None:
        reconstructor = self._reconstructor()
        summary = reconstructor.snapshot_builder.registry.query.summary_from(
            self._seal("event-replay")
        )
        summary["events"]["scheduler"] = {
            "count": 1,
            "phases": ["task_enqueued"],
            "statuses": ["ready"],
            "fingerprints": ["scheduler-fp"],
        }
        summary["events"]["step_executor"] = {
            "count": 2,
            "phases": ["before_step", "after_step"],
            "statuses": ["pending", "succeeded"],
            "fingerprints": ["step-before-fp", "step-after-fp"],
        }

        replay = reconstructor.reconstruct(summary)
        events = replay.event_replay_order()

        self.assertEqual(
            [(item["layer"], item["phase"]) for item in events],
            [
                ("scheduler", "task_enqueued"),
                ("step_executor", "before_step"),
                ("step_executor", "after_step"),
            ],
        )
        self.assertEqual([item["replay_order"] for item in events], [0, 1, 2])

    def test_lineage_replay_reconstruction(self) -> None:
        replay = self._reconstructor().reconstruct(self._seal("lineage-replay"))
        lineage = replay.lineage_replay()

        self.assertEqual(
            [item["lineage_type"] for item in lineage],
            ["plan", "snapshot", "replay", "audit", "bundle"],
        )
        self.assertEqual(
            lineage[2]["lineage_id"],
            "lineage-replay:runtime-evidence:replay",
        )
        self.assertTrue(lineage[2]["verified"])

    def test_failed_execution_replay_behavior(self) -> None:
        reconstructor = self._reconstructor()
        summary = reconstructor.snapshot_builder.registry.query.summary_from(
            self._seal("failed-replay")
        )
        summary["events"]["step_executor"] = {
            "count": 2,
            "phases": ["before_step", "step_failure"],
            "statuses": ["pending", "failed"],
            "fingerprints": ["fp-before", "fp-failed"],
        }

        replay = reconstructor.reconstruct(summary)
        failed = replay.failed_execution_replay()

        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["failed_execution_id"], "fp-failed")
        self.assertEqual(failed[0]["status"], "failed")
        self.assertEqual(replay.payload["replay_counts"]["failed_executions"], 1)

    def test_rollback_replay_reconstruction(self) -> None:
        replay = self._reconstructor().reconstruct(self._seal("rollback-replay"))
        rollback = replay.rollback_replay()

        self.assertTrue(rollback["found"])
        self.assertTrue(rollback["verified"])
        self.assertEqual(
            [item["execution_id"] for item in rollback["rollback_steps"]],
            ["step_executor.execute", "task_runtime.lifecycle", "scheduler.dispatch"],
        )

    def test_immutable_replay_state_guarantees(self) -> None:
        replay = self._reconstructor().reconstruct(self._seal("immutable-replay"))
        before = replay.export()
        payload = replay.payload
        execution = replay.execution_replay()
        lineage = replay.lineage_replay()
        rollback = replay.rollback_replay()

        payload["record_refs"]["bundle_id"] = "polluted"
        execution[0]["execution_id"] = "polluted"
        lineage.append({"lineage_id": "polluted"})
        rollback["rollback_steps"].append({"execution_id": "polluted"})

        self.assertEqual(replay.export(), before)
        self.assertEqual(replay.execution_replay()[0]["execution_id"], "scheduler.dispatch")
        self.assertNotIn("polluted", [item["lineage_id"] for item in replay.lineage_replay()])
        self.assertNotIn(
            "polluted",
            [item["execution_id"] for item in replay.rollback_replay()["rollback_steps"]],
        )

    def test_missing_evidence_safety(self) -> None:
        replay = self._reconstructor().reconstruct(None)
        sealed_state = replay.payload["sealed_state"]

        self.assertFalse(sealed_state["sealed"])
        self.assertEqual(replay.execution_replay(), [])
        self.assertEqual(replay.lineage_replay(), [])
        self.assertEqual(replay.failed_execution_replay(), [])
        self.assertFalse(replay.rollback_replay()["found"])
        self.assertEqual(replay.event_replay_order(), [])

    def test_reconstruction_does_not_mutate_source_snapshot(self) -> None:
        reconstructor = self._reconstructor()
        source_snapshot = reconstructor.snapshot_builder.build(self._seal("source-replay"))
        before = copy.deepcopy(source_snapshot.export())

        replay = reconstructor.reconstruct(source_snapshot)
        replay.payload["record_refs"]["bundle_id"] = "polluted"
        replay.execution_replay()[0]["execution_id"] = "polluted"

        self.assertEqual(source_snapshot.export(), before)


if __name__ == "__main__":
    unittest.main()
