from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class GuardObservabilityEnvelopeContractTest(unittest.TestCase):
    def test_allow_result_gets_observability_event(self) -> None:
        from core.tasks.execution_guard import ExecutionGuard

        with tempfile.TemporaryDirectory() as tmp:
            guard = ExecutionGuard(workspace_root=tmp, shared_dir=tmp)
            result = guard._allow(
                guard_mode="workspace_read",
                policy_action="allow",
                policy_reason="path allowed",
            )

        event = result.get("observability_event")
        adapter = result.get("adapter_payload")

        self.assertIsInstance(event, dict)
        self.assertIs(event.get("ok"), True)
        self.assertEqual(event.get("event_type"), "execution_guard")
        self.assertEqual(event.get("guard_mode"), "workspace_read")
        self.assertEqual(event.get("policy_action"), "allow")
        self.assertEqual(event.get("policy_reason"), "path allowed")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), True)
        self.assertEqual(adapter.get("runtime_mode"), "guard")
        self.assertIsInstance(adapter.get("execution_trace"), list)

    def test_deny_result_gets_observability_event_and_error_payload(self) -> None:
        from core.tasks.execution_guard import ExecutionGuard

        with tempfile.TemporaryDirectory() as tmp:
            guard = ExecutionGuard(workspace_root=tmp, shared_dir=tmp)
            result = guard._deny(
                "blocked path",
                guard_mode="path_outside_workspace",
                policy_action="deny",
                policy_reason="path outside workspace",
            )

        event = result.get("observability_event")
        adapter = result.get("adapter_payload")

        self.assertIsInstance(event, dict)
        self.assertIs(event.get("ok"), False)
        self.assertEqual(event.get("event_type"), "execution_guard")
        self.assertEqual(event.get("guard_mode"), "path_outside_workspace")
        self.assertEqual(event.get("policy_action"), "deny")
        self.assertEqual(event.get("policy_reason"), "path outside workspace")
        self.assertEqual(event.get("error_text"), "blocked path")

        self.assertIsInstance(adapter, dict)
        self.assertIs(adapter.get("ok"), False)
        self.assertEqual(adapter.get("error_type"), "path_outside_workspace")
        self.assertEqual(adapter.get("error_text"), "blocked path")
        self.assertEqual(adapter.get("runtime_mode"), "guard")

    def test_existing_observability_event_is_preserved(self) -> None:
        from core.tasks.execution_guard import ExecutionGuard

        with tempfile.TemporaryDirectory() as tmp:
            guard = ExecutionGuard(workspace_root=tmp, shared_dir=tmp)
            payload = {
                "ok": True,
                "observability_event": {
                    "event_type": "custom",
                    "ok": True,
                },
            }
            result = guard._attach_guard_observability_event(payload)

        self.assertIs(result, payload)
        self.assertEqual(result["observability_event"]["event_type"], "custom")


if __name__ == "__main__":
    unittest.main()
