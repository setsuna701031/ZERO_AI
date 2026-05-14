from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEvidenceSnapshotContractTest(unittest.TestCase):
    def _seal(self, seal_id: str = "snapshot-contract"):
        from core.runtime.runtime_mainline_evidence_seal import build_runtime_mainline_evidence_seal

        return build_runtime_mainline_evidence_seal(
            workspace_root="workspace",
            seal_id=seal_id,
        )

    def _builder(self):
        from core.runtime.runtime_evidence_snapshot import RuntimeEvidenceSnapshotBuilder

        return RuntimeEvidenceSnapshotBuilder()

    def test_deterministic_snapshot_generation(self) -> None:
        builder = self._builder()
        first = builder.build(self._seal("deterministic-snapshot"))
        second = builder.build(self._seal("deterministic-snapshot"))

        self.assertEqual(first.export(), second.export())
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_immutable_snapshot_guarantees(self) -> None:
        snapshot = self._builder().build(self._seal("immutable-snapshot"))
        before = snapshot.export()
        payload = snapshot.payload
        execution = snapshot.export_execution("scheduler.dispatch")
        lineage = snapshot.export_lineage()

        payload["record_refs"]["bundle_id"] = "polluted"
        execution["execution"]["execution_index"] = 999
        lineage["lineage"].append({"lineage_id": "polluted"})

        self.assertEqual(snapshot.export(), before)
        self.assertEqual(
            snapshot.export_execution("scheduler.dispatch")["execution"]["execution_index"],
            0,
        )
        self.assertNotIn("polluted", json.dumps(snapshot.export_lineage(), sort_keys=True))

    def test_replay_safe_snapshot_extraction(self) -> None:
        snapshot = self._builder().build(self._seal("replay-safe-snapshot"))
        exported = snapshot.export()
        replay = snapshot.export_replay()
        rollback = snapshot.export_rollback()

        json.dumps(exported, sort_keys=True)
        self.assertEqual(replay["schema"], "zero.runtime_evidence.replay_snapshot.v1")
        self.assertEqual(rollback["schema"], "zero.runtime_evidence.rollback_snapshot.v1")
        self.assertEqual(replay["replay_count"], 1)
        self.assertEqual(rollback["rollback_count"], 1)
        self.assertEqual(
            replay["replay_index"]["replay-safe-snapshot:runtime-evidence:replay"]["bundle_id"],
            "replay-safe-snapshot:runtime-evidence:bundle",
        )
        self.assertEqual(
            rollback["rollback_index"]["replay-safe-snapshot:runtime-evidence:rollback"]["rollback_order"],
            ["step_executor.execute", "task_runtime.lifecycle", "scheduler.dispatch"],
        )

    def test_failed_execution_snapshot_behavior(self) -> None:
        registry = self._builder().registry
        summary = registry.query.summary_from(self._seal("failed-snapshot"))
        summary["events"]["step_executor"] = {
            "count": 2,
            "phases": ["before_step", "step_failure"],
            "statuses": ["pending", "failed"],
            "fingerprints": ["fp-before", "fp-failed"],
        }
        snapshot = self._builder().build(summary)
        failed = snapshot.export_failed_executions()

        self.assertTrue(failed["failed"])
        self.assertEqual(failed["failed_execution_count"], 1)
        self.assertEqual(failed["failed_executions"][0]["failed_execution_id"], "fp-failed")
        self.assertEqual(failed["failed_executions"][0]["status"], "failed")

    def test_lineage_snapshot_correctness(self) -> None:
        snapshot = self._builder().build(self._seal("lineage-snapshot"))
        lineage = snapshot.export_lineage()

        self.assertEqual(lineage["schema"], "zero.runtime_evidence.lineage_snapshot.v1")
        self.assertEqual(lineage["lineage_count"], 5)
        self.assertEqual(
            [item["lineage_type"] for item in lineage["lineage"]],
            ["plan", "snapshot", "replay", "audit", "bundle"],
        )
        self.assertEqual(
            lineage["lineage"][2]["lineage_id"],
            "lineage-snapshot:runtime-evidence:replay",
        )
        self.assertTrue(lineage["lineage"][2]["verified"])

    def test_missing_evidence_safety(self) -> None:
        snapshot = self._builder().build(None)
        sealed = snapshot.export_sealed_state()

        self.assertFalse(sealed["sealed"])
        self.assertFalse(sealed["complete"])
        self.assertEqual(
            sealed["missing_records"],
            ["snapshot", "replay", "audit", "rollback", "bundle"],
        )
        self.assertEqual(snapshot.export_execution()["execution_count"], 0)
        self.assertEqual(snapshot.export_lineage()["lineage_count"], 0)
        self.assertEqual(snapshot.export_replay()["replay_count"], 0)
        self.assertEqual(snapshot.export_rollback()["rollback_count"], 0)
        self.assertFalse(snapshot.export_failed_executions()["failed"])

    def test_snapshot_does_not_mutate_source_registry(self) -> None:
        registry_snapshot = self._builder().registry.rebuild(self._seal("source-registry-snapshot"))
        before = registry_snapshot.payload
        snapshot = self._builder().build(registry_snapshot)

        snapshot.payload["record_refs"]["bundle_id"] = "polluted"
        snapshot.export_execution()["executions"]["scheduler.dispatch"]["execution_index"] = 999

        self.assertEqual(registry_snapshot.payload, before)


if __name__ == "__main__":
    unittest.main()
