from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEvidencePersistenceContractTest(unittest.TestCase):
    def _operation(self, operation_id="op-1", operation="lifecycle.queue"):
        from core.runtime.runtime_operation import RuntimeOperation

        return RuntimeOperation(
            operation_id,
            operation,
            runtime_args={"operation_arg": operation_id},
            metadata={"operation": operation},
        )

    def _graph(self):
        from core.runtime.runtime_execution_graph import RuntimeExecutionGraph

        graph = RuntimeExecutionGraph()
        graph.add_node("op-2", "lifecycle.dispatch")
        graph.add_node("op-1", "lifecycle.queue")
        graph.add_dependency("op-1", "op-2")
        return graph

    def _transaction(self):
        from core.runtime.runtime_transaction import RuntimeTransaction

        transaction = RuntimeTransaction("tx-1")
        transaction.add_operation(self._operation("op-1", "lifecycle.queue"))
        transaction.add_operation(self._operation("op-2", "lifecycle.dispatch"))
        return transaction

    def _plan(self, metadata=None):
        from core.runtime.execution_plan import ExecutionPlan

        return ExecutionPlan(
            "plan-1",
            self._graph(),
            self._transaction(),
            runtime_args={"scope": {"name": "runtime"}},
            metadata=metadata
            if metadata is not None
            else {"source": {"name": "contract"}},
        )

    def _bundle(
        self,
        bundle_id="bundle-1",
        created_at="bundle-time",
        metadata=None,
    ):
        from core.runtime.execution_audit import ExecutionAuditRecord
        from core.runtime.execution_plan_snapshot import ExecutionPlanSnapshot
        from core.runtime.execution_replay import ExecutionReplayVerifier
        from core.runtime.rollback_verification import RollbackVerificationVerifier
        from core.runtime.runtime_evidence_bundle import RuntimeEvidenceBundle

        snapshot = ExecutionPlanSnapshot.from_plan(
            "snapshot-1",
            self._plan(),
            created_at="snapshot-time",
        )
        replay = ExecutionReplayVerifier(f"replay-{bundle_id}").verify_snapshot(snapshot)
        audit = ExecutionAuditRecord.from_replay_record(
            f"audit-{bundle_id}",
            replay,
            metadata={"audit": {"source": "contract"}},
            runtime_args={"audit_runtime": {"mode": "verify"}},
            created_at="audit-time",
        )
        rollback = RollbackVerificationVerifier(
            f"rollback-{bundle_id}"
        ).verify_snapshot_rollback(snapshot, created_at="rollback-time")
        return RuntimeEvidenceBundle(
            bundle_id,
            snapshot,
            replay,
            audit,
            rollback,
            metadata=metadata
            if metadata is not None
            else {"bundle": {"source": "contract"}},
            runtime_args={"bundle_runtime": {"mode": "portable"}},
            created_at=created_at,
        )

    def _store(self, store_id="store-1"):
        from core.runtime.runtime_evidence_persistence import (
            InMemoryRuntimeEvidenceStore,
        )

        return InMemoryRuntimeEvidenceStore(store_id)

    def test_store_id_validation(self) -> None:
        from core.runtime.runtime_evidence_persistence import (
            InMemoryRuntimeEvidenceStore,
            RuntimeEvidencePersistenceRejected,
        )

        with self.assertRaises(RuntimeEvidencePersistenceRejected):
            InMemoryRuntimeEvidenceStore("")

    def test_save_success(self) -> None:
        store = self._store()
        bundle = self._bundle()
        saved = store.save_bundle(bundle)

        self.assertTrue(store.has_bundle("bundle-1"))
        self.assertEqual(saved.bundle_id, "bundle-1")

    def test_duplicate_bundle_reject(self) -> None:
        from core.runtime.runtime_evidence_persistence import (
            RuntimeEvidencePersistenceRejected,
        )

        store = self._store()
        store.save_bundle(self._bundle())

        with self.assertRaises(RuntimeEvidencePersistenceRejected):
            store.save_bundle(self._bundle())

    def test_load_success(self) -> None:
        store = self._store()
        bundle = self._bundle()
        store.save_bundle(bundle)
        loaded = store.load_bundle("bundle-1")

        self.assertEqual(loaded.bundle_id, "bundle-1")
        self.assertEqual(loaded.fingerprint, bundle.fingerprint)

    def test_missing_bundle_reject(self) -> None:
        from core.runtime.runtime_evidence_persistence import (
            RuntimeEvidencePersistenceRejected,
        )

        with self.assertRaises(RuntimeEvidencePersistenceRejected):
            self._store().load_bundle("missing")

    def test_immutable_isolation_on_save_load(self) -> None:
        store = self._store()
        bundle = self._bundle()
        store.save_bundle(bundle)
        bundle._metadata["bundle"]["source"] = "polluted"

        loaded = store.load_bundle("bundle-1")
        loaded._metadata["bundle"]["source"] = "loaded-polluted"

        self.assertEqual(
            store.load_bundle("bundle-1").metadata,
            {"bundle": {"source": "contract"}},
        )

    def test_list_bundle_ids_deterministic(self) -> None:
        store = self._store()
        store.save_bundle(self._bundle("bundle-2"))
        store.save_bundle(self._bundle("bundle-1"))

        self.assertEqual(store.list_bundle_ids(), ["bundle-2", "bundle-1"])

    def test_delete_success(self) -> None:
        store = self._store()
        bundle = self._bundle()
        store.save_bundle(bundle)
        deleted = store.delete_bundle("bundle-1")

        self.assertEqual(deleted.fingerprint, bundle.fingerprint)
        self.assertFalse(store.has_bundle("bundle-1"))
        self.assertEqual(store.list_bundle_ids(), [])

    def test_fingerprint_deterministic(self) -> None:
        first = self._store()
        second = self._store()
        first.save_bundle(self._bundle("bundle-1"))
        first.save_bundle(self._bundle("bundle-2"))
        second.save_bundle(self._bundle("bundle-1"))
        second.save_bundle(self._bundle("bundle-2"))

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_fingerprint_changes_after_save_delete(self) -> None:
        store = self._store()
        empty = store.fingerprint
        store.save_bundle(self._bundle("bundle-1"))
        after_save = store.fingerprint
        store.delete_bundle("bundle-1")

        self.assertNotEqual(empty, after_save)
        self.assertEqual(empty, store.fingerprint)

    def test_bundle_fingerprint_consistency_after_load(self) -> None:
        store = self._store()
        bundle = self._bundle()
        store.save_bundle(bundle)

        self.assertEqual(store.load_bundle("bundle-1").fingerprint, bundle.fingerprint)

    def test_created_at_does_not_affect_store_fingerprint(self) -> None:
        first = self._store()
        second = self._store()
        first.save_bundle(
            self._bundle(
                created_at="2026-05-13T00:00:00+00:00",
            )
        )
        second.save_bundle(
            self._bundle(
                created_at="2027-01-01T00:00:00+00:00",
            )
        )

        self.assertEqual(first.fingerprint, second.fingerprint)


if __name__ == "__main__":
    unittest.main()
