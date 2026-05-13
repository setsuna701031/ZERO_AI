from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeOperationContractTest(unittest.TestCase):
    def _operation(self):
        from core.runtime.runtime_operation import RuntimeOperation

        return RuntimeOperation(
            "op-1",
            "lifecycle.queue",
            runtime_args={"lifecycle_id": "life-1"},
            payload={"task_id": "task-1"},
            metadata={"source": "contract"},
            dependency_ids=["dep-1"],
        )

    def test_create_operation_pending(self) -> None:
        from core.runtime.runtime_operation import RuntimeOperationStatus

        operation = self._operation()

        self.assertEqual(operation.operation_id, "op-1")
        self.assertEqual(operation.status, RuntimeOperationStatus.PENDING)

    def test_empty_operation_id_rejected(self) -> None:
        from core.runtime.runtime_operation import RuntimeOperation, RuntimeOperationRejected

        with self.assertRaises(RuntimeOperationRejected):
            RuntimeOperation("", "lifecycle.queue")

    def test_empty_operation_rejected(self) -> None:
        from core.runtime.runtime_operation import RuntimeOperation, RuntimeOperationRejected

        with self.assertRaises(RuntimeOperationRejected):
            RuntimeOperation("op-1", "")

    def test_pending_to_running(self) -> None:
        from core.runtime.runtime_operation import RuntimeOperationStatus

        operation = self._operation()
        operation.start()

        self.assertEqual(operation.status, RuntimeOperationStatus.RUNNING)

    def test_running_to_succeeded(self) -> None:
        from core.runtime.runtime_operation import RuntimeOperationStatus

        operation = self._operation()
        result = operation.start().succeed({"ok": True})

        self.assertEqual(operation.status, RuntimeOperationStatus.SUCCEEDED)
        self.assertEqual(result.status, RuntimeOperationStatus.SUCCEEDED)
        self.assertEqual(result.value, {"ok": True})

    def test_running_to_failed(self) -> None:
        from core.runtime.runtime_operation import RuntimeOperationStatus

        operation = self._operation()
        result = operation.start().fail({"error": "boom"})

        self.assertEqual(operation.status, RuntimeOperationStatus.FAILED)
        self.assertEqual(result.status, RuntimeOperationStatus.FAILED)
        self.assertEqual(operation.failure, {"error": "boom"})

    def test_running_to_blocked(self) -> None:
        from core.runtime.runtime_operation import RuntimeOperationStatus

        operation = self._operation()
        result = operation.start().block({"reason": "policy"})

        self.assertEqual(operation.status, RuntimeOperationStatus.BLOCKED)
        self.assertEqual(result.status, RuntimeOperationStatus.BLOCKED)

    def test_cannot_succeed_before_running(self) -> None:
        from core.runtime.runtime_operation import RuntimeOperationRejected

        with self.assertRaises(RuntimeOperationRejected):
            self._operation().succeed()

    def test_terminal_status_cannot_transition_again(self) -> None:
        from core.runtime.runtime_operation import RuntimeOperationRejected

        operation = self._operation()
        operation.start().succeed()

        with self.assertRaises(RuntimeOperationRejected):
            operation.start()
        with self.assertRaises(RuntimeOperationRejected):
            operation.fail({"error": "late"})

    def test_dependency_ids_return_copy(self) -> None:
        operation = self._operation()
        dependencies = operation.dependency_ids
        dependencies.append("polluted")

        self.assertEqual(operation.dependency_ids, ["dep-1"])

    def test_payload_metadata_runtime_args_return_copy(self) -> None:
        operation = self._operation()
        payload = operation.payload
        metadata = operation.metadata
        runtime_args = operation.runtime_args
        payload["task_id"] = "polluted"
        metadata["source"] = "polluted"
        runtime_args["lifecycle_id"] = "polluted"

        self.assertEqual(operation.payload, {"task_id": "task-1"})
        self.assertEqual(operation.metadata, {"source": "contract"})
        self.assertEqual(operation.runtime_args, {"lifecycle_id": "life-1"})

    def test_result_only_attaches_once(self) -> None:
        from core.runtime.runtime_operation import (
            RuntimeOperationRejected,
            RuntimeOperationResult,
        )

        operation = self._operation()
        operation.attach_result(RuntimeOperationResult("op-1", "succeeded"))

        with self.assertRaises(RuntimeOperationRejected):
            operation.attach_result(RuntimeOperationResult("op-1", "succeeded"))

    def test_failure_only_attaches_once(self) -> None:
        from core.runtime.runtime_operation import RuntimeOperationRejected

        operation = self._operation()
        operation.attach_failure({"error": "first"})

        with self.assertRaises(RuntimeOperationRejected):
            operation.attach_failure({"error": "second"})

    def test_result_returns_copy(self) -> None:
        operation = self._operation()
        result = operation.start().succeed({"items": ["ok"]})
        result.value["items"].append("polluted")

        self.assertEqual(operation.result.value, {"items": ["ok"]})

    def test_failure_returns_copy(self) -> None:
        operation = self._operation()
        failure = operation.start().fail({"items": ["bad"]})
        failure.failure["items"].append("polluted")

        self.assertEqual(operation.failure, {"items": ["bad"]})

    def test_fingerprint_is_deterministic(self) -> None:
        from core.runtime.runtime_operation import RuntimeOperation

        first = RuntimeOperation(
            "op-1",
            "lifecycle.queue",
            runtime_args={"b": 2, "a": 1},
            payload={"x": {"b": 2, "a": 1}},
            metadata={"z": 3},
            dependency_ids=["dep-1"],
        )
        second = RuntimeOperation(
            "op-1",
            "lifecycle.queue",
            runtime_args={"a": 1, "b": 2},
            payload={"x": {"a": 1, "b": 2}},
            metadata={"z": 3},
            dependency_ids=["dep-1"],
        )

        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_fingerprint_changes_when_contract_changes(self) -> None:
        from core.runtime.runtime_operation import RuntimeOperation

        first = RuntimeOperation("op-1", "lifecycle.queue")
        second = RuntimeOperation("op-2", "lifecycle.queue")

        self.assertNotEqual(first.fingerprint, second.fingerprint)

    def test_inputs_not_mutated(self) -> None:
        from core.runtime.runtime_operation import RuntimeOperation

        runtime_args = {"items": [{"id": "life-1"}]}
        payload = {"items": [{"id": "task-1"}]}
        metadata = {"tags": ["contract"]}
        dependencies = ["dep-1"]
        before = copy.deepcopy((runtime_args, payload, metadata, dependencies))

        RuntimeOperation(
            "op-1",
            "lifecycle.queue",
            runtime_args=runtime_args,
            payload=payload,
            metadata=metadata,
            dependency_ids=dependencies,
        )

        self.assertEqual((runtime_args, payload, metadata, dependencies), before)


if __name__ == "__main__":
    unittest.main()
