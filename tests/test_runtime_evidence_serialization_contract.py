from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEvidenceSerializationContractTest(unittest.TestCase):
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

    def _bundle(self, created_at="bundle-time", snapshot_created_at="snapshot-time"):
        from core.runtime.execution_audit import ExecutionAuditRecord
        from core.runtime.execution_plan_snapshot import ExecutionPlanSnapshot
        from core.runtime.execution_replay import ExecutionReplayVerifier
        from core.runtime.rollback_verification import RollbackVerificationVerifier
        from core.runtime.runtime_evidence_bundle import RuntimeEvidenceBundle

        snapshot = ExecutionPlanSnapshot.from_plan(
            "snapshot-1",
            self._plan(),
            created_at=snapshot_created_at,
        )
        replay = ExecutionReplayVerifier("replay-1").verify_snapshot(snapshot)
        audit = ExecutionAuditRecord.from_replay_record(
            "audit-1",
            replay,
            metadata={"audit": {"source": "contract"}},
            runtime_args={"audit_runtime": {"mode": "verify"}},
            created_at="audit-time",
        )
        rollback = RollbackVerificationVerifier(
            "rollback-1"
        ).verify_snapshot_rollback(snapshot, created_at="rollback-time")
        return RuntimeEvidenceBundle(
            "bundle-1",
            snapshot,
            replay,
            audit,
            rollback,
            metadata={"bundle": {"source": "contract"}},
            runtime_args={"bundle_runtime": {"mode": "portable"}},
            created_at=created_at,
        )

    def _serializer(self):
        from core.runtime.runtime_evidence_serialization import RuntimeEvidenceSerializer

        return RuntimeEvidenceSerializer()

    def test_serialize_success(self) -> None:
        payload = self._serializer().serialize_bundle(self._bundle())
        data = json.loads(payload)

        self.assertEqual(data["schema_version"], "runtime_evidence_bundle.v1")
        self.assertEqual(data["bundle"]["bundle_id"], "bundle-1")
        self.assertIn("snapshot", data)
        self.assertIn("replay", data)
        self.assertIn("audit", data)
        self.assertIn("rollback_verification", data)
        self.assertIn("fingerprints", data)

    def test_deserialize_success(self) -> None:
        bundle = self._bundle()
        restored = self._serializer().deserialize_bundle(
            self._serializer().serialize_bundle(bundle)
        )

        self.assertEqual(restored.bundle_id, "bundle-1")
        self.assertEqual(restored.plan_id, bundle.plan_id)
        self.assertEqual(restored.snapshot_id, bundle.snapshot_id)
        self.assertEqual(restored.aggregate_status, bundle.aggregate_status)

    def test_serialize_deserialize_roundtrip_deterministic(self) -> None:
        serializer = self._serializer()
        first_payload = serializer.serialize_bundle(self._bundle())
        restored = serializer.deserialize_bundle(first_payload)
        second_payload = serializer.serialize_bundle(restored)

        self.assertEqual(first_payload, second_payload)

    def test_fingerprint_consistency_after_deserialize(self) -> None:
        bundle = self._bundle()
        restored = self._serializer().deserialize_bundle(
            self._serializer().serialize_bundle(bundle)
        )

        self.assertEqual(restored.fingerprint, bundle.fingerprint)

    def test_missing_field_reject(self) -> None:
        from core.runtime.runtime_evidence_serialization import (
            RuntimeEvidenceSerializationRejected,
        )

        payload = json.loads(self._serializer().serialize_bundle(self._bundle()))
        del payload["snapshot"]["plan_id"]

        with self.assertRaises(RuntimeEvidenceSerializationRejected):
            self._serializer().deserialize_bundle(payload)

    def test_payload_fingerprint_mismatch_reject(self) -> None:
        from core.runtime.runtime_evidence_serialization import (
            RuntimeEvidenceSerializationRejected,
        )

        payload = json.loads(self._serializer().serialize_bundle(self._bundle()))
        payload["fingerprints"]["bundle"] = "polluted"

        with self.assertRaises(RuntimeEvidenceSerializationRejected):
            self._serializer().deserialize_bundle(payload)

    def test_payload_mutation_isolation(self) -> None:
        bundle = self._bundle()
        payload = json.loads(self._serializer().serialize_bundle(bundle))
        payload["bundle"]["metadata"]["bundle"]["source"] = "polluted"

        self.assertEqual(bundle.metadata, {"bundle": {"source": "contract"}})

    def test_canonical_deterministic_payload_output(self) -> None:
        payload = self._serializer().serialize_bundle(self._bundle())

        self.assertEqual(
            payload,
            json.dumps(json.loads(payload), sort_keys=True, separators=(",", ":")),
        )

    def test_created_at_does_not_affect_payload_determinism(self) -> None:
        first = self._serializer().serialize_bundle(
            self._bundle(
                created_at="2026-05-13T00:00:00+00:00",
                snapshot_created_at="2026-05-13T00:00:00+00:00",
            )
        )
        second = self._serializer().serialize_bundle(
            self._bundle(
                created_at="2027-01-01T00:00:00+00:00",
                snapshot_created_at="2027-01-01T00:00:00+00:00",
            )
        )

        self.assertEqual(first, second)

    def test_immutable_isolation_after_deserialize(self) -> None:
        restored = self._serializer().deserialize_bundle(
            self._serializer().serialize_bundle(self._bundle())
        )
        snapshot = restored.snapshot
        replay = restored.replay_record
        audit = restored.audit_record
        rollback = restored.rollback_record
        metadata = restored.metadata
        runtime_args = restored.runtime_args

        snapshot._metadata["source"]["name"] = "polluted"
        replay._operation_fingerprints["op-1"] = "polluted"
        audit._metadata["audit"]["source"] = "polluted"
        rollback._metadata["source"]["name"] = "polluted"
        metadata["bundle"]["source"] = "polluted"
        runtime_args["bundle_runtime"]["mode"] = "polluted"

        self.assertEqual(restored.snapshot.metadata, {"source": {"name": "contract"}})
        self.assertNotEqual(
            restored.replay_record.operation_fingerprints["op-1"],
            "polluted",
        )
        self.assertEqual(restored.audit_record.metadata, {"audit": {"source": "contract"}})
        self.assertEqual(restored.rollback_record.metadata, {"source": {"name": "contract"}})
        self.assertEqual(restored.metadata, {"bundle": {"source": "contract"}})
        self.assertEqual(restored.runtime_args, {"bundle_runtime": {"mode": "portable"}})


if __name__ == "__main__":
    unittest.main()
