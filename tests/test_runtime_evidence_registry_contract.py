from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEvidenceRegistryContractTest(unittest.TestCase):
    def _seal(self, seal_id: str = "registry-contract"):
        from core.runtime.runtime_mainline_evidence_seal import build_runtime_mainline_evidence_seal

        return build_runtime_mainline_evidence_seal(
            workspace_root="workspace",
            seal_id=seal_id,
        )

    def _registry(self):
        from core.runtime.runtime_evidence_registry import RuntimeEvidenceRegistry

        return RuntimeEvidenceRegistry()

    def test_deterministic_registry_rebuild(self) -> None:
        registry = self._registry()
        first = registry.rebuild(self._seal("deterministic-registry"))
        second = registry.rebuild(self._seal("deterministic-registry"))

        self.assertEqual(first.payload, second.payload)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_execution_index_lookup(self) -> None:
        snapshot = self._registry().rebuild(self._seal("execution-index"))

        execution = snapshot.lookup_execution("step_executor.execute")
        missing = snapshot.lookup_execution("missing.execute")

        self.assertTrue(execution["found"])
        self.assertEqual(execution["execution_id"], "step_executor.execute")
        self.assertEqual(execution["execution_index"], 2)
        self.assertEqual(execution["aggregate_status"], "succeeded")
        self.assertFalse(missing["found"])
        self.assertEqual(missing["execution_id"], "missing.execute")

    def test_step_index_lookup(self) -> None:
        snapshot = self._registry().rebuild(self._seal("step-index"))

        step = snapshot.lookup_step("task_runtime.lifecycle")

        self.assertTrue(step["found"])
        self.assertEqual(step["step_id"], "task_runtime.lifecycle")
        self.assertEqual(step["execution_id"], "task_runtime.lifecycle")
        self.assertEqual(step["step_kind"], "task_runtime")

    def test_lineage_index_correctness(self) -> None:
        snapshot = self._registry().rebuild(self._seal("lineage-index"))

        replay = snapshot.lookup_lineage("lineage-index:runtime-evidence:replay")
        bundle = snapshot.lookup_lineage("lineage-index:runtime-evidence:bundle")

        self.assertTrue(replay["found"])
        self.assertEqual(replay["lineage_type"], "replay")
        self.assertEqual(replay["lineage_index"], 2)
        self.assertTrue(bundle["found"])
        self.assertEqual(bundle["lineage_type"], "bundle")
        self.assertEqual(bundle["lineage_index"], 4)

    def test_replay_and_rollback_linkage_indexes(self) -> None:
        snapshot = self._registry().rebuild(self._seal("linkage-index"))

        replay = snapshot.lookup_replay("linkage-index:runtime-evidence:replay")
        rollback = snapshot.lookup_rollback("linkage-index:runtime-evidence:rollback")

        self.assertTrue(replay["found"])
        self.assertTrue(replay["verified"])
        self.assertEqual(replay["snapshot_id"], "linkage-index:runtime-evidence:snapshot")
        self.assertIn("linkage-index:runtime-evidence:bundle", replay["lineage_ids"])
        self.assertTrue(rollback["found"])
        self.assertTrue(rollback["verified"])
        self.assertEqual(
            rollback["rollback_order"],
            ["step_executor.execute", "task_runtime.lifecycle", "scheduler.dispatch"],
        )

    def test_failed_execution_indexing(self) -> None:
        query = self._registry().query
        summary = query.summary_from(self._seal("failed-registry"))
        summary["events"]["step_executor"] = {
            "count": 2,
            "phases": ["before_step", "step_failure"],
            "statuses": ["pending", "failed"],
            "fingerprints": ["fp-before", "fp-failed"],
        }
        snapshot = self._registry().rebuild(summary)

        failed = snapshot.failed_executions()

        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["failed_execution_id"], "fp-failed")
        self.assertEqual(failed[0]["source"], "step_executor_event")
        self.assertEqual(failed[0]["status"], "failed")
        self.assertEqual(snapshot.payload["index_counts"]["failed_executions"], 1)

    def test_immutable_read_only_guarantees(self) -> None:
        seal = self._seal("immutable-registry")
        snapshot = self._registry().rebuild(seal)
        before_payload = snapshot.payload
        payload = snapshot.payload
        execution = snapshot.lookup_execution("scheduler.dispatch")
        failed = snapshot.failed_executions()

        payload["execution_index"]["scheduler.dispatch"]["execution_index"] = 999
        execution["execution_index"] = 999
        failed.append({"polluted": True})

        self.assertEqual(snapshot.payload, before_payload)
        self.assertEqual(snapshot.lookup_execution("scheduler.dispatch")["execution_index"], 0)
        self.assertEqual(snapshot.failed_executions(), [])

    def test_missing_evidence_safety(self) -> None:
        snapshot = self._registry().rebuild(None)
        payload = snapshot.payload

        self.assertFalse(payload["sealed"])
        self.assertFalse(snapshot.sealed_state()["sealed"])
        self.assertEqual(payload["index_counts"]["executions"], 0)
        self.assertFalse(snapshot.lookup_execution("scheduler.dispatch")["found"])
        self.assertFalse(snapshot.lookup_lineage("missing-lineage")["found"])
        self.assertFalse(snapshot.lookup_replay("missing-replay")["found"])
        self.assertFalse(snapshot.lookup_rollback("missing-rollback")["found"])

    def test_registry_rebuild_does_not_mutate_source_summary(self) -> None:
        registry = self._registry()
        summary = registry.query.summary_from(self._seal("source-isolation"))
        before = copy.deepcopy(summary)

        registry.rebuild(summary)
        registry.rebuild(summary).payload["record_refs"]["bundle_id"] = "polluted"

        self.assertEqual(summary, before)


if __name__ == "__main__":
    unittest.main()
