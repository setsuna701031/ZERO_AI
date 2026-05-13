from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeReplayEngineContractTest(unittest.TestCase):
    def _manager_with_completed_session(self):
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager

        manager = RuntimeExecutionSessionManager()
        manager.create_session(
            "session-1",
            "life-1",
            replay_group="group-a",
        )
        manager.start_session("session-1")
        manager.complete_session("session-1")
        return manager

    def test_replay_id_empty_rejected(self) -> None:
        from core.runtime.runtime_replay_engine import (
            RuntimeReplayEngine,
            RuntimeReplayRejected,
        )

        with self.assertRaises(RuntimeReplayRejected):
            RuntimeReplayEngine().replay_session("", "session-1")

    def test_duplicate_replay_id_rejected(self) -> None:
        from core.runtime.runtime_replay_engine import (
            RuntimeReplayEngine,
            RuntimeReplayRejected,
        )

        engine = RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        )
        engine.replay_session("replay-1", "session-1")

        with self.assertRaises(RuntimeReplayRejected):
            engine.replay_session("replay-1", "session-1")

    def test_missing_source_session_rejected(self) -> None:
        from core.runtime.runtime_replay_engine import (
            RuntimeReplayEngine,
            RuntimeReplayRejected,
        )

        with self.assertRaises(RuntimeReplayRejected):
            RuntimeReplayEngine(
                session_manager=self._manager_with_completed_session()
            ).replay_session("replay-1", "missing")

    def test_replay_session_creates_replay_session(self) -> None:
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        replay = RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        ).replay_session("replay-1", "session-1")

        self.assertEqual(replay.replay_id, "replay-1")
        self.assertTrue(replay.records)

    def test_replay_session_preserves_source_session_id(self) -> None:
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        replay = RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        ).replay_session("replay-1", "session-1")

        self.assertEqual(replay.source_session_id, "session-1")
        self.assertEqual(
            {record.source_session_id for record in replay.records},
            {"session-1"},
        )

    def test_replay_session_preserves_replay_group(self) -> None:
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        replay = RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        ).replay_session("replay-1", "session-1")

        self.assertEqual(replay.replay_group, "group-a")

    def test_replay_records_follow_lifecycle_sequence(self) -> None:
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        replay = RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        ).replay_session("replay-1", "session-1")

        self.assertEqual(
            [record.phase for record in replay.records],
            ["queued", "dispatched", "executing", "completed"],
        )
        self.assertEqual(
            [record.original_sequence for record in replay.records],
            [1, 2, 3, 4],
        )

    def test_replay_sequence_starts_at_1(self) -> None:
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        replay = RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        ).replay_session("replay-1", "session-1")

        self.assertEqual(
            [record.replay_sequence for record in replay.records],
            [1, 2, 3, 4],
        )

    def test_engine_replay_session_sequence_increments_globally(self) -> None:
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        engine = RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        )
        first = engine.replay_session("replay-1", "session-1")
        second = engine.replay_session("replay-2", "session-1")

        self.assertEqual([first.sequence, second.sequence], [1, 2])

    def test_handler_receives_records_in_replay_sequence_order(self) -> None:
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        received = []
        RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        ).replay_session(
            "replay-1",
            "session-1",
            handler=lambda record: received.append(record.replay_sequence),
        )

        self.assertEqual(received, [1, 2, 3, 4])

    def test_handler_exception_raises_runtime_replay_rejected(self) -> None:
        from core.runtime.runtime_replay_engine import (
            RuntimeReplayEngine,
            RuntimeReplayRejected,
        )

        original = ValueError("boom")

        def fail(_record) -> None:
            raise original

        with self.assertRaises(RuntimeReplayRejected) as context:
            RuntimeReplayEngine(
                session_manager=self._manager_with_completed_session()
            ).replay_session("replay-1", "session-1", handler=fail)

        self.assertIs(context.exception.original_exception, original)

    def test_replay_session_verified_true_after_completion(self) -> None:
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        replay = RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        ).replay_session("replay-1", "session-1")

        self.assertTrue(replay.verified)

    def test_replay_group_replays_all_sessions_in_group(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        manager = RuntimeExecutionSessionManager()
        manager.create_session("session-1", "life-1", replay_group="group-a")
        manager.start_session("session-1")
        manager.complete_session("session-1")
        manager.create_session("session-2", "life-2", replay_group="group-a")
        manager.start_session("session-2")
        manager.complete_session("session-2")
        manager.create_session("session-3", "life-3", replay_group="group-b")

        replay = RuntimeReplayEngine(session_manager=manager).replay_group(
            "replay-1",
            "group-a",
        )

        self.assertEqual(replay.replay_group, "group-a")
        self.assertEqual(
            [record.source_session_id for record in replay.records],
            ["session-1"] * 4 + ["session-2"] * 4,
        )

    def test_replay_group_rejects_empty_match(self) -> None:
        from core.runtime.runtime_replay_engine import (
            RuntimeReplayEngine,
            RuntimeReplayRejected,
        )

        with self.assertRaises(RuntimeReplayRejected):
            RuntimeReplayEngine(
                session_manager=self._manager_with_completed_session()
            ).replay_group("replay-1", "missing-group")

    def test_payload_preserved(self) -> None:
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        payload = {"mode": "verify", "items": [1, 2]}

        replay = RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        ).replay_session("replay-1", "session-1", payload=payload)

        self.assertIs(replay.payload, payload)

    def test_metadata_preserved(self) -> None:
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        metadata = {"source": "contract", "attempt": 1}

        replay = RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        ).replay_session("replay-1", "session-1", metadata=metadata)

        self.assertIs(replay.metadata, metadata)

    def test_payload_not_mutated(self) -> None:
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        payload = {"items": [{"phase": "queued"}]}
        before = copy.deepcopy(payload)

        RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        ).replay_session("replay-1", "session-1", payload=payload)

        self.assertEqual(payload, before)

    def test_metadata_not_mutated(self) -> None:
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        metadata = {"tags": ["contract"], "attempt": 1}
        before = copy.deepcopy(metadata)

        RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        ).replay_session("replay-1", "session-1", metadata=metadata)

        self.assertEqual(metadata, before)

    def test_get_replay_returns_copy(self) -> None:
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        engine = RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        )
        engine.replay_session("replay-1", "session-1")
        replay = engine.get_replay("replay-1")
        replay.records.clear()

        self.assertEqual(len(engine.get_replay("replay-1").records), 4)

    def test_get_replays_returns_copy(self) -> None:
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        engine = RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        )
        engine.replay_session("replay-1", "session-1")
        replays = engine.get_replays()
        replays[0].records.clear()
        replays.clear()

        self.assertEqual(len(engine.get_replays()), 1)
        self.assertEqual(len(engine.get_replays()[0].records), 4)

    def test_clear_resets_replays_and_sequence(self) -> None:
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        engine = RuntimeReplayEngine(
            session_manager=self._manager_with_completed_session()
        )
        engine.replay_session("replay-1", "session-1")
        engine.clear()
        replay = engine.replay_session("replay-2", "session-1")

        self.assertEqual(replay.sequence, 1)
        self.assertEqual([item.replay_id for item in engine.get_replays()], ["replay-2"])

    def test_source_lifecycle_records_are_not_mutated(self) -> None:
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        manager = self._manager_with_completed_session()
        before = [
            record.phase
            for record in manager.get_session("session-1").lifecycle_records
        ]

        RuntimeReplayEngine(session_manager=manager).replay_session(
            "replay-1",
            "session-1",
        )

        after = [
            record.phase
            for record in manager.get_session("session-1").lifecycle_records
        ]
        self.assertEqual(after, before)

    def test_session_manager_exception_wraps_runtime_replay_rejected(self) -> None:
        from core.runtime.runtime_replay_engine import (
            RuntimeReplayEngine,
            RuntimeReplayRejected,
        )

        original = ValueError("boom")

        class FailingSessionManager:
            def get_session(self, _session_id):
                raise original

        with self.assertRaises(RuntimeReplayRejected) as context:
            RuntimeReplayEngine(
                session_manager=FailingSessionManager()
            ).replay_session("replay-1", "session-1")

        self.assertIs(context.exception.original_exception, original)


if __name__ == "__main__":
    unittest.main()
