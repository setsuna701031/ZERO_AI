from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeBoundaryContractTest(unittest.TestCase):
    def test_scheduler_queue_transition_allowed(self) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundary
        from core.runtime.runtime_ownership import RuntimeOwner

        request = RuntimeBoundary().request_queue_transition(RuntimeOwner.SCHEDULER)

        self.assertTrue(request.allowed)
        self.assertEqual(request.operation, "queue_transition")
        self.assertIsNone(request.rejected_reason)

    def test_scheduler_execution_result_write_rejected(self) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundary, RuntimeBoundaryRejected
        from core.runtime.runtime_ownership import RuntimeOwner

        with self.assertRaises(RuntimeBoundaryRejected):
            RuntimeBoundary().request_execution_result_write(RuntimeOwner.SCHEDULER)

    def test_step_executor_execution_result_write_allowed(self) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundary
        from core.runtime.runtime_ownership import RuntimeOwner

        request = RuntimeBoundary().request_execution_result_write(
            RuntimeOwner.STEP_EXECUTOR
        )

        self.assertTrue(request.allowed)
        self.assertEqual(request.operation, "execution_result_write")

    def test_step_executor_queue_transition_rejected(self) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundary, RuntimeBoundaryRejected
        from core.runtime.runtime_ownership import RuntimeOwner

        with self.assertRaises(RuntimeBoundaryRejected):
            RuntimeBoundary().request_queue_transition(RuntimeOwner.STEP_EXECUTOR)

    def test_orchestrator_dispatch_allowed(self) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundary
        from core.runtime.runtime_ownership import RuntimeOwner

        request = RuntimeBoundary().request_orchestration_dispatch(
            RuntimeOwner.ORCHESTRATOR
        )

        self.assertTrue(request.allowed)
        self.assertEqual(request.operation, "orchestration_dispatch")

    def test_orchestrator_snapshot_rejected(self) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundary, RuntimeBoundaryRejected
        from core.runtime.runtime_ownership import RuntimeOwner

        with self.assertRaises(RuntimeBoundaryRejected):
            RuntimeBoundary().request_runtime_snapshot(RuntimeOwner.ORCHESTRATOR)

    def test_monitor_snapshot_allowed(self) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundary
        from core.runtime.runtime_ownership import RuntimeOwner

        request = RuntimeBoundary().request_runtime_snapshot(RuntimeOwner.MONITOR)

        self.assertTrue(request.allowed)
        self.assertEqual(request.operation, "runtime_snapshot")

    def test_monitor_execution_result_write_rejected(self) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundary, RuntimeBoundaryRejected
        from core.runtime.runtime_ownership import RuntimeOwner

        with self.assertRaises(RuntimeBoundaryRejected):
            RuntimeBoundary().request_execution_result_write(RuntimeOwner.MONITOR)

    def test_repair_chain_incident_emit_allowed(self) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundary
        from core.runtime.runtime_ownership import RuntimeOwner

        request = RuntimeBoundary().emit_runtime_incident(RuntimeOwner.REPAIR_CHAIN)

        self.assertTrue(request.allowed)
        self.assertEqual(request.operation, "runtime_incident_emit")

    def test_repair_chain_queue_transition_rejected(self) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundary, RuntimeBoundaryRejected
        from core.runtime.runtime_ownership import RuntimeOwner

        with self.assertRaises(RuntimeBoundaryRejected):
            RuntimeBoundary().request_queue_transition(RuntimeOwner.REPAIR_CHAIN)

    def test_system_can_call_all_boundary_operations(self) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundary
        from core.runtime.runtime_ownership import RuntimeOwner

        boundary = RuntimeBoundary()
        operations = [
            boundary.request_queue_transition,
            boundary.request_execution_result_write,
            boundary.request_orchestration_dispatch,
            boundary.request_runtime_snapshot,
            boundary.emit_runtime_event,
            boundary.emit_runtime_incident,
        ]

        for operation in operations:
            with self.subTest(operation=operation.__name__):
                self.assertTrue(operation(RuntimeOwner.SYSTEM).allowed)

    def test_payload_preserved(self) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundary
        from core.runtime.runtime_ownership import RuntimeOwner

        payload = {"task_id": "task-1", "status": "queued"}

        request = RuntimeBoundary().request_queue_transition(
            RuntimeOwner.SCHEDULER,
            payload=payload,
        )

        self.assertIs(request.payload, payload)

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundary
        from core.runtime.runtime_ownership import RuntimeOwner

        metadata = {"source": "contract", "attempt": 1}

        request = RuntimeBoundary().emit_runtime_event(
            RuntimeOwner.SCHEDULER,
            metadata=metadata,
        )

        self.assertIs(request.metadata, metadata)

    def test_rejection_keeps_request(self) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundary, RuntimeBoundaryRejected
        from core.runtime.runtime_ownership import RuntimeOwner

        with self.assertRaises(RuntimeBoundaryRejected) as context:
            RuntimeBoundary().request_execution_result_write(RuntimeOwner.SCHEDULER)

        self.assertFalse(context.exception.request.allowed)
        self.assertTrue(context.exception.request.rejected_reason)

    def test_rejected_reason_contains_owner_resource_action_operation(self) -> None:
        from core.runtime.runtime_boundary import RuntimeBoundary, RuntimeBoundaryRejected
        from core.runtime.runtime_ownership import RuntimeOwner

        with self.assertRaises(RuntimeBoundaryRejected) as context:
            RuntimeBoundary().request_runtime_snapshot(RuntimeOwner.ORCHESTRATOR)

        rejected_reason = context.exception.request.rejected_reason or ""

        self.assertIn("owner=", rejected_reason)
        self.assertIn("resource=", rejected_reason)
        self.assertIn("action=", rejected_reason)
        self.assertIn("operation=", rejected_reason)
        self.assertIn("ORCHESTRATOR", rejected_reason)
        self.assertIn("RUNTIME_SNAPSHOT", rejected_reason)
        self.assertIn("SNAPSHOT", rejected_reason)
        self.assertIn("runtime_snapshot", rejected_reason)


if __name__ == "__main__":
    unittest.main()
