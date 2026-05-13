from __future__ import annotations

from pathlib import Path


RECOVERY_PATH = Path("core/runtime/runtime_recovery.py")
TEST_PATH = Path("tests/test_runtime_recovery_contract.py")


RECOVERY_CONTENT = r'''from __future__ import annotations

import time
from typing import Any, Dict, List


class RuntimeRecovery:
    TERMINAL_RUNTIME_STATUSES = {
        "finished",
        "failed",
        "blocked",
    }

    def __init__(
        self,
        *,
        max_recovery_attempts: int = 3,
    ) -> None:
        self.max_recovery_attempts = int(max_recovery_attempts)

    def evaluate(
        self,
        runtime_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        degraded = bool(runtime_state.get("degraded"))
        stalled = bool(runtime_state.get("stalled"))

        recovery_history = runtime_state.get("recovery_history")
        if not isinstance(recovery_history, list):
            recovery_history = []

        attempts = len(recovery_history)

        recovery_required = degraded or stalled

        recovery_blocked = attempts >= self.max_recovery_attempts

        action = "none"

        if recovery_required and not recovery_blocked:
            action = "recover"

        if recovery_required and recovery_blocked:
            action = "halt"

        return {
            "runtime_phase": "runtime_recovery",
            "runtime_status": runtime_state.get("runtime_status", "unknown"),
            "recovery_required": recovery_required,
            "recovery_blocked": recovery_blocked,
            "recovery_attempts": attempts,
            "action": action,
        }

    def create_recovery_event(
        self,
        *,
        reason: str,
        action: str,
    ) -> Dict[str, Any]:
        return {
            "event_type": "runtime_recovery",
            "runtime_phase": "runtime_recovery",
            "runtime_status": action,
            "reason": str(reason or ""),
            "timestamp": time.time(),
        }

    def append_recovery_history(
        self,
        runtime_state: Dict[str, Any],
        *,
        reason: str,
        action: str,
    ) -> Dict[str, Any]:
        history = runtime_state.get("recovery_history")

        if not isinstance(history, list):
            history = []

        event = self.create_recovery_event(
            reason=reason,
            action=action,
        )

        history.append(event)

        runtime_state["recovery_history"] = history

        return runtime_state
'''


TEST_CONTENT = r'''from __future__ import annotations

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
'''


def main() -> None:
    RECOVERY_PATH.write_text(RECOVERY_CONTENT, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("[runtime-recovery-v1] created core/runtime/runtime_recovery.py")
    print("[runtime-recovery-v1] created tests/test_runtime_recovery_contract.py")


if __name__ == "__main__":
    main()