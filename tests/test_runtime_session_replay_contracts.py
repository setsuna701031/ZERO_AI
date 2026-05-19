from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeSessionReplayContractsTest(unittest.TestCase):
    def test_runtime_session_replay_contract_smoke(self) -> None:
        from core.runtime.runtime_execution_session import RuntimeExecutionSessionManager
        from core.runtime.runtime_replay_engine import RuntimeReplayEngine

        manager = RuntimeExecutionSessionManager()
        manager.create_session("session-1", "life-1", replay_group="group-a")
        manager.start_session("session-1")
        manager.complete_session("session-1")

        replay = RuntimeReplayEngine(session_manager=manager).replay_session(
            "replay-1",
            "session-1",
        )

        self.assertEqual(replay.replay_id, "replay-1")
        self.assertEqual(replay.source_session_id, "session-1")
        self.assertEqual(
            [record.phase for record in replay.records],
            ["queued", "dispatched", "executing", "completed"],
        )


if __name__ == "__main__":
    unittest.main()
