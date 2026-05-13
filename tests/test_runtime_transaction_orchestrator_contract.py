from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class FakeTransactionManager:
    def __init__(self, fail_run=None) -> None:
        self.begun = []
        self.steps = {}
        self.run_calls = []
        self.commit_calls = []
        self.rollback_calls = []
        self.fail_run = set(fail_run or [])

    def begin(self, transaction_id):
        self.begun.append(transaction_id)
        self.steps[transaction_id] = []
        return {"transaction_id": transaction_id, "status": "created"}

    def add_step(self, transaction_id, operation, runtime_args=None, payload=None, metadata=None):
        self.steps[transaction_id].append(
            {
                "operation": operation,
                "runtime_args": runtime_args,
                "payload": payload,
                "metadata": metadata,
            }
        )
        return {"transaction_id": transaction_id, "operation": operation}

    def run(self, transaction_id):
        self.run_calls.append(transaction_id)
        if transaction_id in self.fail_run:
            raise ValueError(f"failed {transaction_id}")
        return {
            "transaction_id": transaction_id,
            "status": "completed",
            "steps": self.steps.get(transaction_id, []),
        }

    def commit(self, transaction_id):
        self.commit_calls.append(transaction_id)
        return {"transaction_id": transaction_id, "status": "committed"}

    def rollback(self, transaction_id, reason=None):
        self.rollback_calls.append((transaction_id, reason))
        return {
            "transaction_id": transaction_id,
            "status": "rolled_back",
            "reason": reason,
        }


class RuntimeTransactionOrchestratorContractTest(unittest.TestCase):
    def _orchestrator(self, manager=None):
        from core.runtime.runtime_transaction_orchestrator import (
            RuntimeTransactionOrchestrator,
        )

        return RuntimeTransactionOrchestrator(
            transaction_manager=manager if manager is not None else FakeTransactionManager()
        )

    def _steps(self):
        return [
            {
                "operation": "lifecycle.queue",
                "runtime_args": {"lifecycle_id": "life-1"},
                "payload": {"task_id": "task-1"},
                "metadata": {"source": "contract"},
            }
        ]

    def test_create_orchestration(self) -> None:
        orchestration = self._orchestrator().create("orch-1")

        self.assertEqual(orchestration.orchestration_id, "orch-1")
        self.assertEqual(orchestration.status, "created")
        self.assertFalse(orchestration.committed)
        self.assertFalse(orchestration.rolled_back)

    def test_empty_orchestration_id_rejected(self) -> None:
        from core.runtime.runtime_transaction_orchestrator import (
            RuntimeTransactionOrchestrationRejected,
        )

        with self.assertRaises(RuntimeTransactionOrchestrationRejected):
            self._orchestrator().create("")

    def test_duplicate_orchestration_id_rejected(self) -> None:
        from core.runtime.runtime_transaction_orchestrator import (
            RuntimeTransactionOrchestrationRejected,
        )

        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")

        with self.assertRaises(RuntimeTransactionOrchestrationRejected):
            orchestrator.create("orch-1")

    def test_add_transaction_to_created_orchestration(self) -> None:
        manager = FakeTransactionManager()
        orchestrator = self._orchestrator(manager=manager)
        orchestrator.create("orch-1")
        item = orchestrator.add_transaction("orch-1", "tx-1", steps=self._steps())

        self.assertEqual(item.status, "pending")
        self.assertEqual(item.transaction_id, "tx-1")
        self.assertEqual(manager.begun, ["tx-1"])
        self.assertEqual(manager.steps["tx-1"], self._steps())

    def test_duplicate_transaction_id_in_orchestration_rejected(self) -> None:
        from core.runtime.runtime_transaction_orchestrator import (
            RuntimeTransactionOrchestrationRejected,
        )

        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")

        with self.assertRaises(RuntimeTransactionOrchestrationRejected):
            orchestrator.add_transaction("orch-1", "tx-1")

    def test_empty_transaction_id_rejected(self) -> None:
        from core.runtime.runtime_transaction_orchestrator import (
            RuntimeTransactionOrchestrationRejected,
        )

        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")

        with self.assertRaises(RuntimeTransactionOrchestrationRejected):
            orchestrator.add_transaction("orch-1", "")

    def test_add_transaction_rejected_after_run_completed(self) -> None:
        from core.runtime.runtime_transaction_orchestrator import (
            RuntimeTransactionOrchestrationRejected,
        )

        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")
        orchestrator.run("orch-1")

        with self.assertRaises(RuntimeTransactionOrchestrationRejected):
            orchestrator.add_transaction("orch-1", "tx-2")

    def test_item_sequence_increments_per_orchestration(self) -> None:
        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        first = orchestrator.add_transaction("orch-1", "tx-1")
        second = orchestrator.add_transaction("orch-1", "tx-2")
        orchestrator.create("orch-2")
        other = orchestrator.add_transaction("orch-2", "tx-3")

        self.assertEqual([first.sequence, second.sequence, other.sequence], [1, 2, 1])

    def test_orchestration_sequence_increments_globally(self) -> None:
        orchestrator = self._orchestrator()
        first = orchestrator.create("orch-1")
        second = orchestrator.create("orch-2")

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_run_executes_transactions_in_order(self) -> None:
        manager = FakeTransactionManager()
        orchestrator = self._orchestrator(manager=manager)
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")
        orchestrator.add_transaction("orch-1", "tx-2")
        orchestrator.run("orch-1")

        self.assertEqual(manager.run_calls, ["tx-1", "tx-2"])

    def test_run_marks_orchestration_completed(self) -> None:
        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")
        orchestration = orchestrator.run("orch-1")

        self.assertEqual(orchestration.status, "completed")

    def test_run_stores_transaction_results(self) -> None:
        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")
        orchestration = orchestrator.run("orch-1")

        self.assertEqual(orchestration.items[0].status, "completed")
        self.assertEqual(orchestration.items[0].result["transaction_id"], "tx-1")
        self.assertEqual(orchestration.results[0]["transaction_id"], "tx-1")

    def test_handler_can_override_item_result(self) -> None:
        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")

        orchestration = orchestrator.run(
            "orch-1",
            handler=lambda item, tx_result: {
                "handled": item.transaction_id,
                "status": tx_result["status"],
            },
        )

        self.assertEqual(orchestration.items[0].result, {"handled": "tx-1", "status": "completed"})

    def test_transaction_failure_marks_orchestration_failed(self) -> None:
        orchestrator = self._orchestrator(manager=FakeTransactionManager(fail_run={"tx-2"}))
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")
        orchestrator.add_transaction("orch-1", "tx-2")

        with self.assertRaises(Exception):
            orchestrator.run("orch-1")

        self.assertEqual(orchestrator.get("orch-1").status, "failed")
        self.assertEqual(orchestrator.get("orch-1").items[1].status, "failed")

    def test_transaction_failure_wraps_runtime_transaction_orchestration_rejected(self) -> None:
        from core.runtime.runtime_transaction_orchestrator import (
            RuntimeTransactionOrchestrationRejected,
        )

        orchestrator = self._orchestrator(manager=FakeTransactionManager(fail_run={"tx-1"}))
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")

        with self.assertRaises(RuntimeTransactionOrchestrationRejected) as context:
            orchestrator.run("orch-1")

        self.assertIsNotNone(context.exception.original_exception)

    def test_pending_items_skipped_after_failure(self) -> None:
        orchestrator = self._orchestrator(manager=FakeTransactionManager(fail_run={"tx-2"}))
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")
        orchestrator.add_transaction("orch-1", "tx-2")
        orchestrator.add_transaction("orch-1", "tx-3")

        with self.assertRaises(Exception):
            orchestrator.run("orch-1")

        self.assertEqual(
            [item.status for item in orchestrator.get("orch-1").items],
            ["completed", "failed", "skipped"],
        )

    def test_commit_requires_completed(self) -> None:
        from core.runtime.runtime_transaction_orchestrator import (
            RuntimeTransactionOrchestrationRejected,
        )

        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")

        with self.assertRaises(RuntimeTransactionOrchestrationRejected):
            orchestrator.commit("orch-1")

    def test_commit_marks_orchestration_committed(self) -> None:
        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")
        orchestrator.run("orch-1")
        orchestration = orchestrator.commit("orch-1")

        self.assertEqual(orchestration.status, "committed")
        self.assertTrue(orchestration.committed)

    def test_commit_marks_items_committed(self) -> None:
        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")
        orchestrator.add_transaction("orch-1", "tx-2")
        orchestrator.run("orch-1")
        orchestration = orchestrator.commit("orch-1")

        self.assertEqual(
            [item.status for item in orchestration.items],
            ["committed", "committed"],
        )

    def test_rollback_allowed_from_created(self) -> None:
        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestration = orchestrator.rollback("orch-1")

        self.assertEqual(orchestration.status, "rolled_back")
        self.assertTrue(orchestration.rolled_back)

    def test_rollback_allowed_from_completed(self) -> None:
        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")
        orchestrator.run("orch-1")
        orchestration = orchestrator.rollback("orch-1")

        self.assertEqual(orchestration.status, "rolled_back")
        self.assertEqual(orchestration.items[0].status, "rolled_back")

    def test_rollback_allowed_from_failed(self) -> None:
        orchestrator = self._orchestrator(manager=FakeTransactionManager(fail_run={"tx-1"}))
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")
        with self.assertRaises(Exception):
            orchestrator.run("orch-1")

        orchestration = orchestrator.rollback("orch-1", reason="failed")

        self.assertEqual(orchestration.status, "rolled_back")
        self.assertEqual(orchestration.items[0].status, "rolled_back")

    def test_rollback_rejected_after_committed(self) -> None:
        from core.runtime.runtime_transaction_orchestrator import (
            RuntimeTransactionOrchestrationRejected,
        )

        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")
        orchestrator.run("orch-1")
        orchestrator.commit("orch-1")

        with self.assertRaises(RuntimeTransactionOrchestrationRejected):
            orchestrator.rollback("orch-1")

    def test_rolled_back_orchestration_cannot_run(self) -> None:
        from core.runtime.runtime_transaction_orchestrator import (
            RuntimeTransactionOrchestrationRejected,
        )

        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrator.rollback("orch-1")

        with self.assertRaises(RuntimeTransactionOrchestrationRejected):
            orchestrator.run("orch-1")

    def test_committed_orchestration_cannot_run(self) -> None:
        from core.runtime.runtime_transaction_orchestrator import (
            RuntimeTransactionOrchestrationRejected,
        )

        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")
        orchestrator.run("orch-1")
        orchestrator.commit("orch-1")

        with self.assertRaises(RuntimeTransactionOrchestrationRejected):
            orchestrator.run("orch-1")

    def test_committed_orchestration_cannot_add_transaction(self) -> None:
        from core.runtime.runtime_transaction_orchestrator import (
            RuntimeTransactionOrchestrationRejected,
        )

        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")
        orchestrator.run("orch-1")
        orchestrator.commit("orch-1")

        with self.assertRaises(RuntimeTransactionOrchestrationRejected):
            orchestrator.add_transaction("orch-1", "tx-2")

    def test_rolled_back_orchestration_cannot_add_transaction(self) -> None:
        from core.runtime.runtime_transaction_orchestrator import (
            RuntimeTransactionOrchestrationRejected,
        )

        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrator.rollback("orch-1")

        with self.assertRaises(RuntimeTransactionOrchestrationRejected):
            orchestrator.add_transaction("orch-1", "tx-1")

    def test_payload_preserved(self) -> None:
        payload = {"batch": "one"}
        orchestration = self._orchestrator().create("orch-1", payload=payload)

        self.assertIs(orchestration.payload, payload)

    def test_metadata_preserved(self) -> None:
        metadata = {"source": "contract"}
        orchestration = self._orchestrator().create("orch-1", metadata=metadata)

        self.assertIs(orchestration.metadata, metadata)

    def test_steps_preserved(self) -> None:
        steps = self._steps()
        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        item = orchestrator.add_transaction("orch-1", "tx-1", steps=steps)

        self.assertIs(item.steps, steps)

    def test_payload_not_mutated(self) -> None:
        payload = {"items": [{"id": "one"}]}
        before = copy.deepcopy(payload)
        orchestrator = self._orchestrator()
        orchestrator.create("orch-1", payload=payload)
        orchestrator.rollback("orch-1")

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        metadata = {"tags": ["contract"]}
        before = copy.deepcopy(metadata)
        orchestrator = self._orchestrator()
        orchestrator.create("orch-1", metadata=metadata)
        orchestrator.rollback("orch-1")

        self.assertEqual(metadata, before)

    def test_steps_not_mutated(self) -> None:
        steps = self._steps()
        before = copy.deepcopy(steps)
        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1", steps=steps)
        orchestrator.run("orch-1")

        self.assertEqual(steps, before)

    def test_get_returns_copy(self) -> None:
        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrator.add_transaction("orch-1", "tx-1")
        orchestration = orchestrator.get("orch-1")
        orchestration.status = "polluted"
        orchestration.items[0].status = "polluted"

        current = orchestrator.get("orch-1")
        self.assertEqual(current.status, "created")
        self.assertEqual(current.items[0].status, "pending")

    def test_list_all_returns_copy(self) -> None:
        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrations = orchestrator.list_all()
        orchestrations[0].status = "polluted"
        orchestrations.clear()

        current = orchestrator.list_all()
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].status, "created")

    def test_clear_resets_orchestrator_and_sequence(self) -> None:
        orchestrator = self._orchestrator()
        orchestrator.create("orch-1")
        orchestrator.clear()
        orchestration = orchestrator.create("orch-2")

        self.assertEqual(orchestration.sequence, 1)
        self.assertEqual(len(orchestrator.list_all()), 1)


if __name__ == "__main__":
    unittest.main()
