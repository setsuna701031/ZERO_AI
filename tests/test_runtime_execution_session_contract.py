from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeExecutionSessionContractTest(unittest.TestCase):
    def _manager_with_started_session(self):
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        manager = RuntimeExecutionSessionManager()
        manager.create_session("session-1", "life-1")
        manager.start_session("session-1")
        return manager

    def test_create_session_records_queued_lifecycle(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        session = RuntimeExecutionSessionManager().create_session(
            "session-1",
            "life-1",
        )

        self.assertEqual(session.session_id, "session-1")
        self.assertEqual(session.lifecycle_records[0].phase, "queued")

    def test_duplicate_session_rejected(self) -> None:
        from core.runtime.runtime_execution_session import (
            RuntimeExecutionSessionManager,
            RuntimeExecutionSessionRejected,
        )

        manager = RuntimeExecutionSessionManager()
        manager.create_session("session-1", "life-1")

        with self.assertRaises(RuntimeExecutionSessionRejected):
            manager.create_session("session-1", "life-2")

    def test_empty_session_id_rejected(self) -> None:
        from core.runtime.runtime_execution_session import (
            RuntimeExecutionSessionManager,
            RuntimeExecutionSessionRejected,
        )

        with self.assertRaises(RuntimeExecutionSessionRejected):
            RuntimeExecutionSessionManager().create_session("", "life-1")

    def test_empty_lifecycle_id_rejected(self) -> None:
        from core.runtime.runtime_execution_session import (
            RuntimeExecutionSessionManager,
            RuntimeExecutionSessionRejected,
        )

        with self.assertRaises(RuntimeExecutionSessionRejected):
            RuntimeExecutionSessionManager().create_session("session-1", "")

    def test_parent_must_exist(self) -> None:
        from core.runtime.runtime_execution_session import (
            RuntimeExecutionSessionManager,
            RuntimeExecutionSessionRejected,
        )

        with self.assertRaises(RuntimeExecutionSessionRejected):
            RuntimeExecutionSessionManager().create_session(
                "session-1",
                "life-1",
                parent_session_id="missing",
            )

    def test_start_session_records_dispatched_and_executing(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        manager = RuntimeExecutionSessionManager()
        manager.create_session("session-1", "life-1")
        session = manager.start_session("session-1")

        self.assertEqual(
            [record.phase for record in session.lifecycle_records],
            ["queued", "dispatched", "executing"],
        )

    def test_complete_session_records_completed(self) -> None:
        manager = self._manager_with_started_session()

        session = manager.complete_session("session-1")

        self.assertEqual(session.lifecycle_records[-1].phase, "completed")

    def test_fail_session_records_failed(self) -> None:
        manager = self._manager_with_started_session()

        session = manager.fail_session("session-1")

        self.assertEqual(session.lifecycle_records[-1].phase, "failed")

    def test_incident_requires_failed_lifecycle(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionRejected

        manager = self._manager_with_started_session()

        with self.assertRaises(RuntimeExecutionSessionRejected):
            manager.incident_session("session-1")

    def test_repair_requires_incident_lifecycle(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionRejected

        manager = self._manager_with_started_session()
        manager.fail_session("session-1")

        with self.assertRaises(RuntimeExecutionSessionRejected):
            manager.repair_session("session-1")

    def test_replay_requires_completed_or_repaired_lifecycle(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionRejected

        completed = self._manager_with_started_session()
        completed.complete_session("session-1")
        completed_session = completed.replay_session("session-1")

        repaired = self._manager_with_started_session()
        repaired.fail_session("session-1")
        repaired.incident_session("session-1")
        repaired.repair_session("session-1")
        repaired_session = repaired.replay_session("session-1")

        blocked = self._manager_with_started_session()
        with self.assertRaises(RuntimeExecutionSessionRejected):
            blocked.replay_session("session-1")

        self.assertEqual(completed_session.lifecycle_records[-1].phase, "replayed")
        self.assertEqual(repaired_session.lifecycle_records[-1].phase, "replayed")

    def test_sequence_increments_globally(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        manager = RuntimeExecutionSessionManager()
        first = manager.create_session("session-1", "life-1")
        second = manager.create_session("session-2", "life-2")

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_get_session_returns_copy(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        manager = RuntimeExecutionSessionManager()
        manager.create_session("session-1", "life-1")
        session = manager.get_session("session-1")
        session.lifecycle_records.clear()

        self.assertEqual(len(manager.get_session("session-1").lifecycle_records), 1)

    def test_get_sessions_returns_all_sessions(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        manager = RuntimeExecutionSessionManager()
        manager.create_session("session-1", "life-1")
        manager.create_session("session-2", "life-2")

        self.assertEqual(
            [session.session_id for session in manager.get_sessions()],
            ["session-1", "session-2"],
        )

    def test_get_sessions_filters_replay_group(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        manager = RuntimeExecutionSessionManager()
        manager.create_session("session-1", "life-1", replay_group="group-a")
        manager.create_session("session-2", "life-2", replay_group="group-b")

        self.assertEqual(
            [session.session_id for session in manager.get_sessions("group-a")],
            ["session-1"],
        )

    def test_get_sessions_returns_copy(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        manager = RuntimeExecutionSessionManager()
        manager.create_session("session-1", "life-1")
        sessions = manager.get_sessions()
        sessions[0].lifecycle_records.clear()

        self.assertEqual(len(manager.get_sessions()[0].lifecycle_records), 1)

    def test_lineage_returns_root_to_child_order(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        manager = RuntimeExecutionSessionManager()
        manager.create_session("root", "life-root")
        manager.create_session("child", "life-child", parent_session_id="root")
        manager.create_session("grandchild", "life-grand", parent_session_id="child")

        self.assertEqual(
            [session.session_id for session in manager.get_lineage("grandchild")],
            ["root", "child", "grandchild"],
        )

    def test_payload_preserved(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        payload = {"task_id": "task-1", "state": "queued"}

        session = RuntimeExecutionSessionManager().create_session(
            "session-1",
            "life-1",
            payload=payload,
        )

        self.assertIs(session.payload, payload)
        self.assertIs(session.lifecycle_records[0].payload, payload)

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        metadata = {"source": "contract", "attempt": 1}

        session = RuntimeExecutionSessionManager().create_session(
            "session-1",
            "life-1",
            metadata=metadata,
        )

        self.assertIs(session.metadata, metadata)
        self.assertIs(session.lifecycle_records[0].metadata, metadata)

    def test_payload_not_mutated(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        payload = {"items": [{"task_id": "task-1", "state": "queued"}]}
        before = copy.deepcopy(payload)

        RuntimeExecutionSessionManager().create_session(
            "session-1",
            "life-1",
            payload=payload,
        )

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        metadata = {"tags": ["contract"], "attempt": 1}
        before = copy.deepcopy(metadata)

        RuntimeExecutionSessionManager().create_session(
            "session-1",
            "life-1",
            metadata=metadata,
        )

        self.assertEqual(metadata, before)

    def test_lifecycle_exception_wraps_runtime_execution_session_rejected(self) -> None:
        from core.runtime.runtime_execution_session import (
            RuntimeExecutionSessionManager,
            RuntimeExecutionSessionRejected,
        )

        original = ValueError("boom")

        class FailingLifecyclePipeline:
            def queue(self, lifecycle_id, payload=None, metadata=None):
                raise original

            def clear(self):
                pass

        with self.assertRaises(RuntimeExecutionSessionRejected) as context:
            RuntimeExecutionSessionManager(
                lifecycle_pipeline=FailingLifecyclePipeline()
            ).create_session("session-1", "life-1")

        self.assertIs(context.exception.original_exception, original)

    def test_clear_resets_manager_and_sequence(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        manager = RuntimeExecutionSessionManager()
        manager.create_session("session-1", "life-1")
        manager.clear()
        session = manager.create_session("session-2", "life-2")

        self.assertEqual(session.sequence, 1)
        self.assertEqual(
            [stored.session_id for stored in manager.get_sessions()],
            ["session-2"],
        )

    def test_session_includes_lifecycle_records(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        session = RuntimeExecutionSessionManager().create_session(
            "session-1",
            "life-1",
        )

        self.assertEqual(len(session.lifecycle_records), 1)
        self.assertEqual(session.lifecycle_records[0].phase, "queued")


if __name__ == "__main__":
    unittest.main()
