from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeRecoveryContractTest(unittest.TestCase):
    def test_runtime_recovery_requests_recovery(self) -> None:
        from core.runtime.runtime_recovery import RuntimeRecovery

        recovery = RuntimeRecovery()

        result = recovery.evaluate({
            "runtime_status": "degraded",
            "degraded": True,
            "stalled": False,
            "recovery_history": [],
        })

        self.assertTrue(result["recovery_required"])
        self.assertEqual(result["action"], "recover")

    def test_runtime_recovery_halts_after_max_attempts(self) -> None:
        from core.runtime.runtime_recovery import RuntimeRecovery

        recovery = RuntimeRecovery(max_recovery_attempts=2)

        result = recovery.evaluate({
            "runtime_status": "degraded",
            "degraded": True,
            "stalled": False,
            "recovery_history": [
                {"x": 1},
                {"x": 2},
            ],
        })

        self.assertTrue(result["recovery_blocked"])
        self.assertEqual(result["action"], "halt")

    def test_runtime_recovery_history_append(self) -> None:
        from core.runtime.runtime_recovery import RuntimeRecovery

        recovery = RuntimeRecovery()

        state = recovery.append_recovery_history(
            {},
            reason="runtime stalled",
            action="recover",
        )

        history = state["recovery_history"]

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["event_type"], "runtime_recovery")


if __name__ == "__main__":
    unittest.main()
