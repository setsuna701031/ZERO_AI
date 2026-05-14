from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeEvidenceIntegrationContractTest(unittest.TestCase):
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

    def _emitter(self, integration_id="integration-1"):
        from core.runtime.runtime_evidence_integration import RuntimeEvidenceEmitter

        return RuntimeEvidenceEmitter(integration_id)

    def _emit_all(self, emitter=None, plan=None):
        emitter = emitter if emitter is not None else self._emitter()
        plan = plan if plan is not None else self._plan()
        snapshot = emitter.emit_snapshot(plan)
        replay = emitter.emit_replay(snapshot, plan)
        audit = emitter.emit_audit(replay)
        rollback = emitter.emit_rollback(snapshot)
        bundle = emitter.emit_bundle(snapshot, replay, audit, rollback)
        return snapshot, replay, audit, rollback, bundle

    def test_integration_id_validation(self) -> None:
        from core.runtime.runtime_evidence_integration import (
            RuntimeEvidenceEmitter,
            RuntimeEvidenceIntegrationRejected,
        )

        with self.assertRaises(RuntimeEvidenceIntegrationRejected):
            RuntimeEvidenceEmitter("")

    def test_deterministic_emission_order(self) -> None:
        emitter = self._emitter()
        self._emit_all(emitter)

        self.assertEqual(
            [item["type"] for item in emitter.emission_order],
            ["snapshot", "replay", "audit", "rollback", "bundle"],
        )

    def test_snapshot_replay_audit_rollback_bundle_emission_success(self) -> None:
        emitter = self._emitter()
        snapshot, replay, audit, rollback, bundle = self._emit_all(emitter)

        self.assertEqual(snapshot.snapshot_id, "integration-1:snapshot")
        self.assertEqual(replay.replay_id, "integration-1:replay")
        self.assertEqual(audit.audit_id, "integration-1:audit")
        self.assertEqual(rollback.rollback_id, "integration-1:rollback")
        self.assertEqual(bundle.bundle_id, "integration-1:bundle")
        self.assertEqual(emitter.context.plan_id, "plan-1")
        self.assertEqual(emitter.context.snapshot_id, "integration-1:snapshot")

    def test_immutable_isolation_behavior(self) -> None:
        snapshot, replay, audit, rollback, bundle = self._emit_all()

        snapshot._metadata["source"]["name"] = "polluted"
        replay._operation_fingerprints["op-1"] = "polluted"
        audit._metadata = {"polluted": True}
        rollback._metadata["source"]["name"] = "polluted"
        bundle._metadata = {"polluted": True}

        fresh = self._emit_all()[0]
        self.assertEqual(fresh.metadata, {"source": {"name": "contract"}})

    def test_deterministic_fingerprint(self) -> None:
        first = self._emitter()
        second = self._emitter()
        self._emit_all(first)
        self._emit_all(second)

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_fingerprint_changes_when_evidence_changes(self) -> None:
        first = self._emitter()
        second = self._emitter()
        self._emit_all(first)
        self._emit_all(
            second,
            plan=self._plan(metadata={"source": {"name": "changed"}}),
        )

        self.assertNotEqual(first.fingerprint, second.fingerprint)

    def test_runtime_mutation_isolation_after_emission(self) -> None:
        plan = self._plan()
        emitter = self._emitter()
        snapshot = emitter.emit_snapshot(plan)
        before = snapshot.fingerprint

        plan._metadata["source"]["name"] = "polluted"
        plan._runtime_args["scope"]["name"] = "polluted"
        plan._graph.add_node("op-3", "recovery.run")
        plan._transaction.add_operation(self._operation("op-3", "recovery.run"))

        self.assertEqual(snapshot.fingerprint, before)
        self.assertEqual(snapshot.execution_order, ["op-1", "op-2"])

    def test_context_immutable_behavior(self) -> None:
        emitter = self._emitter()
        self._emit_all(emitter)
        context = emitter.context
        identity = context.identity

        identity["plan_id"] = "polluted"
        context._identity["plan_id"] = "polluted"

        self.assertEqual(emitter.context.plan_id, "plan-1")
        self.assertEqual(emitter.context.identity["plan_id"], "plan-1")

    def test_created_at_does_not_affect_fingerprint(self) -> None:
        first = self._emitter()
        second = self._emitter()
        self._emit_all(first)
        self._emit_all(second)

        self.assertNotEqual(first.context.snapshot_id, None)
        self.assertEqual(first.fingerprint, second.fingerprint)


if __name__ == "__main__":
    unittest.main()
