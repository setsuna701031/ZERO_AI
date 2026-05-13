from __future__ import annotations

import copy
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class FakeStep:
    operation: str
    runtime_args: object
    payload: object
    metadata: object
    sequence: int


@dataclass
class FakeTransaction:
    transaction_id: str
    steps: list
    sequence: int


@dataclass
class FakePlan:
    plan_id: str
    transactions: list


class FakePlanner:
    def __init__(self, fail=False) -> None:
        self.fail = fail
        self.calls = []

    def create_plan(self, plan_id, operations, payload=None, metadata=None):
        self.calls.append(
            {
                "plan_id": plan_id,
                "operations": operations,
                "payload": payload,
                "metadata": metadata,
            }
        )
        if self.fail:
            raise ValueError("planner failed")

        transactions = []
        by_id = {}
        for operation in operations:
            transaction_id = operation.get("transaction_id") or f"{plan_id}:tx:1"
            transaction = by_id.get(transaction_id)
            if transaction is None:
                transaction = FakeTransaction(
                    transaction_id=transaction_id,
                    steps=[],
                    sequence=len(transactions) + 1,
                )
                by_id[transaction_id] = transaction
                transactions.append(transaction)
            transaction.steps.append(
                FakeStep(
                    operation=operation.get("operation"),
                    runtime_args=operation.get("runtime_args"),
                    payload=operation.get("payload"),
                    metadata=operation.get("metadata"),
                    sequence=len(transaction.steps) + 1,
                )
            )

        return FakePlan(plan_id=plan_id, transactions=transactions)


class FakeOrchestrator:
    def __init__(self, fail_at=None) -> None:
        self.fail_at = fail_at
        self.created = []
        self.added = []
        self.ran = []
        self.committed = []
        self.rolled_back = []

    def create(self, orchestration_id, payload=None, metadata=None):
        if self.fail_at == "create":
            raise ValueError("orchestrator create failed")
        self.created.append((orchestration_id, payload, metadata))
        return {"orchestration_id": orchestration_id, "status": "created"}

    def add_transaction(self, orchestration_id, transaction_id, steps=None):
        if self.fail_at == "add":
            raise ValueError("orchestrator add failed")
        self.added.append((orchestration_id, transaction_id, steps))
        return {"transaction_id": transaction_id, "steps": steps}

    def run(self, orchestration_id, handler=None):
        if self.fail_at == "run":
            raise ValueError("orchestrator run failed")
        self.ran.append((orchestration_id, handler))
        return {"orchestration_id": orchestration_id, "status": "completed"}

    def commit(self, orchestration_id):
        self.committed.append(orchestration_id)
        return {"orchestration_id": orchestration_id, "status": "committed"}

    def rollback(self, orchestration_id, reason=None):
        self.rolled_back.append((orchestration_id, reason))
        return {
            "orchestration_id": orchestration_id,
            "status": "rolled_back",
            "reason": reason,
        }


class RuntimePlanExecutorContractTest(unittest.TestCase):
    def _operation(self, operation="lifecycle.queue", transaction_id=None):
        request = {
            "operation": operation,
            "runtime_args": {"lifecycle_id": "life-1"},
            "payload": {"task_id": operation},
            "metadata": {"source": "contract"},
        }
        if transaction_id is not None:
            request["transaction_id"] = transaction_id
        return request

    def _executor(self, planner=None, orchestrator=None):
        from core.runtime.runtime_plan_executor import RuntimePlanExecutor

        return RuntimePlanExecutor(
            planner=planner if planner is not None else FakePlanner(),
            orchestrator=orchestrator if orchestrator is not None else FakeOrchestrator(),
        )

    def test_execute_plan_creates_execution(self) -> None:
        execution = self._executor().execute_plan(
            "exec-1",
            "plan-1",
            [self._operation()],
        )

        self.assertEqual(execution.execution_id, "exec-1")
        self.assertEqual(execution.plan_id, "plan-1")
        self.assertEqual(execution.status, "completed")

    def test_empty_execution_id_rejected(self) -> None:
        from core.runtime.runtime_plan_executor import RuntimePlanExecutionRejected

        with self.assertRaises(RuntimePlanExecutionRejected):
            self._executor().execute_plan("", "plan-1", [self._operation()])

    def test_duplicate_execution_id_rejected(self) -> None:
        from core.runtime.runtime_plan_executor import RuntimePlanExecutionRejected

        executor = self._executor()
        executor.execute_plan("exec-1", "plan-1", [self._operation()])

        with self.assertRaises(RuntimePlanExecutionRejected):
            executor.execute_plan("exec-1", "plan-2", [self._operation()])

    def test_empty_plan_id_rejected(self) -> None:
        from core.runtime.runtime_plan_executor import RuntimePlanExecutionRejected

        with self.assertRaises(RuntimePlanExecutionRejected):
            self._executor().execute_plan("exec-1", "", [self._operation()])

    def test_execute_plan_creates_orchestration(self) -> None:
        orchestrator = FakeOrchestrator()
        self._executor(orchestrator=orchestrator).execute_plan(
            "exec-1",
            "plan-1",
            [self._operation()],
        )

        self.assertEqual(orchestrator.created[0][0], "exec-1:orchestration")

    def test_execute_plan_adds_planned_transactions_to_orchestrator(self) -> None:
        orchestrator = FakeOrchestrator()
        self._executor(orchestrator=orchestrator).execute_plan(
            "exec-1",
            "plan-1",
            [
                self._operation("lifecycle.queue", transaction_id="tx-1"),
                self._operation("recovery.run", transaction_id="tx-2"),
            ],
        )

        self.assertEqual(
            [(item[1], item[2][0]["operation"]) for item in orchestrator.added],
            [("tx-1", "lifecycle.queue"), ("tx-2", "recovery.run")],
        )

    def test_execute_plan_runs_orchestration(self) -> None:
        orchestrator = FakeOrchestrator()
        self._executor(orchestrator=orchestrator).execute_plan(
            "exec-1",
            "plan-1",
            [self._operation()],
        )

        self.assertEqual(orchestrator.ran[0][0], "exec-1:orchestration")

    def test_execution_status_completed_after_run(self) -> None:
        execution = self._executor().execute_plan(
            "exec-1",
            "plan-1",
            [self._operation()],
        )

        self.assertEqual(execution.status, "completed")

    def test_commit_requires_completed(self) -> None:
        from core.runtime.runtime_plan_executor import RuntimePlanExecutionRejected

        executor = self._executor(orchestrator=FakeOrchestrator(fail_at="run"))
        with self.assertRaises(RuntimePlanExecutionRejected):
            executor.execute_plan("exec-1", "plan-1", [self._operation()])

        with self.assertRaises(RuntimePlanExecutionRejected):
            executor.commit_execution("exec-1")

    def test_commit_marks_committed(self) -> None:
        orchestrator = FakeOrchestrator()
        executor = self._executor(orchestrator=orchestrator)
        executor.execute_plan("exec-1", "plan-1", [self._operation()])
        execution = executor.commit_execution("exec-1")

        self.assertEqual(execution.status, "committed")
        self.assertTrue(execution.committed)
        self.assertEqual(orchestrator.committed, ["exec-1:orchestration"])

    def test_rollback_allowed_from_completed(self) -> None:
        orchestrator = FakeOrchestrator()
        executor = self._executor(orchestrator=orchestrator)
        executor.execute_plan("exec-1", "plan-1", [self._operation()])
        execution = executor.rollback_execution("exec-1", reason="contract")

        self.assertEqual(execution.status, "rolled_back")
        self.assertTrue(execution.rolled_back)
        self.assertEqual(
            orchestrator.rolled_back,
            [("exec-1:orchestration", "contract")],
        )

    def test_rollback_rejected_after_committed(self) -> None:
        from core.runtime.runtime_plan_executor import RuntimePlanExecutionRejected

        executor = self._executor()
        executor.execute_plan("exec-1", "plan-1", [self._operation()])
        executor.commit_execution("exec-1")

        with self.assertRaises(RuntimePlanExecutionRejected):
            executor.rollback_execution("exec-1")

    def test_planner_exception_wraps_runtime_plan_execution_rejected(self) -> None:
        from core.runtime.runtime_plan_executor import RuntimePlanExecutionRejected

        with self.assertRaises(RuntimePlanExecutionRejected) as context:
            self._executor(planner=FakePlanner(fail=True)).execute_plan(
                "exec-1",
                "plan-1",
                [self._operation()],
            )

        self.assertIsNotNone(context.exception.original_exception)

    def test_orchestrator_exception_wraps_runtime_plan_execution_rejected(self) -> None:
        from core.runtime.runtime_plan_executor import RuntimePlanExecutionRejected

        with self.assertRaises(RuntimePlanExecutionRejected) as context:
            self._executor(orchestrator=FakeOrchestrator(fail_at="run")).execute_plan(
                "exec-1",
                "plan-1",
                [self._operation()],
            )

        self.assertIsNotNone(context.exception.original_exception)

    def test_failed_execution_records_status_failed(self) -> None:
        from core.runtime.runtime_plan_executor import RuntimePlanExecutionRejected

        executor = self._executor(orchestrator=FakeOrchestrator(fail_at="run"))
        with self.assertRaises(RuntimePlanExecutionRejected):
            executor.execute_plan("exec-1", "plan-1", [self._operation()])

        self.assertEqual(executor.get_execution("exec-1").status, "failed")

    def test_sequence_increments_globally(self) -> None:
        executor = self._executor()
        first = executor.execute_plan("exec-1", "plan-1", [self._operation()])
        second = executor.execute_plan("exec-2", "plan-2", [self._operation()])

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_payload_preserved(self) -> None:
        payload = {"batch": "one"}
        execution = self._executor().execute_plan(
            "exec-1",
            "plan-1",
            [self._operation()],
            payload=payload,
        )

        self.assertIs(execution.payload, payload)

    def test_metadata_preserved(self) -> None:
        metadata = {"source": "contract"}
        execution = self._executor().execute_plan(
            "exec-1",
            "plan-1",
            [self._operation()],
            metadata=metadata,
        )

        self.assertIs(execution.metadata, metadata)

    def test_operations_preserved(self) -> None:
        operations = [self._operation()]
        execution = self._executor().execute_plan("exec-1", "plan-1", operations)

        self.assertIs(execution.operations, operations)

    def test_payload_not_mutated(self) -> None:
        payload = {"items": [{"id": "one"}]}
        before = copy.deepcopy(payload)
        self._executor().execute_plan(
            "exec-1",
            "plan-1",
            [self._operation()],
            payload=payload,
        )

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        metadata = {"tags": ["contract"]}
        before = copy.deepcopy(metadata)
        self._executor().execute_plan(
            "exec-1",
            "plan-1",
            [self._operation()],
            metadata=metadata,
        )

        self.assertEqual(metadata, before)

    def test_operations_not_mutated(self) -> None:
        operations = [self._operation()]
        before = copy.deepcopy(operations)
        self._executor().execute_plan("exec-1", "plan-1", operations)

        self.assertEqual(operations, before)

    def test_get_execution_returns_copy(self) -> None:
        executor = self._executor()
        executor.execute_plan("exec-1", "plan-1", [self._operation()])
        execution = executor.get_execution("exec-1")
        execution.status = "polluted"

        self.assertEqual(executor.get_execution("exec-1").status, "completed")

    def test_list_executions_returns_copy(self) -> None:
        executor = self._executor()
        executor.execute_plan("exec-1", "plan-1", [self._operation()])
        executions = executor.list_executions()
        executions[0].status = "polluted"
        executions.clear()

        current = executor.list_executions()
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].status, "completed")

    def test_clear_resets_executor_and_sequence(self) -> None:
        executor = self._executor()
        executor.execute_plan("exec-1", "plan-1", [self._operation()])
        executor.clear()
        execution = executor.execute_plan("exec-2", "plan-2", [self._operation()])

        self.assertEqual(execution.sequence, 1)
        self.assertEqual(len(executor.list_executions()), 1)


if __name__ == "__main__":
    unittest.main()
