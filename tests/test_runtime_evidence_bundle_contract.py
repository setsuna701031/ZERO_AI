from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEvidenceBundleContractTest(unittest.TestCase):
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

    def _plan(self, plan_id="plan-1", metadata=None):
        from core.runtime.execution_plan import ExecutionPlan

        return ExecutionPlan(
            plan_id,
            self._graph(),
            self._transaction(),
            runtime_args={"scope": {"name": "runtime"}},
            metadata=metadata
            if metadata is not None
            else {"source": {"name": "contract"}},
        )

    def _snapshot(self, plan=None, snapshot_id="snapshot-1"):
        from core.runtime.execution_plan_snapshot import ExecutionPlanSnapshot

        return ExecutionPlanSnapshot.from_plan(
            snapshot_id,
            plan if plan is not None else self._plan(),
            created_at="snapshot-time",
        )

    def _replay_record(self, snapshot=None, replay_id="replay-1"):
        from core.runtime.execution_replay import ExecutionReplayVerifier

        snapshot = snapshot if snapshot is not None else self._snapshot()
        return ExecutionReplayVerifier(replay_id).verify_snapshot(snapshot)

    def _audit_record(self, replay_record=None, audit_id="audit-1"):
        from core.runtime.execution_audit import ExecutionAuditRecord

        return ExecutionAuditRecord.from_replay_record(
            audit_id,
            replay_record if replay_record is not None else self._replay_record(),
            metadata={"audit": {"source": "contract"}},
            runtime_args={"audit_runtime": {"mode": "verify"}},
            created_at="audit-time",
        )

    def _rollback_record(self, snapshot=None, rollback_id="rollback-1"):
        from core.runtime.rollback_verification import RollbackVerificationVerifier

        snapshot = snapshot if snapshot is not None else self._snapshot()
        return RollbackVerificationVerifier(rollback_id).verify_snapshot_rollback(
            snapshot,
            created_at="rollback-time",
        )

    def _evidence(self, snapshot=None):
        snapshot = snapshot if snapshot is not None else self._snapshot()
        replay = self._replay_record(snapshot=snapshot)
        audit = self._audit_record(replay_record=replay)
        rollback = self._rollback_record(snapshot=snapshot)
        return snapshot, replay, audit, rollback

    def _bundle(
        self,
        bundle_id="bundle-1",
        evidence=None,
        metadata=None,
        runtime_args=None,
        created_at="bundle-time-a",
    ):
        from core.runtime.runtime_evidence_bundle import RuntimeEvidenceBundle

        snapshot, replay, audit, rollback = (
            evidence if evidence is not None else self._evidence()
        )
        return RuntimeEvidenceBundle(
            bundle_id,
            snapshot,
            replay,
            audit,
            rollback,
            metadata=metadata
            if metadata is not None
            else {"bundle": {"source": "contract"}},
            runtime_args=runtime_args
            if runtime_args is not None
            else {"bundle_runtime": {"mode": "portable"}},
            created_at=created_at,
        )

    def test_bundle_id_validation(self) -> None:
        from core.runtime.runtime_evidence_bundle import (
            RuntimeEvidenceBundle,
            RuntimeEvidenceBundleRejected,
        )

        snapshot, replay, audit, rollback = self._evidence()
        with self.assertRaises(RuntimeEvidenceBundleRejected):
            RuntimeEvidenceBundle("", snapshot, replay, audit, rollback)

    def test_bundle_identity_consistency_validation(self) -> None:
        bundle = self._bundle()

        self.assertEqual(bundle.plan_id, "plan-1")
        self.assertEqual(bundle.snapshot_id, "snapshot-1")

    def test_identity_mismatch_reject(self) -> None:
        from core.runtime.runtime_evidence_bundle import (
            RuntimeEvidenceBundle,
            RuntimeEvidenceBundleRejected,
        )

        snapshot, replay, audit, rollback = self._evidence()
        other_snapshot = self._snapshot(plan=self._plan(plan_id="plan-2"))
        mismatched_replay = self._replay_record(snapshot=other_snapshot)

        with self.assertRaises(RuntimeEvidenceBundleRejected):
            RuntimeEvidenceBundle(
                "bundle-1",
                snapshot,
                mismatched_replay,
                audit,
                rollback,
            )

    def test_immutable_copy_behavior(self) -> None:
        bundle = self._bundle()
        metadata = bundle.metadata
        runtime_args = bundle.runtime_args
        snapshot = bundle.snapshot
        replay = bundle.replay_record
        audit = bundle.audit_record
        rollback = bundle.rollback_record

        metadata["bundle"]["source"] = "polluted"
        runtime_args["bundle_runtime"]["mode"] = "polluted"
        snapshot._metadata["source"]["name"] = "polluted"
        replay._operation_fingerprints["op-1"] = "polluted"
        audit._metadata["audit"]["source"] = "polluted"
        rollback._metadata["source"]["name"] = "polluted"

        self.assertEqual(bundle.metadata, {"bundle": {"source": "contract"}})
        self.assertEqual(bundle.runtime_args, {"bundle_runtime": {"mode": "portable"}})
        self.assertEqual(bundle.snapshot.metadata, {"source": {"name": "contract"}})
        self.assertNotEqual(
            bundle.replay_record.operation_fingerprints["op-1"],
            "polluted",
        )
        self.assertEqual(
            bundle.audit_record.metadata,
            {"audit": {"source": "contract"}},
        )
        self.assertEqual(
            bundle.rollback_record.metadata,
            {"source": {"name": "contract"}},
        )

    def test_deterministic_fingerprint(self) -> None:
        evidence = self._evidence()
        first = self._bundle(
            evidence=evidence,
            metadata={"b": 2, "a": 1},
            runtime_args={"z": 3, "a": 1},
        )
        second = self._bundle(
            evidence=evidence,
            metadata={"a": 1, "b": 2},
            runtime_args={"a": 1, "z": 3},
        )

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        evidence = self._evidence()
        first = self._bundle(
            evidence=evidence,
            created_at="2026-05-13T00:00:00+00:00",
        )
        second = self._bundle(
            evidence=evidence,
            created_at="2027-01-01T00:00:00+00:00",
        )

        self.assertNotEqual(first.created_at, second.created_at)
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_fingerprint_changes_when_evidence_changes(self) -> None:
        first = self._bundle(evidence=self._evidence())
        changed_snapshot = self._snapshot(
            plan=self._plan(metadata={"source": {"name": "changed"}})
        )
        second = self._bundle(evidence=self._evidence(snapshot=changed_snapshot))

        self.assertNotEqual(first.fingerprint, second.fingerprint)

    def test_derived_properties_correctness(self) -> None:
        bundle = self._bundle()

        self.assertEqual(bundle.plan_id, bundle.snapshot.plan_id)
        self.assertEqual(bundle.snapshot_id, bundle.snapshot.snapshot_id)
        self.assertEqual(bundle.aggregate_status, bundle.snapshot.status)

    def test_bundle_unaffected_by_external_mutation(self) -> None:
        snapshot, replay, audit, rollback = self._evidence()
        bundle = self._bundle(evidence=(snapshot, replay, audit, rollback))

        snapshot._metadata["source"]["name"] = "polluted"
        replay._operation_fingerprints["op-1"] = "polluted"
        audit._metadata["audit"]["source"] = "polluted"
        rollback._metadata["source"]["name"] = "polluted"

        self.assertEqual(bundle.snapshot.metadata, {"source": {"name": "contract"}})
        self.assertNotEqual(
            bundle.replay_record.operation_fingerprints["op-1"],
            "polluted",
        )
        self.assertEqual(
            bundle.audit_record.metadata,
            {"audit": {"source": "contract"}},
        )
        self.assertEqual(
            bundle.rollback_record.metadata,
            {"source": {"name": "contract"}},
        )


if __name__ == "__main__":
    unittest.main()
