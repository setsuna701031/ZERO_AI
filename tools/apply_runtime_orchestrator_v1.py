from __future__ import annotations

from pathlib import Path


ORCHESTRATOR_PATH = Path("core/runtime/runtime_orchestrator.py")
TEST_PATH = Path("tests/test_runtime_orchestrator_contract.py")


ORCHESTRATOR_CONTENT = r'''from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from core.runtime.runtime_monitor import RuntimeMonitor
from core.runtime.runtime_recovery import RuntimeRecovery
from core.runtime.runtime_snapshot import RuntimeSnapshot
from core.runtime.runtime_state import RuntimeState


class RuntimeOrchestrator:
    def __init__(
        self,
        event_log_path: str | Path,
        *,
        stalled_timeout_seconds: float = 300.0,
        max_recovery_attempts: int = 3,
    ) -> None:
        self.event_log_path = Path(event_log_path)
        self.monitor = RuntimeMonitor(
            self.event_log_path,
            stalled_timeout_seconds=stalled_timeout_seconds,
        )
        self.recovery = RuntimeRecovery(max_recovery_attempts=max_recovery_attempts)
        self.snapshot = RuntimeSnapshot(self.event_log_path)
        self.state = RuntimeState(self.event_log_path)

    def evaluate_runtime(self) -> Dict[str, Any]:
        state = self.state.aggregate()
        monitor_result = self.monitor.poll()

        merged_state = {
            **state,
            "degraded": bool(monitor_result.get("degraded")),
            "stalled": bool(monitor_result.get("stalled")),
            "alerts": monitor_result.get("alerts", []),
        }

        recovery_result = self.recovery.evaluate(merged_state)
        snapshot = self.snapshot.build_snapshot()

        return {
            "ok": bool(monitor_result.get("ok", True)) and not bool(recovery_result.get("recovery_blocked")),
            "runtime_phase": "runtime_orchestrator",
            "runtime_status": merged_state.get("runtime_status", "unknown"),
            "monitor": monitor_result,
            "recovery": recovery_result,
            "snapshot": snapshot,
            "state": state,
        }

    def should_trigger_recovery(self) -> bool:
        result = self.evaluate_runtime()
        recovery = result.get("recovery")
        if not isinstance(recovery, dict):
            return False
        return str(recovery.get("action") or "") == "recover"
'''


TEST_CONTENT = r'''from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class RuntimeOrchestratorContractTest(unittest.TestCase):
    def test_runtime_orchestrator_evaluate_runtime(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink
        from core.runtime.runtime_orchestrator import RuntimeOrchestrator

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            sink = RuntimeEventSink(path)
            sink.append_event({
                "event_type": "status",
                "runtime_mode": "execute",
                "status": "running",
                "task_id": "task-1",
                "timestamp": time.time(),
            })

            orchestrator = RuntimeOrchestrator(path)
            result = orchestrator.evaluate_runtime()

        self.assertEqual(result["runtime_phase"], "runtime_orchestrator")
        self.assertEqual(result["runtime_status"], "running")
        self.assertIn("monitor", result)
        self.assertIn("recovery", result)
        self.assertIn("snapshot", result)
        self.assertIn("state", result)

    def test_runtime_orchestrator_triggers_recovery(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink
        from core.runtime.runtime_orchestrator import RuntimeOrchestrator

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            sink = RuntimeEventSink(path)
            sink.append_event({
                "event_type": "failure",
                "runtime_mode": "repo_state",
                "timestamp": time.time(),
            })

            orchestrator = RuntimeOrchestrator(path)
            should = orchestrator.should_trigger_recovery()

        self.assertTrue(should)

    def test_runtime_orchestrator_does_not_trigger_recovery(self) -> None:
        from core.runtime.event_sink import RuntimeEventSink
        from core.runtime.runtime_orchestrator import RuntimeOrchestrator

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            sink = RuntimeEventSink(path)
            sink.append_event({
                "event_type": "status",
                "runtime_mode": "execute",
                "status": "running",
                "timestamp": time.time(),
            })

            orchestrator = RuntimeOrchestrator(path)
            should = orchestrator.should_trigger_recovery()

        self.assertFalse(should)


if __name__ == "__main__":
    unittest.main()
'''


def main() -> None:
    ORCHESTRATOR_PATH.write_text(ORCHESTRATOR_CONTENT, encoding="utf-8")
    TEST_PATH.write_text(TEST_CONTENT, encoding="utf-8")

    print("[runtime-orchestrator-v1] updated core/runtime/runtime_orchestrator.py")
    print("[runtime-orchestrator-v1] updated tests/test_runtime_orchestrator_contract.py")


if __name__ == "__main__":
    main()